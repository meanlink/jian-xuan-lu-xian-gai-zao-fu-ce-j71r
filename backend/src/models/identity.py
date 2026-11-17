from sqlalchemy import String, JSON, Double, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Person(Base):
    __tablename__ = 'persons'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(300), default='')
    status: Mapped[str] = mapped_column(String(20), default='active')  # active | merged
    merged_into: Mapped[int | None] = mapped_column(ForeignKey('persons.id'), nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
class IdentityBinding(Base):
    __tablename__ = 'identity_bindings'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.id'))
    warehouse: Mapped[str] = mapped_column(String(60))
    work_id: Mapped[str] = mapped_column(String(60))
    valid_from: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 空表示至今
    state: Mapped[str] = mapped_column(String(20), default='active')  # active | revoked
    created_at: Mapped[float] = mapped_column(Double)
class IdentityMap(Base):
    __tablename__ = 'identity_maps'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    version: Mapped[int] = mapped_column(Integer)
    assignments: Mapped[dict] = mapped_column(JSON, default=dict)  # {行号: {person,label} | {raw}}
    excluded: Mapped[list] = mapped_column(JSON, default=list)  # 被配对冲突排除的行号
    exclusions: Mapped[list] = mapped_column(JSON, default=list)  # 排除明细 [{key,choice,kept,dropped}]
    state: Mapped[str] = mapped_column(String(20), default='active')  # active | superseded
    created_at: Mapped[float] = mapped_column(Double)
class IdentityRebuild(Base):
    __tablename__ = 'identity_rebuilds'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    fingerprint: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default='previewed')  # previewed|stale|confirmed|rebuilding|switched|failed
    preview: Mapped[dict] = mapped_column(JSON, default=dict)  # 受影响人员与配对冲突预览
    plan: Mapped[dict] = mapped_column(JSON, default=dict)  # 已确认的归属方案（中断恢复依据）
    resolutions: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    map_id: Mapped[int | None] = mapped_column(ForeignKey('identity_maps.id'), nullable=True)
    map_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(String(1000), default='')
    created_at: Mapped[float] = mapped_column(Double)
    confirmed_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
