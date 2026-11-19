"""实验套编排服务：受理快照、DAG 调度、重试留用、收齐公开。

并发模型：单 worker 进程内用线程池并发跑互不依赖的分支；数据库行锁保证
同一分支不会被重复调度。独立分支可并发，下游等自己的全部上游完成才开跑。
"""
import json
import redis
from fastapi import HTTPException
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.experiment import Experiment, ExperimentBranch
from src.utils.serialization import record
from src.services.dag import validate_definition, GraphError
from src.services.graph_engine import validate_branch_plan, execute_branch

QUEUE_KEY = 'operator-experiments'
queue = redis.Redis.from_url(REDIS_URL)


def _public(row):
    """未公开的套只暴露进度，不泄露分支结果与输入快照；公开后返回完整记录。"""
    data = record(row)
    if not row.published:
        data.pop('result', None)
        data.pop('snapshot', None)
    return data


def list_items():
    with Session() as s:
        rows = s.query(Experiment).order_by(Experiment.id.desc()).limit(100).all()
        return [_public(r) for r in rows]


def detail(item_id):
    with Session() as s:
        row = s.get(Experiment, item_id)
        if not row:
            raise HTTPException(404, '未找到实验套')
        return _public(row)


def branches_for(item_id):
    with Session() as s:
        exp = s.get(Experiment, item_id)
        if not exp:
            raise HTTPException(404, '未找到实验套')
        rows = s.query(ExperimentBranch).filter_by(experiment_id=item_id)\
            .order_by(ExperimentBranch.id).all()
        out = []
        for b in rows:
            d = record(b)
            if not exp.published:
                # 未公开只给进度，不给分支结果
                d.pop('result', None)
            out.append(d)
        return out


def create(data):
    """受理实验套：校验 DAG、冻结计划版本与输入快照、入队根分支。"""
    try:
        nodes = validate_definition([b.model_dump() for b in data.branches])
    except GraphError as exc:
        raise HTTPException(400, str(exc))
    with Session() as s:
        dataset = s.get(Dataset, data.dataset_id)
        if not dataset:
            raise HTTPException(404, '未找到数据集')
        plan_cache = {}

        def plan_with_agg(pid):
            if pid not in plan_cache:
                plan = s.get(Plan, pid)
                if not plan:
                    raise HTTPException(404, '引用的计划不存在')
                if plan.dataset_id != dataset.id:
                    raise HTTPException(400, '分支计划不属于本实验数据集')
                try:
                    agg = validate_branch_plan(plan.steps)
                except GraphError as exc:
                    raise HTTPException(400, str(exc))
                plan_cache[pid] = (plan, agg)
            return plan_cache[pid]

        snapshot = {'dataset': record(dataset), 'plans': {}}
        definition = []
        for node in nodes:
            plan, agg = plan_with_agg(node['plan_id'])
            # 边一致性：下游声明的 measure 必须由上游分组真实产出
            for dep in node['depends_on']:
                dep_node = next(n for n in nodes if n['node_key'] == dep)
                _, dep_agg = plan_with_agg(dep_node['plan_id'])
                if node['measure'] != dep_agg:
                    raise HTTPException(
                        400,
                        f"分支 {node['node_key']} 期望 {node['measure']} 采样，"
                        f"但上游 {dep} 产出的是 {dep_agg}")
            snapshot['plans'][node['node_key']] = record(plan)
            definition.append({**node, 'plan_version': plan.version,
                               'aggregate': agg})

        exp = Experiment(name=data.name, dataset_id=dataset.id, status='running',
                         definition=definition, snapshot=snapshot, published=0)
        s.add(exp)
        s.flush()
        branch_ids = []
        for node in definition:
            status = 'queued' if not node['depends_on'] else 'blocked'
            branch = ExperimentBranch(
                experiment_id=exp.id, node_key=node['node_key'],
                plan_id=node['plan_id'], plan_version=node['plan_version'],
                depends_on=node['depends_on'], measure=node['measure'],
                status=status, attempts=0)
            s.add(branch)
            s.flush()
            if status == 'queued':
                branch_ids.append(branch.id)
        s.commit()
        exp_id = exp.id
    for bid in branch_ids:
        queue.rpush(QUEUE_KEY, json.dumps({'branch_id': bid}))
    return detail(exp_id)


def retry(experiment_id):
    """失败重试：已完成分支原样留用，只重排队 failed 的分支。"""
    queued_ids = []
    with Session() as s:
        exp = s.get(Experiment, experiment_id)
        if not exp:
            raise HTTPException(404, '未找到实验套')
        if exp.status != 'failed':
            raise HTTPException(409, '只有失败的实验套可以重试；在途实验无需重试')
        rows = s.query(ExperimentBranch).filter_by(experiment_id=experiment_id).all()
        for b in rows:
            if b.status == 'failed':
                b.status = 'queued'
                b.error = None
                s.flush()
                queued_ids.append(b.id)
            # completed 分支留用；blocked 分支保持等待，由调度解锁
        exp.status = 'running'
        exp.error = None
        s.commit()
    for bid in queued_ids:
        queue.rpush(QUEUE_KEY, json.dumps({'branch_id': bid}))
    return detail(experiment_id)


