import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
import zipfile

import pytest

from app import backup
from app.backup_crypto import BackupError, MAGIC, decrypt, encrypt, package, unpack


PASSPHRASE = 'synthetic backup passphrase for tests only'


def manifest():
    return {'format': 1, 'client_major': 17, 'server_major': 17, 'schema_version': 1,
            'counts': {table: 1 for table in backup.TABLES}, 'created_at': '2026-11-23T00:00:00Z',
            'scope': 'application tables only'}


def toc():
    return '\n'.join(f'1; 0 0 {kind} public {table} owner' for table in backup.TABLES for kind in ('TABLE', 'TABLE DATA')).encode()


def test_authenticated_roundtrip_and_unique_ciphertext():
    payload = package(b'PGDMPsynthetic archive', manifest())
    first, second = encrypt(payload, PASSPHRASE), encrypt(payload, PASSPHRASE)
    assert first != second
    assert b'PGDMPsynthetic' not in first and b'counts' not in first
    dump, info = unpack(decrypt(first, PASSPHRASE))
    assert dump == b'PGDMPsynthetic archive'
    assert info['counts'] == manifest()['counts']


@pytest.mark.parametrize('change', ['wrong_password', 'ciphertext', 'salt', 'nonce', 'header', 'truncated'])
def test_wrong_passphrase_and_tampering_are_rejected(change):
    blob = bytearray(encrypt(package(b'PGDMPfixture', manifest()), PASSPHRASE))
    password = PASSPHRASE
    if change == 'wrong_password':
        password = 'different synthetic test passphrase'
    elif change == 'truncated':
        del blob[-8:]
    else:
        index = {'ciphertext': -1, 'salt': len(MAGIC), 'nonce': len(MAGIC) + 16, 'header': 0}[change]
        blob[index] ^= 1
    with pytest.raises(BackupError):
        decrypt(bytes(blob), password)


def test_package_checks_hash_and_rejects_extra_members():
    valid = package(b'PGDMPfixture', manifest())
    output = io.BytesIO(valid)
    with zipfile.ZipFile(output, 'a') as archive:
        archive.writestr('../unexpected', b'not extracted')
    with pytest.raises(BackupError, match='Unexpected'):
        unpack(output.getvalue())
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest() | {'dump_sha256': 'wrong'}))
        archive.writestr('database.dump', b'PGDMPfixture')
    with pytest.raises(BackupError, match='checksum'):
        unpack(output.getvalue())
    with pytest.raises(BackupError):
        encrypt(valid, 'too short')


def test_pg_credentials_are_only_in_child_environment(monkeypatch):
    monkeypatch.setenv('PGSERVICE', 'unexpected')
    monkeypatch.setenv('PGHOSTADDR', '203.0.113.2')
    environment = backup.pg_environment('postgresql+psycopg://tester:synthetic%40password@pool.example:5432/postgres?sslmode=require')
    assert environment['PGPASSWORD'] == 'synthetic@password'
    assert environment['PGSSLMODE'] == 'require'
    assert environment['PGHOST'] == 'pool.example'
    assert 'PGSERVICE' not in environment and 'PGHOSTADDR' not in environment
    with pytest.raises(BackupError):
        backup.pg_environment('postgresql+psycopg://user:fixture@pool.example/postgres?sslmode=disable')
    with pytest.raises(BackupError):
        backup.pg_environment('sqlite:///test.db')


@pytest.mark.parametrize('url,confirmation', [
    ('postgresql+psycopg://user:fixture@production.example/ai_soc_restore_test', 'ai_soc_restore_test'),
    ('postgresql+psycopg://user:fixture@127.0.0.1/postgres', 'postgres'),
    ('postgresql+psycopg://user:fixture@localhost/ai_soc_restore_test', 'ai_soc_restore_test'),
    ('postgresql+psycopg://user:fixture@127.0.0.1/ai_soc_restore_test?host=production.example', 'ai_soc_restore_test'),
    ('postgresql+psycopg://user:fixture@127.0.0.1/ai_soc_restore_test', 'wrong'),
])
def test_unsafe_restore_target_is_refused_before_connecting(monkeypatch, url, confirmation):
    def must_not_connect(*args, **kwargs):
        raise AssertionError('Unsafe target must never be contacted')
    monkeypatch.setattr(backup, 'create_engine', must_not_connect)
    with pytest.raises(BackupError):
        backup.restore_check(b'PGDMPfixture', manifest(), {}, 17, url, confirmation)


def test_safe_target_requires_a_real_loopback_address_and_empty_database(monkeypatch):
    monkeypatch.setattr(backup, 'validate_contents', lambda *args: None)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    monkeypatch.setattr(backup, 'create_engine', lambda *args, **kwargs: engine)
    calls = []
    monkeypatch.setattr(backup, 'run_client', lambda *args, **kwargs: calls.append(args))
    url = 'postgresql+psycopg://user:fixture@127.0.0.1/ai_soc_restore_test'
    connection.scalar.side_effect = ['10.0.0.1']
    with pytest.raises(BackupError, match='loopback'):
        backup.restore_check(b'PGDMPfixture', manifest(), {}, 17, url, 'ai_soc_restore_test')
    connection.scalar.side_effect = ['127.0.0.1', 'ai_soc_restore_test', '170011', 1]
    with pytest.raises(BackupError, match='empty'):
        backup.restore_check(b'PGDMPfixture', manifest(), {}, 17, url, 'ai_soc_restore_test')
    assert calls == []


