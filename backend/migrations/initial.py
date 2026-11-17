from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models
# 存量库的列补充：create_all 只建缺失的表，不会修改已有表
COLUMN_ADDITIONS = {
    'datasets': {'active_map_id': 'INTEGER NULL', 'identity_version': 'INTEGER NULL'},
    'jobs': {'identity_map_id': 'INTEGER NULL'},
}
def migrate():
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in COLUMN_ADDITIONS.items():
            existing = {c['name'] for c in insp.get_columns(table)}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
if __name__=='__main__':migrate()
