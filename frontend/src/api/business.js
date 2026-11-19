import {api,post} from './client.js';
export const datasets={list:()=>api('/datasets'),save:(d,id)=>post('/datasets'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const plans={list:()=>api('/plans'),save:(d,id)=>post('/plans'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const traces={list:()=>api('/traces'),run:d=>post('/traces',d),detail:id=>api('/traces/'+id)};
export const experiments={
 list:()=>api('/experiments'),
 run:d=>post('/experiments',d),
 detail:id=>api('/experiments/'+id),
 branches:id=>api('/experiments/'+id+'/branches'),
 retry:id=>post('/experiments/'+id+'/retry',{},'POST'),
 exportUrl:id=>'/api/experiments/'+id+'/export'
};
