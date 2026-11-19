/** @typedef {{id:number,name:string,sensors:object[],readings:object[]}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,steps:object[],version:number}} Plan */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed',result:object|null}} Trace */
/** @typedef {{node_key:string,plan_id:number,plan_version:number,depends_on:string[],measure:'count'|'sum'|'avg',status:'blocked'|'queued'|'running'|'completed'|'failed',attempts:number,result:object|null,error:string|null}} ExperimentBranch */
/** @typedef {{id:number,name:string,dataset_id:number,status:'running'|'failed'|'completed'|'published',published:0|1,definition:object[],result:object|null,error:string|null}} Experiment */
export {};
