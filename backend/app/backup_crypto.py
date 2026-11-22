"""Versioned, authenticated encryption for small application backup archives."""
import hashlib
import io
import json
import os
import zipfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


MAGIC = b'AI-SOC-BACKUP-1\0'
MAX_DUMP_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = MAX_DUMP_BYTES + 32768
HEADER_BYTES = len(MAGIC) + 16 + 12


class BackupError(Exception):
    pass


def key(passphrase, salt):
    if len(passphrase) < 16:
        raise BackupError('Use a backup passphrase with at least 16 characters.')
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536).derive(passphrase.encode('utf-8'))


def package(dump, manifest):
    if not dump.startswith(b'PGDMP') or len(dump) > MAX_DUMP_BYTES:
        raise BackupError('Expected a PostgreSQL custom archive no larger than 64 MiB.')
    metadata = dict(manifest, dump_sha256=hashlib.sha256(dump).hexdigest())
    encoded = json.dumps(metadata, sort_keys=True).encode('utf-8')
    if len(encoded) > 16384:
        raise BackupError('Backup manifest is too large.')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('manifest.json', encoded)
        archive.writestr('database.dump', dump)
    return output.getvalue()


def unpack(payload):
    if len(payload) > MAX_PACKAGE_BYTES:
        raise BackupError('Backup exceeds the supported size limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) != 2 or {entry.filename for entry in entries} != {'manifest.json', 'database.dump'}:
                raise BackupError('Unexpected backup package contents.')
            for entry in entries:
                limit = 16384 if entry.filename == 'manifest.json' else MAX_DUMP_BYTES
                if entry.compress_type != zipfile.ZIP_STORED or entry.file_size > limit:
                    raise BackupError('Unsupported backup package member.')
            manifest = json.loads(archive.read('manifest.json'))
            dump = archive.read('database.dump')
        if (not dump.startswith(b'PGDMP') or not isinstance(manifest, dict)
                or manifest.get('dump_sha256') != hashlib.sha256(dump).hexdigest()):
            raise BackupError('Backup archive checksum does not match.')
        return dump, manifest
    except (zipfile.BadZipFile, ValueError, KeyError) as error:
        raise BackupError('Invalid backup package.') from None


def encrypt(payload, passphrase):
    if len(payload) > MAX_PACKAGE_BYTES:
        raise BackupError('Backup exceeds the supported size limit.')
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    return header + AESGCM(key(passphrase, salt)).encrypt(nonce, payload, header)


def decrypt(blob, passphrase):
    if not HEADER_BYTES + 16 <= len(blob) <= MAX_PACKAGE_BYTES + HEADER_BYTES + 16 or not blob.startswith(MAGIC):
        raise BackupError('Unsupported or damaged encrypted backup.')
    salt, nonce = blob[len(MAGIC):len(MAGIC) + 16], blob[len(MAGIC) + 16:HEADER_BYTES]
    try:
        return AESGCM(key(passphrase, salt)).decrypt(nonce, blob[HEADER_BYTES:], blob[:HEADER_BYTES])
    except InvalidTag:
        raise BackupError('Backup authentication failed: wrong passphrase or damaged file.') from None
