# Schema v1
SQLAlchemy metadata creates users, audits, datasets, plans, traces. Natural names are unique; foreign keys reference parent entities. Each trace stores immutable JSON input snapshots. PostgreSQL persists metadata and teaching datasets; the bounded Python operators execute the plan.

## v2 增补：实验套 DAG 编排
- `plans.version`：每次新建为 1，每次更新自增。实验套在受理时冻结 `plan_version` 与完整计划快照，计划后续修改不影响在途实验（原套仍用受理时版本）。老库缺列时 `src/bootstrap.py` 以 `ALTER TABLE ... ADD COLUMN version INTEGER NOT NULL DEFAULT 1` 幂等补齐。
- `experiments`：一次实验套，含 `status(running/failed/completed/published)`、受理时 `definition` 与 `snapshot`、`published` 标志、`result` 与 `published_at`。未公开前 result/snapshot 不对外返回。
- `experiment_branches`：DAG 节点，含 `node_key`、`plan_id/plan_version`、`depends_on`、`measure(count/sum/avg)`、`status(blocked/queued/running/completed/failed)`、分支 `result/error`、`attempts`，`(experiment_id,node_key)` 唯一。
- 建表仍由 `Base.metadata.create_all` 幂等完成；worker 崩溃残留的 running 分支在启动 `bootstrap.ensure_schema()` 中转为 failed，供人工重试。
