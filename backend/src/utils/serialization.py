import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'identity_version':d.identity_version, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','identity_map_id','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def binding_dict(b):
    return {k:getattr(b,k) for k in ['id','person_id','warehouse','work_id','valid_from','valid_to','state','created_at']}
def person_dict(p, bindings, names):
    return {'id':p.id, 'name':p.name, 'note':p.note, 'status':p.status, 'merged_into':p.merged_into,
            'merged_into_name':names.get(p.merged_into), 'created_at':p.created_at,
            'bindings':[binding_dict(b) for b in bindings]}
def rebuild_dict(r):
    return {k:getattr(r,k) for k in ['id','dataset_id','fingerprint','state','preview','resolutions','progress','total','map_id','map_version','error','created_at','confirmed_at','finished_at']}
