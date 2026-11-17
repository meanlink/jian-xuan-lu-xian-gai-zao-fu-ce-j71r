from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Person, IdentityBinding, IdentityRebuild, Dataset
from src.schemas.identity import PersonInput, BindingInput, MergeInput, ConfirmInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import identity
from src.services.audit import record
from src.utils.serialization import person_dict, rebuild_dict
router = APIRouter(prefix='/identity')

@router.get('/persons')
def persons(db=Depends(get_db), u=Depends(current_user)):
    all_p = list(db.scalars(select(Person).order_by(Person.id)))
    by_pid = {}
    for b in db.scalars(select(IdentityBinding).order_by(IdentityBinding.valid_from, IdentityBinding.id)):
        by_pid.setdefault(b.person_id, []).append(b)
    names = {p.id: p.name for p in all_p}
    return [person_dict(p, by_pid.get(p.id, []), names) for p in all_p]

@router.post('/persons', status_code=201)
def create_person(data: PersonInput, db=Depends(get_db), u=Depends(can_write)):
    p = identity.create_person(db, data)
    record(db, u.email, 'person.create', {'id': p.id, 'name': p.name})
    db.commit()
    return {'id': p.id, 'name': p.name}

@router.post('/persons/{id}/merge')
def merge(id: int, data: MergeInput, db=Depends(get_db), u=Depends(admin_only)):
    p = identity.merge_person(db, id, data.into_id)
    record(db, u.email, 'person.merge', {'id': p.id, 'into': p.merged_into})
    db.commit()
    return {'id': p.id, 'status': p.status, 'merged_into': p.merged_into}

@router.post('/persons/{id}/split')
def split(id: int, db=Depends(get_db), u=Depends(admin_only)):
    p = identity.split_person(db, id)
    record(db, u.email, 'person.split', {'id': p.id})
    db.commit()
    return {'id': p.id, 'status': p.status}

@router.post('/bindings', status_code=201)
def create_binding(data: BindingInput, db=Depends(get_db), u=Depends(can_write)):
    b = identity.add_binding(db, data, u.email)
    record(db, u.email, 'binding.create', {'id': b.id, 'person_id': b.person_id, 'work_id': b.work_id, 'warehouse': b.warehouse})
    db.commit()
    return {'id': b.id}

@router.post('/bindings/{id}/revoke')
def revoke_binding(id: int, db=Depends(get_db), u=Depends(can_write)):
    b = identity.revoke_binding(db, id)
    record(db, u.email, 'binding.revoke', {'id': b.id, 'work_id': b.work_id, 'warehouse': b.warehouse})
    db.commit()
    return {'id': b.id, 'state': b.state}

@router.get('/rebuilds')
def rebuilds(dataset_id: int | None = None, db=Depends(get_db), u=Depends(current_user)):
    q = select(IdentityRebuild).order_by(IdentityRebuild.id.desc()).limit(50)
    if dataset_id:
        q = select(IdentityRebuild).where(IdentityRebuild.dataset_id == dataset_id).order_by(IdentityRebuild.id.desc()).limit(50)
    names = {d.id: d.name for d in db.scalars(select(Dataset))}
    return [{**rebuild_dict(r), 'dataset_name': names.get(r.dataset_id, '')} for r in db.scalars(q)]

@router.post('/datasets/{dataset_id}/preview', status_code=201)
def preview(dataset_id: int, db=Depends(get_db), u=Depends(can_write)):
    d = db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, '数据批次不存在')
    r, created = identity.preview(db, d)
    if created:
        record(db, u.email, 'identity.preview', {'dataset': d.id, 'rebuild': r.id, 'conflicts': len(r.preview.get('conflicts', []))})
    db.commit()
    return rebuild_dict(r)

@router.post('/rebuilds/{rebuild_id}/confirm')
def confirm(rebuild_id: int, data: ConfirmInput, db=Depends(get_db), u=Depends(admin_only)):
    r = db.get(IdentityRebuild, rebuild_id)
    if not r:
        raise HTTPException(404, '身份重建任务不存在')
    r, changed = identity.confirm(db, r, data.resolutions)
    if changed:
        record(db, u.email, 'identity.confirm', {'rebuild': r.id, 'dataset': r.dataset_id, 'excluded': len(r.plan.get('excluded', []))})
    db.commit()
    return rebuild_dict(r)
