"""Tiny SQLite schema sync for the demo database (no Alembic).

- Adds columns that exist in the models but not in the table.
- Rebuilds a table when a column became nullable (SQLite can't ALTER that).
create_all() still creates brand-new tables.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base

logger = logging.getLogger(__name__)


def sync_schema(engine: Engine) -> list[str]:
    if engine.dialect.name != "sqlite":
        return []
    changes: list[str] = []
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        existing_tables = set(inspect(conn).get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            info = {row[1]: row for row in conn.execute(text(f"PRAGMA table_info('{table.name}')"))}
            missing = [column for column in table.columns if column.name not in info]
            tightened = [
                column for column in table.columns
                if column.name in info and column.nullable and info[column.name][3] == 1  # notnull flag
            ]
            for column in missing:
                if not column.nullable and column.default is None:
                    raise RuntimeError(f"Cannot add NOT NULL column {table.name}.{column.name}")
                column_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))
                changes.append(f"added {table.name}.{column.name}")
            if tightened:
                old = f"{table.name}__old"
                conn.execute(text(f'ALTER TABLE "{table.name}" RENAME TO "{old}"'))
                for index in table.indexes:  # index names are global in SQLite
                    conn.execute(text(f'DROP INDEX IF EXISTS "{index.name}"'))
                table.create(conn)
                columns = ", ".join(f'"{name}"' for name in info if name in table.columns)
                conn.execute(text(f'INSERT INTO "{table.name}" ({columns}) SELECT {columns} FROM "{old}"'))
                conn.execute(text(f'DROP TABLE "{old}"'))
                changes.append(f"rebuilt {table.name} ({', '.join(c.name for c in tightened)} now nullable)")
    for change in changes:
        logger.info("Schema: %s", change)
    return changes
