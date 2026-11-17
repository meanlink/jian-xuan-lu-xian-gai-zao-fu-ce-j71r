import time, json, logging
from pathlib import Path
from sqlalchemy import select
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report, IdentityMap, IdentityRebuild
from src.services.business import analyze
from src.services.reports import deliver
from src.services.audit import record
from src.services.identity import apply_map, finalize_rebuild
logging.basicConfig(level=logging.INFO)
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        j.status='running'; db.commit()
        try:
            d=db.get(Dataset,j.dataset_id)
            records, originals, idmap = d.records, None, None
            if j.identity_map_id:
                idmap=db.get(IdentityMap,j.identity_map_id)
            if idmap:
                records, idinfo, originals = apply_map(d.records, idmap)
            result=analyze(records,j.params)
            if idmap:
                # 结果快照保留身份依据；明细同时展示稳定人员与原始工号、测时日期
                result['identity']=idinfo
                cols=result['table']['columns']
                result['table']['columns']=cols[:1]+[{'key':'work_id','label':'原始工号'},{'key':'measured_at','label':'测时日期'}]+cols[1:]
                for row in result['table']['rows']:
                    o=originals.get(row['operator']) or {}
                    row['work_id']=o.get('work_id','')
                    row['measured_at']=o.get('date') or ''
            json.dumps(result,allow_nan=False)
            j.result=result;j.status='completed';j.finished_at=time.time()
            record(db,'worker','job.completed',{'id':j.id,'identity_version':idinfo['version'] if idmap else None})
        except Exception as e:
            logging.exception('Analysis failed')
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'error':j.error})
        db.commit()
def run_rebuild(rebuild_id):
    # 已确认进度持久化在重建任务上；中断后由此恢复，重试不新增测时批次
    with Session() as db:
        r=db.get(IdentityRebuild,rebuild_id)
        if not r or r.state not in ('confirmed','rebuilding'):return
        try:
            r.state='rebuilding';db.commit()
            finalize_rebuild(db,r)
            record(db,'worker','identity.switched',{'id':r.id,'dataset':r.dataset_id,'map_version':r.map_version})
            db.commit()
        except Exception as e:
            logging.exception('Identity rebuild failed')
            db.rollback()
            r=db.get(IdentityRebuild,rebuild_id)
            r.state='failed';r.error=str(e)[:990];db.commit()
def tick():
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        rebuilds=list(db.scalars(select(IdentityRebuild.id).where(IdentityRebuild.state.in_(['confirmed','rebuilding'])).limit(2)))
    for rebuild_id in rebuilds:run_rebuild(rebuild_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()
def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
