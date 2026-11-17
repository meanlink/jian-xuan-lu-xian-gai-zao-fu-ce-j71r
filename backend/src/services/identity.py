"""人员身份簿：仓别+工号+生效期 → 稳定人员。

测时记录（数据批次）保持不可变，始终保留发生日期与原始工号；
身份依据（IdentityMap）按批次版本化，确认后整批重建并一次性切换，
旧版本永久保留，旧分析保持原值。
"""
import re
import time
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, func
from src.config.database import Session
from src.models import Person, IdentityBinding, IdentityMap, IdentityRebuild, Dataset
from src.services.audit import record
from src.utils.serialization import checksum

OPEN_END = '9999-12-31'
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
CHOICES = ('first', 'last', 'none')  # 配对冲突处理：保留最早行 / 保留最新行 / 全部排除


def _day(value, label):
    s = str(value or '').strip()
    if not DATE_RE.match(s):
        raise HTTPException(422, f'{label}须为 YYYY-MM-DD 格式')
    try:
        date.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, f'{label}不是有效日期')
    return s


def effective(persons, pid):
    """沿归并链找到当前有效人员；循环防御。"""
    seen = set()
    while pid in persons and persons[pid].status == 'merged' and persons[pid].merged_into:
        if pid in seen:
            break
        seen.add(pid)
        pid = persons[pid].merged_into
    return pid


def _persons(db):
    return {p.id: p for p in db.scalars(select(Person))}


def _overlap_rows(bindings, warehouse, work_id, valid_from, valid_to, ignore_id=None):
    """同一仓别工号在生效期上重叠的有效归属。"""
    end = valid_to or OPEN_END
    rows = []
    for b in bindings:
        if b.id == ignore_id or b.state != 'active':
            continue
        if b.warehouse != warehouse or b.work_id != work_id:
            continue
        if b.valid_from <= end and valid_from <= (b.valid_to or OPEN_END):
            rows.append(b)
    return rows


def _audit_side(actor, action, detail):
    """冲突等失败路径也要留痕；独立会话，不随请求回滚。"""
    with Session() as side:
        record(side, actor, action, detail)
        side.commit()


def create_person(db, data):
    name = data.name.strip()
    if db.scalar(select(Person).where(Person.name == name)):
        raise HTTPException(409, '同名人员已登记，请通过归并处理重复身份')
    p = Person(name=name, note=data.note.strip(), status='active', created_at=time.time())
    db.add(p)
    db.flush()
    return p


def add_binding(db, data, actor):
    person = db.get(Person, data.person_id)
    if not person:
        raise HTTPException(404, '稳定人员不存在')
    if person.status != 'active':
        raise HTTPException(409, '已归并人员不能登记新归属，请先拆分归并或改登记到归并目标')
    warehouse, work_id = data.warehouse.strip(), data.work_id.strip()
    if not warehouse or not work_id:
        raise HTTPException(422, '仓别与工号不能为空')
    valid_from = _day(data.valid_from, '生效开始')
    valid_to = _day(data.valid_to, '生效结束') if data.valid_to and data.valid_to.strip() else None
    if valid_to and valid_to < valid_from:
        raise HTTPException(422, '生效结束不能早于生效开始')
    bindings = list(db.scalars(select(IdentityBinding)))
    persons = _persons(db)
    for other in _overlap_rows(bindings, warehouse, work_id, valid_from, valid_to):
        holder = persons.get(effective(persons, other.person_id))
        detail = {'work_id': work_id, 'warehouse': warehouse, 'valid_from': valid_from, 'valid_to': valid_to,
                  'held_by': holder.name if holder else other.person_id}
        if effective(persons, other.person_id) != person.id:
            _audit_side(actor, 'binding.conflict', detail)
            raise HTTPException(409, f'重叠归属阻止启用：{work_id}@{warehouse} 在 {max(valid_from, other.valid_from)}~{min(valid_to or OPEN_END, other.valid_to or OPEN_END)} 已归属 {detail["held_by"]}')
        _audit_side(actor, 'binding.conflict', {**detail, 'duplicate': True})
        raise HTTPException(409, '该仓别工号在此时段已归属同一人员，请勿重复登记')
    b = IdentityBinding(person_id=person.id, warehouse=warehouse, work_id=work_id,
                        valid_from=valid_from, valid_to=valid_to, state='active', created_at=time.time())
    db.add(b)
    db.flush()
    return b


