export const ROLES={admin:'管理员',operator:'操作员',viewer:'观察员'};
export const STATUSES={queued:'等待执行',running:'执行中',completed:'已完成',failed:'执行失败'};
export const OPERATORS=['scan','filter','hash_join','group'];
// 实验套整体与分支状态：blocked 表示等待上游，published 表示收齐后一次性公开
export const SUITE_STATUSES={running:'编排运行中',failed:'存在失败分支',completed:'分支已收齐',published:'已公开结果'};
export const BRANCH_STATUSES={blocked:'等待上游',queued:'排队中',running:'执行中',completed:'已完成',failed:'执行失败'};
export const MEASURES={count:'计数 count',sum:'总和 sum',avg:'均值 avg'};
