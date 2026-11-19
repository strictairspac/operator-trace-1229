import {datasets,plans,traces,experiments} from '../api/business.js';
export const store={datasets:[],plans:[],traces:[],experiments:[],user:null};
export async function refresh(){
 [store.datasets,store.plans,store.traces,store.experiments]=await Promise.all([
  datasets.list(),plans.list(),traces.list(),experiments.list()]);
}
