import {store} from '../stores/business.js';
import {esc,json} from '../utils/html.js';
import {table} from '../components/common/table.js';
import {suiteStatus,branchStatus} from '../components/common/status.js';
import {MEASURES} from '../constants/enums.js';
import {experiments as experimentApi} from '../api/business.js';
import {downloadUrl} from '../api/client.js';

// 表单里的分支草稿，纯前端状态
let draft=[{node_key:'upstream',plan_id:'',depends_on:[],measure:'avg'}];
let activeId=null;
let activeBranches=[];

export function getDraft(){return draft;}
export function getActiveId(){return activeId;}
export function setActive(id){activeId=id;activeBranches=[];}
export function setActiveBranches(rows){activeBranches=rows;}

export function experimentsPage(){
 const rows=store.experiments;
 return `<div class="split"><section>
  <h2>把相互依赖的计划组成一套实验</h2>
  <p>上游按传感器分组，count/sum/avg 作为下游采样值；依赖成环会被拒收，独立分支并发执行。</p>
  <form id="experiment-form">
   <label>实验套名称<input name="name" required placeholder="lab-20261119-dag"></label>
   <label>输入数据集<select name="dataset_id">${store.datasets.map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join('')}</select></label>
   <div id="branch-draft">${draft.map((b,i)=>branchRow(b,i)).join('')}</div>
   <button type="button" class="quiet" id="add-branch">＋ 添加分支</button>
   <small>分支计划必须含 sensor_id 分组；下游 measure 要与上游聚合一致。受理后计划再改不影响本套。</small>
   <button type="submit">受理并发起实验 →</button>
  </form>
 </section><section>
  <h2>实验剖面 <em>${rows.length}</em></h2>
  ${table(['实验套 / 受理时间','整体状态','分支进度','动作'],rows.map(e=>[
   `<b>${esc(e.name)}</b><small>#${e.id} · 数据集 #${e.dataset_id}</small><small>${esc(e.created_at||'')}</small>`,
   suiteStatus(e.status,e.published),
   progressCell(e),
   `<button class="quiet" data-watch="${e.id}">查看分支进度 →</button>`
  ].map(c=>c)))}
  <div id="branch-panel" ${activeId?'':'hidden'}>${activeId?branchPanel():''}</div>
  <aside class="note">结果在全部分支收齐并公开前不展示明细，只给进度；公开后可导出整套 JSON。失败重试会留用已完成的分支，只补跑失败分支，且不会重复发布。</aside>
 </section></div>`;
}

function branchRow(b,i){
 return `<div class="branch-row" data-i="${i}">
  <label>节点键<input data-k="node_key" value="${esc(b.node_key)}" placeholder="upstream"></label>
  <label>计划<select data-k="plan_id">${store.plans.map(p=>`<option value="${p.id}" ${String(p.id)===String(b.plan_id)?'selected':''}>${esc(p.name)} v${p.version||1}</option>`).join('')}</select></label>
  <label>采样口径<select data-k="measure">${Object.entries(MEASURES).map(([k,v])=>`<option value="${k}" ${b.measure===k?'selected':''}>${esc(v)}</option>`).join('')}</select></label>
  <label>依赖上游（多选）<select multiple data-k="depends_on" size="3">${draft.map((o,j)=>j===i?'':`<option value="${esc(o.node_key)}" ${b.depends_on.includes(o.node_key)?'selected':''}>${esc(o.node_key)}</option>`).join('')}</select></label>
  <button type="button" class="quiet" data-remove-branch="${i}" ${draft.length===1?'disabled':''}>删除</button>
 </div>`;
}

function progressCell(e){
 const def=e.definition||[];
 const total=def.length;
 // 未公开时没有分支明细，只能展示定义里的节点数与整体状态
 return `<span class="muted">${total} 个分支</span>`;
}

function branchPanel(){
 const e=store.experiments.find(x=>x.id===Number(activeId));
 if(!e)return '';
 return `<div class="branch-panel">
  <h3>分支进度 · ${esc(e.name)} ${suiteStatus(e.status,e.published)}</h3>
  ${e.status==='failed'?`<button data-retry="${e.id}">重试失败分支（留用已完成）</button>`:''}
  ${e.published?`<button class="quiet" data-export-exp="${e.id}">导出整套结果 ↓</button>`:'<p class="muted">结果收齐公开后可导出，当前仅展示进度。</p>'}
  ${table(['节点','计划版本','依赖','口径','状态','尝试','输出行'],(activeBranches.length?activeBranches:(e.definition||[]).map(d=>({...d,status:'blocked',attempts:0}))).map(b=>[
   `<b>${esc(b.node_key)}</b>`,
   `v${b.plan_version??'?'}`,
   (b.depends_on||[]).map(esc).join('、')||'— 根分支',
   esc(b.measure||''),
   branchStatus(b.status),
   String(b.attempts??0),
   b.result?String(b.result.output_rows??''):(b.status==='completed'?'':'—')
  ]))}
  ${e.published&&e.result?`<details open><summary>公开结果（仅公开后可见）</summary><pre>${json(e.result)}</pre></details>`:''}
  ${e.error?`<div class="feedback error">${esc(e.error)}</div>`:''}
 </div>`;
}

export function bindExperimentPage(){
 const form=document.getElementById('experiment-form');
 document.getElementById('add-branch')?.addEventListener('click',()=>{
  draft.push({node_key:'branch-'+(draft.length+1),plan_id:store.plans[0]?.id||'',depends_on:[],measure:'avg'});
  rerenderDraft();
 });
 bindDraftRows();
 form?.addEventListener('submit',async e=>{
  e.preventDefault();
  const fd=new FormData(form);
  const payload={name:fd.get('name'),dataset_id:Number(fd.get('dataset_id')),
   branches:draft.map(b=>({node_key:b.node_key,plan_id:Number(b.plan_id),depends_on:b.depends_on,measure:b.measure}))};
  try{
   const created=await experimentApi.run(payload);
   draft=[{node_key:'upstream',plan_id:store.plans[0]?.id||'',depends_on:[],measure:'avg'}];
   activeId=created.id;activeBranches=[];
   window.__refreshAndRender?.();
  }catch(err){window.__feedback?.(err.message,true);}
 });
 document.querySelectorAll('[data-watch]').forEach(b=>b.addEventListener('click',async()=>{
  activeId=Number(b.dataset.watch);
  try{activeBranches=await experimentApi.branches(activeId);}catch{activeBranches=[];}
  window.__refreshAndRender?.();
 }));
 document.querySelectorAll('[data-retry]').forEach(b=>b.addEventListener('click',async()=>{
  try{await experimentApi.retry(Number(b.dataset.retry));window.__feedback?.('已重排队失败分支，已完成分支留用。');window.__refreshAndRender?.();}
  catch(err){window.__feedback?.(err.message,true);}
 }));
 document.querySelectorAll('[data-export-exp]').forEach(b=>b.addEventListener('click',async()=>{
  const id=Number(b.dataset.exportExp);
  try{await downloadUrl(experimentApi.exportUrl(id),'experiment-'+id+'.json');}
  catch(err){window.__feedback?.(err.message,true);}
 }));
}

function bindDraftRows(){
 document.querySelectorAll('[data-remove-branch]').forEach(btn=>btn.addEventListener('click',()=>{
  draft.splice(Number(btn.dataset.removeBranch),1);rerenderDraft();
 }));
 document.querySelectorAll('#branch-draft .branch-row').forEach(row=>{
  const i=Number(row.dataset.i);
  row.querySelectorAll('[data-k]').forEach(el=>el.addEventListener('change',()=>{
   const k=el.dataset.k;
   draft[i][k]=k==='depends_on'?Array.from(el.selectedOptions).map(o=>o.value):(k==='plan_id'?Number(el.value):el.value);
  }));
 });
}

function rerenderDraft(){
 const el=document.getElementById('branch-draft');
 if(el)el.innerHTML=draft.map((b,i)=>branchRow(b,i)).join('');
 // 只重绑草稿行，避免给常驻 form 重复挂 submit
 bindDraftRows();
}
