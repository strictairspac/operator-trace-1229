import {STATUSES,SUITE_STATUSES,BRANCH_STATUSES} from '../../constants/enums.js';
export const status=s=>`<span class="status ${s}">${STATUSES[s]||s}</span>`;
export const suiteStatus=(s,published)=>{
 const cls=published?'published':s;
 const label=published?SUITE_STATUSES.published:(SUITE_STATUSES[s]||s);
 return `<span class="status suite ${cls}">${label}</span>`;
};
export const branchStatus=s=>`<span class="status branch ${s}">${BRANCH_STATUSES[s]||s}</span>`;
