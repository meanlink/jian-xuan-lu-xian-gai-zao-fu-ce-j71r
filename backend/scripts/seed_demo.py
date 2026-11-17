import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, Person, IdentityBinding, IdentityMap, IdentityRebuild
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum
# 演示身份簿：临时工裴岚换号（T-214→T-388，同人两号）；工号 T-107 复用（汪潮离职后由岑蔚启用，异人同工号）
IDENTITY_PERSONS = [
    ('裴岚', '临时工，11 月起换发新工号', [('东仓', 'T-214', '2026-09-01', '2026-10-31'), ('东仓', 'T-388', '2026-11-01', None)]),
    ('汪潮', '正式工，8 月底离职', [('东仓', 'T-107', '2026-05-01', '2026-08-31')]),
    ('岑蔚', '9 月入职，复用离职工号 T-107', [('东仓', 'T-107', '2026-09-01', None)]),
    ('简宁', '试点一组', [('东仓', 'T-120', '2026-09-01', None)]),
    ('陆逢', '试点三组', [('东仓', 'T-133', '2026-09-01', None)]),
    ('蒲航', '西仓试点', [('西仓', 'T-201', '2026-09-01', None)]),
]
IDENTITY_ROWS = [
    {'operator': 'T-214', 'warehouse': '东仓', 'date': '2026-10-20', 'team': '一组', 'before': 428.5, 'after': 401.2},
    {'operator': 'T-388', 'warehouse': '东仓', 'date': '2026-11-05', 'team': '一组', 'before': 421.0, 'after': 392.8},
    {'operator': 'T-107', 'warehouse': '东仓', 'date': '2026-06-15', 'team': '二组', 'before': 455.3, 'after': 440.1},
    {'operator': 'T-107', 'warehouse': '东仓', 'date': '2026-10-02', 'team': '二组', 'before': 402.6, 'after': 388.4},
    {'operator': 'T-120', 'warehouse': '东仓', 'date': '2026-10-11', 'team': '三组', 'before': 398.2, 'after': 381.5},
    {'operator': 'T-133', 'warehouse': '东仓', 'date': '2026-10-12', 'team': '三组', 'before': 410.9, 'after': 394.0},
    {'operator': 'T-201', 'warehouse': '西仓', 'date': '2026-10-09', 'team': '四组', 'before': 436.4, 'after': 429.7},
    {'operator': 'T-950', 'warehouse': '东仓', 'date': '2026-10-15', 'team': '四组', 'before': 444.8, 'after': 431.2},
    {'operator': 'OP-901', 'team': '一组', 'before': 418.3, 'after': 405.6},
    {'operator': 'OP-902', 'team': '二组', 'before': 409.7, 'after': 398.9},
]
def seed_identity(db):
    persons = {}
    for name, note, bindings in IDENTITY_PERSONS:
        p = db.scalar(select(Person).where(Person.name == name))
        if not p:
            p = Person(name=name, note=note, status='active', created_at=time.time())
            db.add(p); db.flush()
        persons[name] = p
        for warehouse, work_id, valid_from, valid_to in bindings:
            if not db.scalar(select(IdentityBinding).where(IdentityBinding.person_id == p.id, IdentityBinding.work_id == work_id, IdentityBinding.valid_from == valid_from)):
                db.add(IdentityBinding(person_id=p.id, warehouse=warehouse, work_id=work_id, valid_from=valid_from, valid_to=valid_to, state='active', created_at=time.time()))
    name = '11 月复测 · 换号与工号复用样本'
    if not db.scalar(select(Dataset).where(Dataset.name == name)):
        db.add(Dataset(name=name, source='BL_route_retest-202611.csv', records=IDENTITY_ROWS, checksum=checksum(IDENTITY_ROWS), created_at=time.time()))
        db.flush()
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        seed_identity(db)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,Person,IdentityBinding,IdentityMap,IdentityRebuild]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
