ROLES=('admin','operator','viewer')
STATUSES=('queued','running','completed','failed')
OPERATORS=('scan','filter','hash_join','group')
# 实验套：整体生命周期；分支（节点）在同一套状态机上运行，另加 blocked 表示等待上游
SUITE_STATUSES=('running','failed','completed','published')
BRANCH_STATUSES=('blocked','queued','running','completed','failed')
UPSTREAM_AGGREGATES=('count','sum','avg')