def revoke_binding(db, binding_id):
    b = db.get(IdentityBinding, binding_id)
    if not b:
        raise HTTPException(404, '归属记录不存在')
    if b.state != 'active':
        raise HTTPException(409, '该归属已停用')
    b.state = 'revoked'
    return b


def merge_person(db, person_id, into_id):
    p, t = db.get(Person, person_id), db.get(Person, into_id)
    if not p or not t:
        raise HTTPException(404, '稳定人员不存在')
    if p.id == t.id:
        raise HTTPException(422, '不能归并到自身')
    if p.status != 'active':
        raise HTTPException(409, '该人员已处于归并状态，如需调整请先拆分')
    if t.status != 'active':
        raise HTTPException(409, '归并目标须为在册人员')
    p.status, p.merged_into = 'merged', t.id
    return p


def split_person(db, person_id):
    """拆分误归并：恢复人员在册状态。测时按原始记录重新归属，不是改展示名。"""
    p = db.get(Person, person_id)
    if not p:
        raise HTTPException(404, '稳定人员不存在')
    if p.status != 'merged':
        raise HTTPException(409, '仅已归并人员可以拆分')
    persons = _persons(db)
    bindings = list(db.scalars(select(IdentityBinding)))
    mine = [b for b in bindings if b.person_id == p.id and b.state == 'active']
    for b in mine:
        for other in _overlap_rows(bindings, b.warehouse, b.work_id, b.valid_from, b.valid_to, ignore_id=b.id):
            if effective(persons, other.person_id) == p.id:
                continue
            holder = persons.get(effective(persons, other.person_id))
            raise HTTPException(409, f'拆分后 {b.work_id}@{b.warehouse} 在重叠生效期内将与 {holder.name if holder else "?"} 归属冲突，请先调整归属记录')
    p.status, p.merged_into = 'active', None
    return p


def registry_fingerprint(db, dataset):
    """批次指纹 + 身份簿当前状态；任何归属变化都会使旧预览过期。"""
    persons = _persons(db)
    bindings = list(db.scalars(select(IdentityBinding).where(IdentityBinding.state == 'active')))
    state = {
        'merges': sorted([p.id, p.merged_into] for p in persons.values() if p.merged_into),
        'bindings': sorted([b.warehouse, b.work_id, b.valid_from, b.valid_to or '', effective(persons, b.person_id)] for b in bindings),
    }
    return checksum({'dataset': dataset.checksum, 'registry': state})


