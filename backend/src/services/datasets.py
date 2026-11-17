from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata
from src.utils.serialization import checksum
import math, re, time
from datetime import date
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    for index,row in enumerate(data.records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='':
                if c.get('optional'):
                    row.pop(c['key'], None); continue
                raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
            elif c['type']=='date':
                s=str(value).strip()
                if not DATE_RE.match(s):
                    raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 须为 YYYY-MM-DD 格式')
                try: date.fromisoformat(s)
                except ValueError: raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 不是有效日期')
                row[c['key']]=s
            elif c['type']=='string':
                s=str(value).strip()
                if not s or len(s)>60: raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 须为 1–60 字文本')
                row[c['key']]=s
        if bool(row.get('date')) != bool(row.get('warehouse')):
            raise HTTPException(422, f'第 {index+1} 行测时日期与仓别需同时提供，身份归属才能按生效期匹配')
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    db.add(d); db.flush()
    return d