def test_successful_isolated_restore_uses_atomic_create_only_command(monkeypatch):
    monkeypatch.setattr(backup, 'validate_contents', lambda *args: None)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = ['127.0.0.1', 'ai_soc_restore_test', '170011', 0]
    monkeypatch.setattr(backup, 'create_engine', lambda *args, **kwargs: engine)
    monkeypatch.setattr(backup, 'inventory', lambda connection: {
        'counts': manifest()['counts'], 'schema_version': 1, 'rls_enabled': True,
    })
    calls = []
    monkeypatch.setattr(backup, 'run_client', lambda *args: calls.append(args))
    result = backup.restore_check(b'PGDMPfixture', manifest(), {'pg_restore': 'pg_restore'}, 17,
                                  'postgresql+psycopg://user:fixture@127.0.0.1/ai_soc_restore_test', 'ai_soc_restore_test')
    command, environment, data = calls[0]
    assert '--single-transaction' in command and '--exit-on-error' in command
    assert '--clean' not in command and '--create' not in command
    assert all('fixture' not in argument for argument in command)
    assert environment['PGHOST'] == '127.0.0.1' and data == b'PGDMPfixture'
    assert result['rls_enabled']


def test_verify_checks_all_expected_tables_without_restoring(monkeypatch):
    commands = []
    def client(command, **kwargs):
        commands.append(command)
        return toc()
    monkeypatch.setattr(backup, 'run_client', client)
    backup.validate_contents(b'PGDMPfixture', manifest(), {'pg_restore': 'pg_restore'}, 17)
    assert commands == [['pg_restore', '--list']]
    monkeypatch.setattr(backup, 'run_client', lambda *args, **kwargs: b'')
    with pytest.raises(BackupError, match='nine'):
        backup.validate_contents(b'PGDMPfixture', manifest(), {'pg_restore': 'pg_restore'}, 17)


def test_capture_shares_a_read_only_snapshot_with_native_dump_without_password_args(monkeypatch):
    engine = MagicMock()
    connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
    connection.scalar.side_effect = [4096, 'synthetic-snapshot-id']
    monkeypatch.setattr(backup, 'create_engine', lambda *args, **kwargs: engine)
    monkeypatch.setattr(backup, 'inventory', lambda connection: manifest())
    calls = []
    def native(command, environment=None, data=None):
        calls.append((command, environment))
        return toc() if '--list' in command else b'PGDMPsynthetic-native-result'
    monkeypatch.setattr(backup, 'run_client', native)
    dump, info = backup.capture('postgresql+psycopg://user:synthetic-password@pool.example/postgres?sslmode=require',
                               {'pg_dump': 'pg_dump', 'pg_restore': 'pg_restore'}, 17)
    command, environment = calls[0]
    assert '--snapshot=synthetic-snapshot-id' in command and '--format=custom' in command
    assert all('synthetic-password' not in argument and 'pool.example' not in argument for argument in command)
    assert environment['PGPASSWORD'] == 'synthetic-password'
    assert any(str(call.args[0]) == 'SET TRANSACTION READ ONLY' for call in connection.execute.call_args_list)
    assert dump == b'PGDMPsynthetic-native-result' and info['counts'] == manifest()['counts']


def test_native_errors_do_not_echo_secrets(monkeypatch):
    fake = MagicMock(returncode=1, stdout=b'', stderr=b'contains synthetic-private-credential')
    monkeypatch.setattr(backup.subprocess, 'run', lambda *args, **kwargs: fake)
    with pytest.raises(BackupError) as error:
        backup.run_client(['pg_dump'], {'PGPASSWORD': 'synthetic-private-credential'})
    assert 'synthetic-private-credential' not in str(error.value)


def test_noninteractive_prompt_refuses_fallback_echo(monkeypatch):
    monkeypatch.setattr(backup.sys.stdin, 'isatty', lambda: False)
    with pytest.raises(BackupError, match='interactive'):
        backup.prompt_passphrase()


def test_encrypted_writer_wont_overwrite_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'private_directory', lambda: tmp_path)
    identifier = MagicMock(hex='fixedidentifier')
    monkeypatch.setattr(backup, 'uuid4', lambda: identifier)
    clock = MagicMock()
    clock.now.return_value.strftime.return_value = 'fixed-time-'
    monkeypatch.setattr(backup, 'datetime', clock)
    first = backup.write_encrypted(b'encrypted-fixture-one')
    with pytest.raises(FileExistsError):
        backup.write_encrypted(b'encrypted-fixture-two')
    assert first.read_bytes() == b'encrypted-fixture-one'