def _resolve(records, persons, bindings):
    """逐行归属：返回 assignments、分组与统计。不改变原始记录。"""
    by_key = {}
    for b in bindings:
        if b.state == 'active':
            by_key.setdefault((b.warehouse, b.work_id), []).append(b)
    for rows in by_key.values():
        rows.sort(key=lambda b: (b.valid_from, b.id))
    eff_cache = {}
    def eff(pid):
        if pid not in eff_cache:
            eff_cache[pid] = effective(persons, pid)
        return eff_cache[pid]
    assignments, groups = {}, {}
    resolved = unresolved = legacy = 0
    for i, rec in enumerate(records):
        wid = str(rec.get('operator', ''))
        wh, dt = rec.get('warehouse'), rec.get('date')
        a = None
        if wh and dt:
            cand = [b for b in by_key.get((wh, wid), []) if b.valid_from <= dt <= (b.valid_to or OPEN_END)]
            if cand:
                pid = eff(cand[-1].person_id)
                holder = persons.get(pid)
                a = {'person': pid, 'label': holder.name if holder else f'人员{pid}'}
                resolved += 1
            else:
                unresolved += 1
        else:
            legacy += 1
        if a is None:
            a = {'raw': wid}
        assignments[str(i)] = a
        key = f"person:{a['person']}" if 'person' in a else f"raw:{a['raw']}"
        groups.setdefault(key, []).append(i)
    labels, used = {}, set()
    for key, idxs in groups.items():
        a = assignments[str(idxs[0])]
        base = a.get('label') or a.get('raw')
        label, n = base, 2
        while label in used:
            label, n = f'{base}({n})', n + 1
        used.add(label)
        labels[key] = label
        if 'person' in a:
            for i in idxs:
                assignments[str(i)]['label'] = label
    return assignments, groups, labels, {'resolved': resolved, 'unresolved': unresolved, 'legacy': legacy}


def compute_preview(db, dataset, fingerprint):
    persons = _persons(db)
    bindings = list(db.scalars(select(IdentityBinding)))
    assignments, groups, labels, stats = _resolve(dataset.records, persons, bindings)
    current = db.get(IdentityMap, dataset.active_map_id) if dataset.active_map_id else None
    current_excluded = set(current.excluded or []) if current else set()
    affected = {}
    for i, rec in enumerate(dataset.records):
        a = assignments[str(i)]
        new_label = a.get('label') or a.get('raw')
        if current:
            old = current.assignments.get(str(i)) or {}
            old_label = old.get('label') or old.get('raw') or str(rec.get('operator', ''))
            changed = old_label != new_label or i in current_excluded
        else:
            old_label = str(rec.get('operator', ''))
            changed = old_label != new_label
        if changed:
            e = affected.setdefault(new_label, {'label': new_label, 'from': set(), 'records': 0})
            e['from'].add(old_label)
            e['records'] += 1
    affected_rows = sorted(({'label': k, 'from': sorted(v['from']), 'records': v['records']} for k, v in affected.items()), key=lambda x: x['label'])
    conflicts = []
    for key, idxs in groups.items():
        if len(idxs) > 1:
            conflicts.append({'key': key, 'label': labels[key], 'records': [
                {'index': i, 'operator': str(dataset.records[i].get('operator', '')),
                 'warehouse': dataset.records[i].get('warehouse') or '', 'date': dataset.records[i].get('date') or '',
                 'before': dataset.records[i].get('before'), 'after': dataset.records[i].get('after')} for i in idxs]})
    preview = {'dataset_id': dataset.id, 'fingerprint': fingerprint, 'total': len(dataset.records), **stats,
               'affected': affected_rows[:100], 'affected_total': len(affected_rows), 'conflicts': conflicts,
               'generated_at': time.time()}
    return preview, {'assignments': assignments}


def preview(db, dataset):
    """幂等预览：身份簿未变时返回已有预览，不新增重建任务。"""
    fp = registry_fingerprint(db, dataset)
    existing = db.scalar(select(IdentityRebuild).where(
        IdentityRebuild.dataset_id == dataset.id, IdentityRebuild.fingerprint == fp,
        IdentityRebuild.state == 'previewed'))
    if existing:
        return existing, False
    body, plan = compute_preview(db, dataset, fp)
    for old in db.scalars(select(IdentityRebuild).where(IdentityRebuild.dataset_id == dataset.id, IdentityRebuild.state == 'previewed')):
        old.state = 'stale'
    r = IdentityRebuild(dataset_id=dataset.id, fingerprint=fp, state='previewed', preview=body,
                        plan=plan, total=len(dataset.records), created_at=time.time())
    db.add(r)
    db.flush()
    return r, True


