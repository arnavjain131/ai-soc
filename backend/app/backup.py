"""Offline native PostgreSQL backups. No HTTP endpoint or production restore."""
import argparse
import csv
import getpass
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .backup_crypto import BackupError, MAX_DUMP_BYTES, MAX_PACKAGE_BYTES, HEADER_BYTES, encrypt, decrypt, package, unpack
from .config import Settings


TABLES = ('soc_workspaces', 'soc_memberships', 'soc_sources', 'soc_events', 'soc_incidents',
          'soc_alerts', 'soc_alert_events', 'soc_audit_logs', 'soc_schema_migrations')


def pg_environment(database_url, local=False):
    url = make_url(database_url)
    if url.get_backend_name() != 'postgresql' or not url.host or not url.database or not url.username:
        raise BackupError('A configured PostgreSQL connection is required.')
    environment = {name: value for name, value in os.environ.items() if not name.upper().startswith('PG')}
    sslmode = url.query.get('sslmode', 'disable' if local else 'require')
    if not local and sslmode not in ('require', 'verify-ca', 'verify-full'):
        raise BackupError('Remote backups require TLS.')
    environment.update(PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
                       PGUSER=url.username, PGPASSWORD=url.password or '', PGSSLMODE=sslmode,
                       PGCONNECT_TIMEOUT='10', PGAPPNAME='ai-soc-maintenance')
    return environment


def client_tools():
    configured = os.environ.get('SOC_PG_BIN')
    suffix = '.exe' if os.name == 'nt' else ''
    paths = {}
    for name in ('pg_dump', 'pg_restore'):
        candidate = str(Path(configured) / (name + suffix)) if configured else shutil.which(name)
        if not candidate and os.name == 'nt':
            default = Path('C:/Program Files/PostgreSQL/17/bin') / (name + suffix)
            candidate = str(default) if default.is_file() else None
        if not candidate or not Path(candidate).is_file():
            raise BackupError('PostgreSQL 17 Command Line Tools are missing. Install them or set SOC_PG_BIN to their bin directory.')
        paths[name] = candidate
    versions = []
    for name, path in paths.items():
        result = subprocess.run([path, '--version'], capture_output=True, timeout=10)
        match = re.search(rb'PostgreSQL\) (\d+)', result.stdout)
        if result.returncode or not match:
            raise BackupError('Could not verify PostgreSQL client tools.')
        versions.append(int(match.group(1)))
    if versions[0] != versions[1]:
        raise BackupError('pg_dump and pg_restore must have the same major version.')
    return paths, versions[0]