# ---- worker 侧调度 ----

def run_branch(branch_id):
    """worker 调用：领取一个分支，合入上游结果后执行，并驱动下游调度。"""
    exp_id = None
    with Session() as s:
        branch = s.get(ExperimentBranch, branch_id)
        if not branch or branch.status != 'queued':
            return  # 已被其他线程领取或已处理，幂等跳过
        exp = s.get(Experiment, branch.experiment_id)
        exp_id = exp.id
        branch.status = 'running'
        branch.attempts = (branch.attempts or 0) + 1
        snapshot = exp.snapshot
        upstream_inputs = []
        for dep in branch.depends_on:
            up = s.query(ExperimentBranch).filter_by(
                experiment_id=exp.id, node_key=dep).one()
            if up.status != 'completed':
                # 并发下不应发生；显式失败而不是静默等待
                s.rollback()
                _mark_failed(branch_id, exp.id,
                             f'上游 {dep} 尚未完成，分支不能开跑')
                _schedule(exp.id)
                return
            upstream_inputs.append((dep, up.result, branch.measure))
        plan_snapshot = snapshot['plans'][branch.node_key]
        try:
            result = execute_branch(snapshot['dataset'], plan_snapshot,
                                    upstream_inputs or None)
        except Exception as exc:
            s.rollback()
            _mark_failed(branch_id, exp.id, str(exc)[:1000])
            _schedule(exp.id)
            return
        branch.status = 'completed'
        branch.result = result
        branch.error = None
        s.commit()
    _schedule(exp_id)


def _mark_failed(branch_id, experiment_id, message):
    with Session() as s:
        b = s.get(ExperimentBranch, branch_id)
        if b and b.status != 'completed':
            b.status = 'failed'
            b.error = message[:1000]
        exp = s.get(Experiment, experiment_id)
        if exp and exp.status == 'running':
            exp.status = 'failed'
            exp.error = f"分支 {b.node_key if b else branch_id} 失败：{message[:800]}"
        s.commit()


def _schedule(experiment_id):
    """上游收敛后解锁下游；全部完成则一次性公开结果。行锁串行化调度。"""
    ready_ids = []
    with Session() as s:
        exp = s.get(Experiment, experiment_id, with_for_update=True)
        branches = s.query(ExperimentBranch).filter_by(
            experiment_id=experiment_id).all()
        by_key = {b.node_key: b for b in branches}
        if any(b.status == 'failed' for b in branches):
            if exp.status == 'running':
                exp.status = 'failed'
            s.commit()
            return
        for b in branches:
            if b.status != 'blocked':
                continue
            if all(by_key[k].status == 'completed' for k in b.depends_on):
                b.status = 'queued'
                s.flush()
                ready_ids.append(b.id)
        s.commit()
        remaining = s.query(ExperimentBranch).filter_by(
            experiment_id=experiment_id).all()
        if all(b.status == 'completed' for b in remaining):
            _publish(experiment_id)
    for bid in ready_ids:
        queue.rpush(QUEUE_KEY, json.dumps({'branch_id': bid}))


def _publish(experiment_id):
    """收齐才一起公开；已公开则不重复发布（重试也不重复发布）。"""
    with Session() as s:
        exp = s.get(Experiment, experiment_id)
        if exp.published:
            return
        branches = s.query(ExperimentBranch).filter_by(
            experiment_id=experiment_id).order_by(ExperimentBranch.id).all()
        if not branches or any(b.status != 'completed' for b in branches):
            return
        from datetime import datetime, timezone
        exp.result = {'branches': [
            {'node_key': b.node_key, 'status': b.status,
             'plan_version': b.plan_version, 'depends_on': b.depends_on,
             'measure': b.measure, 'output_rows': b.result['output_rows'],
             'checksum': b.result['checksum'], 'result': b.result}
            for b in branches]}
        exp.status = 'published'
        exp.published = 1
        exp.published_at = datetime.now(timezone.utc)
        s.commit()
    from src.services.audit import log
    log('worker', 'experiment.published', str(experiment_id))


def export(experiment_id):
    with Session() as s:
        exp = s.get(Experiment, experiment_id)
        if not exp:
            raise HTTPException(404, '未找到实验套')
        if not exp.published:
            raise HTTPException(409, '实验尚未收齐公开，结果暂不可导出')
        return record(exp)
