"""Generate initial PostgreSQL DDL without connecting to any database."""
from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from .models import Base


def main():
    statements = [
        '-- Migration 001: first authentication detection slice. Apply once with the Supabase SQL editor.',
        '-- Backend-only tables: no browser Data API access. Backend queries must authorize workspace membership.',
        'BEGIN;',
    ]
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect())).strip() + ';')
        for index in sorted(table.indexes, key=lambda i: i.name):
            statements.append(str(CreateIndex(index).compile(dialect=dialect())) + ';')
        statements.append(f'ALTER TABLE public.{table.name} ENABLE ROW LEVEL SECURITY;')
        statements.append(f'REVOKE ALL ON TABLE public.{table.name} FROM anon, authenticated, PUBLIC;')
    statements.extend([
        'CREATE TABLE public.soc_schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());',
        'ALTER TABLE public.soc_schema_migrations ENABLE ROW LEVEL SECURITY;',
        'REVOKE ALL ON TABLE public.soc_schema_migrations FROM anon, authenticated, PUBLIC;',
        'INSERT INTO public.soc_schema_migrations (version) VALUES (1);',
        'COMMIT;',
    ])
    destination = Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' / '001_initial.sql'
    destination.parent.mkdir(parents=True, exist_ok=True)
    sql = '\n'.join(line.rstrip() for line in '\n\n'.join(statements).splitlines()) + '\n'
    destination.write_text(sql, encoding='utf-8')
    print('Initial PostgreSQL migration generated; no remote database was contacted.')


if __name__ == '__main__':
    main()