def run_client(command, environment=None, data=None):
    try:
        result = subprocess.run(command, env=environment, input=data, capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError('PostgreSQL client did not complete. No credentials or raw output are logged.') from None
    if result.returncode:
        raise BackupError('PostgreSQL client failed. Check tool compatibility and connectivity locally; raw output is withheld.')
    return result.stdout


def inventory(connection):
    counts = {table: connection.scalar(text(f'SELECT count(*) FROM public.{table}')) for table in TABLES}
    version = connection.scalar(text("SELECT current_setting('server_version')"))
    rls = dict(connection.execute(text('''SELECT c.relname, c.relrowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY(:names)'''), {'names': list(TABLES)}).all())
    return {'counts': counts, 'server_version': version, 'server_major': int(version.split('.')[0]),
            'schema_version': connection.scalar(text('SELECT max(version) FROM public.soc_schema_migrations')),
            'rls_enabled': all(rls.get(table) is True for table in TABLES)}


def source_inventory(url):
    pg_environment(url)  # Validate configuration without displaying it.
    engine = create_engine(url, connect_args={'connect_timeout': 10})
    try:
        with engine.connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            connection.execute(text("SET LOCAL statement_timeout = '15000'"))
            return inventory(connection)
    finally:
        engine.dispose()


def validate_contents(dump, manifest, tools, major):
    if (manifest.get('format') != 1 or manifest.get('client_major') != major
            or set(manifest.get('counts', {})) != set(TABLES)):
        raise BackupError('Backup format, table scope or client version does not match.')
    toc = run_client([tools['pg_restore'], '--list'], data=dump).decode('utf-8', errors='replace')
    tables = set(re.findall(r'\bTABLE public (soc_\w+)\s', toc))
    data_tables = set(re.findall(r'\bTABLE DATA public (soc_\w+)\s', toc))
    if tables != set(TABLES) or data_tables != set(TABLES):
        raise BackupError('Archive does not contain exactly the nine expected application tables and data sections.')


def capture(url, tools, major):
    environment = pg_environment(url)
    engine = create_engine(url, connect_args={'connect_timeout': 10})
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with connection.begin():
                connection.execute(text('SET TRANSACTION READ ONLY'))
                connection.execute(text("SET LOCAL statement_timeout = '15000'"))
                manifest = inventory(connection)
                if manifest['server_major'] != major:
                    raise BackupError('Use client tools with the same major version as the PostgreSQL server.')
                size = connection.scalar(text('SELECT sum(pg_total_relation_size(tablename::regclass)) FROM unnest(CAST(:names AS text[])) AS tablename'),
                                         {'names': ['public.' + table for table in TABLES]})
                if size > MAX_DUMP_BYTES:
                    raise BackupError('Database exceeds this small-lab backup tool size limit. Use a reviewed streaming workflow.')
                snapshot = connection.scalar(text('SELECT pg_export_snapshot()'))
                command = [tools['pg_dump'], '--format=custom', '--no-owner', '--no-privileges', '--no-password',
                           '--strict-names', '--snapshot=' + snapshot]
                command.extend('--table=public.' + table for table in TABLES)
                dump = run_client(command, environment)
                if len(dump) > MAX_DUMP_BYTES:
                    raise BackupError('Database archive exceeds 64 MiB; no backup written.')
                manifest.update(format=1, client_major=major,
                                created_at=datetime.now(timezone.utc).isoformat(),
                                scope='Nine public soc_* tables; excludes Supabase Auth, Storage, roles, provider settings and collector credentials/state.')
                validate_contents(dump, manifest, tools, major)
                return dump, manifest
    finally:
        engine.dispose()


def private_directory():
    base = Path(os.environ['LOCALAPPDATA']) / 'AI-SOC' / 'backups' if os.name == 'nt' else Path.home() / '.local/share/ai-soc/backups'
    if base.is_symlink():
        raise BackupError('Backup directory must not be a symlink.')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
        sid = next(csv.reader(io.StringIO(identity.stdout.strip())))[1]
        if not re.fullmatch(r'S-1-(?:\d+-)*\d+', sid):
            raise BackupError('Could not determine the local backup owner.')
        result = subprocess.run(['icacls', str(base), '/inheritance:r', '/grant:r',
                                 f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], capture_output=True)
        if result.returncode:
            raise BackupError('Could not restrict permissions on the private backup directory.')
    else:
        base.chmod(0o700)
    return base


def write_encrypted(blob):
    path = private_directory() / ('ai-soc-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8] + '.aisocbak')
    created = False
    try:
        with path.open('xb') as output:
            created = True
            output.write(blob); output.flush(); os.fsync(output.fileno())
        if os.name != 'nt':
            path.chmod(0o600)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def read_encrypted(path):
    with Path(path).open('rb') as source:
        blob = source.read(MAX_PACKAGE_BYTES + HEADER_BYTES + 17)
    return unpack(decrypt(blob, prompt_passphrase()))


def prompt_passphrase(confirm=False):
    if not sys.stdin.isatty():
        raise BackupError('Run in an interactive terminal for the hidden backup-passphrase prompt.')
    value = getpass.getpass('Backup passphrase (not your database password): ')
    if len(value) < 16:
        raise BackupError('Use a backup passphrase with at least 16 characters.')
    if confirm and getpass.getpass('Confirm backup passphrase: ') != value:
        raise BackupError('Backup passphrases did not match.')
    return value


def restore_target(url, confirmation):
    parsed = make_url(url)
    if (parsed.get_backend_name() != 'postgresql' or parsed.host not in ('127.0.0.1', '::1')
            or not re.fullmatch(r'ai_soc_restore_[a-z0-9_]{1,40}', parsed.database or '')
            or parsed.database != confirmation or parsed.query):
        raise BackupError('Restore checks require a literal loopback host, an ai_soc_restore_* database, no URL options and exact database-name confirmation.')
    return parsed


def restore_check(dump, manifest, tools, major, url, confirmation):
    parsed = restore_target(url, confirmation)
    validate_contents(dump, manifest, tools, major)
    engine = create_engine(url, connect_args={'connect_timeout': 10, 'hostaddr': parsed.host, 'sslmode': 'disable'})
    try:
        with engine.connect() as connection:
            address = connection.scalar(text('SELECT inet_server_addr()::text'))
            if address not in ('127.0.0.1/32', '::1/128', '127.0.0.1', '::1'):
                raise BackupError('Restore server itself must report a loopback address; remote tunnels are refused.')
            if connection.scalar(text('SELECT current_database()')) != parsed.database:
                raise BackupError('Restore target database does not match.')
            server_major = int(connection.scalar(text("SELECT current_setting('server_version_num')"))) // 10000
            if server_major < manifest['server_major']:
                raise BackupError('Restore-check server must not be older than the source PostgreSQL major version.')
            count = connection.scalar(text('''SELECT
                (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema') +
                (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema')'''))
            if count:
                raise BackupError('Restore-check database must be empty. Existing objects will not be dropped.')
        run_client([tools['pg_restore'], '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges',
                    '--no-password', '--dbname=' + parsed.database], pg_environment(url, local=True), dump)
        with engine.connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            restored = inventory(connection)
            if restored['counts'] != manifest['counts'] or restored['schema_version'] != manifest['schema_version'] or not restored['rls_enabled']:
                raise BackupError('Restore completed, but count/schema/RLS checks need review. The isolated target was retained.')
        return restored
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('create')
    verify = sub.add_parser('verify'); verify.add_argument('archive')
    restore = sub.add_parser('restore-check'); restore.add_argument('archive'); restore.add_argument('--confirm-database', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            report = source_inventory(Settings().database_url)
            print(json.dumps(report, indent=2))
            tools, major = client_tools()
            if major != report['server_major']:
                raise BackupError('Install PostgreSQL client tools matching the database major version.')
            print('Client tools ready. No backup or restore performed.')
        else:
            tools, major = client_tools()
            if args.command == 'create':
                passphrase = prompt_passphrase(confirm=True)
                dump, manifest = capture(Settings().database_url, tools, major)
                blob = encrypt(package(dump, manifest), passphrase)
                # Authenticate the exact bytes before writing the encrypted file.
                unpack(decrypt(blob, passphrase))
                print('Encrypted application backup:', write_encrypted(blob))
                print('Scope: nine application tables only. Keep the passphrase separately; it is not saved.')
            else:
                dump, manifest = read_encrypted(args.archive)
                validate_contents(dump, manifest, tools, major)
                if args.command == 'verify':
                    print(json.dumps({name: manifest[name] for name in ('created_at', 'counts', 'schema_version', 'scope')}, indent=2))
                    print('Encryption, archive checksum and table-of-contents checks passed. No restore was performed.')
                else:
                    load_dotenv(Path(__file__).resolve().parents[1] / '.env.restore')
                    target = os.environ.get('SOC_RESTORE_DATABASE_URL')
                    if not target:
                        raise BackupError('Configure the isolated local SOC_RESTORE_DATABASE_URL privately in backend/.env.restore.')
                    restore_check(dump, manifest, tools, major, target, args.confirm_database)
                    print('Isolated local restore, row counts, schema version and RLS checks passed. Target retained for review.')
    except BackupError as error:
        print(str(error), file=sys.stderr); return 1
    except (EOFError, KeyboardInterrupt):
        print('Cancelled. No restore was requested against the hosted database.', file=sys.stderr); return 1
    except Exception as error:
        print(f'Maintenance failed ({type(error).__name__}). Credentials, passphrases and raw client output are not logged.', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
