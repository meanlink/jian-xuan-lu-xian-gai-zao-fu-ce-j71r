/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,identity_version:number|null}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,identity_map_id:number|null}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,person_id:number,warehouse:string,work_id:string,valid_from:string,valid_to:string|null,state:string}} IdentityBinding */
/** @typedef {{id:number,name:string,note:string,status:string,merged_into:number|null,merged_into_name:string|null,bindings:IdentityBinding[]}} Person */
/** @typedef {{id:number,dataset_id:number,state:string,preview:Object,resolutions:Object,progress:number,total:number,map_version:number|null,error:string}} IdentityRebuild */
export {};
