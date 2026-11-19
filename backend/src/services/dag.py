"""实验套 DAG 校验：引用完整性、重复键、成环检测与拓扑分层。

纯标准库实现，不依赖数据库，便于独立测试。
"""
from src.constants.enums import UPSTREAM_AGGREGATES


class GraphError(ValueError):
    """可恢复的计划编排错误，对应 HTTP 400。"""


def validate_definition(nodes):
    """校验分支定义并返回规范化后的节点列表；任何结构问题抛 GraphError。

    节点字段：node_key / plan_id / depends_on / measure
    规则：至少一个节点；键唯一；依赖必须指向已声明节点且不能依赖自己；依赖成环拒收。
    """
    if not isinstance(nodes, list) or not nodes:
        raise GraphError('实验套至少包含一个计划分支')
    seen = set()
    normalized = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GraphError(f'第{i + 1}个分支定义格式错误')
        key = node.get('node_key')
        if not isinstance(key, str) or not key.strip() or len(key) > 80:
            raise GraphError(f'第{i + 1}个分支缺少有效的 node_key')
        if key in seen:
            raise GraphError(f'分支节点键重复：{key}')
        plan_id = node.get('plan_id')
        if not isinstance(plan_id, int) or isinstance(plan_id, bool) or plan_id < 1:
            raise GraphError(f'分支 {key} 的 plan_id 无效')
        deps = node.get('depends_on', [])
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            raise GraphError(f'分支 {key} 的 depends_on 必须是节点键数组')
        if key in deps:
            raise GraphError(f'分支 {key} 不能依赖自身')
        if len(deps) != len(set(deps)):
            raise GraphError(f'分支 {key} 的依赖存在重复项')
        measure = node.get('measure', 'avg')
        if measure not in UPSTREAM_AGGREGATES:
            raise GraphError(f'分支 {key} 的 measure 仅允许 count/sum/avg')
        seen.add(key)
        normalized.append({'node_key': key, 'plan_id': plan_id,
                           'depends_on': list(deps), 'measure': measure})
    # 依赖必须指向已声明的节点
    for node in normalized:
        for dep in node['depends_on']:
            if dep not in seen:
                raise GraphError(f"分支 {node['node_key']} 引用了不存在的上游 {dep}")
    detect_cycle(normalized)
    return normalized


def detect_cycle(nodes):
    """Kahn 拓扑排序；剩余节点即处于环中。"""
    indegree = {n['node_key']: len(n['depends_on']) for n in nodes}
    children = {n['node_key']: [] for n in nodes}
    for n in nodes:
        for dep in n['depends_on']:
            children[dep].append(n['node_key'])
    ready = [k for k, d in indegree.items() if d == 0]
    visited = 0
    while ready:
        k = ready.pop()
        visited += 1
        for child in children[k]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(nodes):
        stuck = sorted(k for k, d in indegree.items() if d > 0)
        raise GraphError('计划依赖成环，实验套已拒收；成环节点：' + '、'.join(stuck))


def topological_layers(nodes):
    """返回分层列表；同层节点互不依赖，可并发执行。"""
    by_key = {n['node_key']: n for n in nodes}
    layers, remaining = [], set(by_key)
    while remaining:
        layer = sorted(k for k in remaining
                       if all(d not in remaining for d in by_key[k]['depends_on']))
        if not layer:  # 理论上 validate 已挡环，这里兜底
            raise GraphError('计划依赖成环，实验套已拒收')
        layers.append(layer)
        remaining.difference_update(layer)
    return layers