def confirm(db, r, resolutions):
    """确认整批重建：冲突未解不放行；重试返回既有任务，不新增测时批次。"""
    if r.state in ('confirmed', 'rebuilding', 'switched'):
        return r, False
    if r.state == 'stale':
        raise HTTPException(409, '身份簿或批次已变化，请重新预览')
    dataset = db.get(Dataset, r.dataset_id)
    if r.fingerprint != registry_fingerprint(db, dataset):
        r.state = 'stale'
        raise HTTPException(409, '身份簿已变化，请重新预览')
    conflicts = r.preview.get('conflicts', [])
    missing = [c['label'] for c in conflicts if resolutions.get(c['key']) not in CHOICES]
    if missing:
        raise HTTPException(409, '配对冲突未解不放行：' + '、'.join(missing))
    busy = db.scalar(select(IdentityRebuild).where(
        IdentityRebuild.dataset_id == dataset.id,
        IdentityRebuild.state.in_(['confirmed', 'rebuilding']), IdentityRebuild.id != r.id))
    if busy:
        raise HTTPException(409, '该批次已有进行中的身份切换')
    excluded, exclusions = [], []
    for c in conflicts:
        choice = resolutions[c['key']]
        idxs = sorted(x['index'] for x in c['records'])
        keep = {'first': idxs[0], 'last': idxs[-1]}.get(choice)
        drop = idxs if keep is None else [i for i in idxs if i != keep]
        excluded += drop
        exclusions.append({'key': c['label'], 'choice': choice, 'kept': keep, 'dropped': sorted(drop)})
    r.plan = {**r.plan, 'excluded': sorted(excluded), 'exclusions': exclusions}
    r.resolutions = {k: v for k, v in resolutions.items() if k in {c['key'] for c in conflicts}}
    r.state, r.confirmed_at, r.error = 'confirmed', time.time(), ''
    return r, True


def finalize_rebuild(db, r):
    """整批重建并一次性切换：单事务内生成新版本、替换批次指针。"""
    dataset = db.get(Dataset, r.dataset_id)
    version = (db.scalar(select(func.max(IdentityMap.version)).where(IdentityMap.dataset_id == dataset.id)) or 0) + 1
    m = IdentityMap(dataset_id=dataset.id, version=version, assignments=r.plan.get('assignments', {}),
                    excluded=r.plan.get('excluded', []), exclusions=r.plan.get('exclusions', []),
                    state='active', created_at=time.time())
    db.add(m)
    db.flush()
    for old in db.scalars(select(IdentityMap).where(IdentityMap.dataset_id == dataset.id,
                                                    IdentityMap.state == 'active', IdentityMap.id != m.id)):
        old.state = 'superseded'
    dataset.active_map_id, dataset.identity_version = m.id, version
    for other in db.scalars(select(IdentityRebuild).where(IdentityRebuild.dataset_id == dataset.id,
                                                          IdentityRebuild.state == 'previewed', IdentityRebuild.id != r.id)):
        other.state = 'stale'
    r.map_id, r.map_version = m.id, version
    r.progress, r.state, r.finished_at = r.total, 'switched', time.time()


def apply_map(records, idmap):
    """按固定身份版本解析测时；供分析任务从受理到完成使用同一依据。"""
    excluded = set(idmap.excluded or [])
    assignments = idmap.assignments or {}
    out, originals, resolved, fallback = [], {}, 0, 0
    for i, rec in enumerate(records):
        if i in excluded:
            continue
        a = assignments.get(str(i)) or {}
        if 'person' in a:
            label, resolved = a['label'], resolved + 1
        else:
            label, fallback = a.get('raw') or str(rec.get('operator', '')), fallback + 1
        row = dict(rec)
        row['operator'] = label
        originals[label] = {'work_id': rec.get('operator', ''), 'date': rec.get('date')}
        out.append(row)
    info = {'map_id': idmap.id, 'version': idmap.version, 'resolved': resolved, 'fallback': fallback,
            'excluded_count': len(excluded), 'exclusions': idmap.exclusions or []}
    return out, info, originals
