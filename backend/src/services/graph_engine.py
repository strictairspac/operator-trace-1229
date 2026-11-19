"""实验套分支执行：上游分组产出 → 下游采样表 → 受限算子执行。

设计要点：
- 上游按传感器分组，输出行的 count/sum/avg 被当作下游采样值；
- 同值行照算：每个上游输出行都生成一条独立 reading，不做去重或合并；
- 多上游的采样表按顺序拼接，下游等自己的全部上游齐了才开跑；
- 执行仍复用受限 DSL 的 operators.execute，禁止 eval/任意 SQL 的约束不变。
"""
from src.services.operators import execute
from src.services.dag import GraphError


def _final_group(steps):
    groups = [s for s in steps if s.get('op') == 'group']
    if not groups:
        raise GraphError('分支计划必须包含 group 算子，以 count/sum/avg 产出采样值')
    return groups[-1]


def validate_branch_plan(steps):
    """分支计划校验：必须有按 sensor_id 的分组聚合，产出 count/sum/avg 之一。"""
    group = _final_group(steps)
    if 'sensor_id' not in group['keys']:
        raise GraphError('分支分组键必须包含 sensor_id，下游才能按传感器继续采样')
    if group['aggregate'] not in ('count', 'sum', 'avg'):
        raise GraphError('分支仅支持 value 的 count/sum/avg 聚合作为采样值')
    if group['measure'] != 'value':
        raise GraphError('分支仅支持对 value 聚合')
    return group['aggregate']


def readings_from_upstream(node_key, result, measure):
    """把一个上游分支的最终输出转成 readings；同值输出行各自成行，照算不去重。"""
    readings = []
    for idx, row in enumerate(result['output']):
        if 'sensor_id' not in row:
            raise GraphError(f'上游分支 {node_key} 的输出缺少 sensor_id，无法下游采样')
        if measure not in row:
            raise GraphError(
                f"上游分支 {node_key} 的输出没有 {measure} 列；请让上游按该聚合产出")
        value = row[measure]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise GraphError(f'上游分支 {node_key} 的 {measure} 不是数值采样')
        readings.append({
            'sensor_id': int(row['sensor_id']),
            'value': float(value),
            # recorded_at 仅用于满足 readings 字段约束，并标明采样来源行
            'recorded_at': f'{node_key}:{idx}',
        })
    return readings


def build_downstream_dataset(dataset_snapshot, upstream_inputs):
    """upstream_inputs: [(node_key, result, measure), ...] 全部上游齐活后调用。"""
    readings = []
    for node_key, result, measure in upstream_inputs:
        readings.extend(readings_from_upstream(node_key, result, measure))
    if len(readings) > 2000:
        raise GraphError('合成采样超过2000条上限，请减少上游分组输出')
    return {'id': dataset_snapshot['id'], 'name': dataset_snapshot['name'],
            'sensors': dataset_snapshot['sensors'], 'readings': readings}


def execute_branch(dataset_snapshot, plan_snapshot, upstream_inputs=None):
    """执行单个分支。根分支读原始 readings；非根分支读上游合成采样。"""
    steps = plan_snapshot['steps']
    if upstream_inputs:
        dataset = build_downstream_dataset(dataset_snapshot, upstream_inputs)
    else:
        dataset = dataset_snapshot
    return execute(dataset, steps)
