import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const identity={
 persons:()=>api('/identity/persons'),
 createPerson:data=>api('/identity/persons',{method:'POST',body:JSON.stringify(data)}),
 merge:(id,into_id)=>api('/identity/persons/'+id+'/merge',{method:'POST',body:JSON.stringify({into_id})}),
 split:id=>api('/identity/persons/'+id+'/split',{method:'POST'}),
 createBinding:data=>api('/identity/bindings',{method:'POST',body:JSON.stringify(data)}),
 revoke:id=>api('/identity/bindings/'+id+'/revoke',{method:'POST'}),
 rebuilds:datasetId=>api('/identity/rebuilds'+(datasetId?'?dataset_id='+datasetId:'')),
 preview:datasetId=>api('/identity/datasets/'+datasetId+'/preview',{method:'POST'}),
 confirm:(id,data)=>api('/identity/rebuilds/'+id+'/confirm',{method:'POST',body:JSON.stringify(data)})
};
