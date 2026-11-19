"""启动引导：幂等建表与崩溃恢复。

SQLAlchemy metadata 负责建表（含新增的 experiments / experiment_branches）。
worker 崩溃后没有自动重跑在途分支（与单计划 trace 口径一致），这里把残留
running 分支转成 failed，供人工在剖面页发起重试，重试只重跑失败分支、
已完成分支留用。
"""
import logging
from sqlalchemy import text
from src.config.database import Base, engine, Session
# 导入全部模型，保证 metadata 完整
from src.models import identity, dataset, plan, trace, experiment  # noqa: F401


def ensure_schema():
    Base.metadata.create_all(engine)
    _reconcile()


def _reconcile():
    with engine.begin() as conn:
        # 老库可能缺 plans.version / experiments 新列；create_all 只建新表不补列
        cols = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='plans'")).fetchall()
        if cols and 'version' not in {r[0] for r in cols}:
            conn.execute(text(
                'ALTER TABLE plans ADD COLUMN version INTEGER NOT NULL DEFAULT 1'))
    with Session() as s:
        stuck = s.query(experiment.ExperimentBranch).filter_by(status='running').all()
        for b in stuck:
            b.status = 'failed'
            b.error = 'worker 进程中断，任务未自动重试；请在剖面页发起重试'
            exp = s.get(experiment.Experiment, b.experiment_id)
            if exp and exp.status == 'running':
                exp.status = 'failed'
                exp.error = f'分支 {b.node_key} 因 worker 中断失败，可重试'
        if stuck:
            logging.warning('reconciled %s interrupted experiment branches', len(stuck))
        # 自愈：极端崩溃窗口下可能出现分支全完成、实验却停在 running 未公开
        from src.services.experiments import _schedule
        open_exps = s.query(experiment.Experiment).filter_by(published=0).all()
        recoverable = []
        for e in open_exps:
            bs = s.query(experiment.ExperimentBranch).filter_by(
                experiment_id=e.id).all()
            if bs and all(b.status == 'completed' for b in bs):
                recoverable.append(e.id)
        s.commit()
    for eid in recoverable:
        _schedule(eid)
        logging.warning('re-published stalled experiment %s', eid)
