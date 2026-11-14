import io
import json
import sqlite3
from contextlib import closing

from collector import ssh_journal


SINCE = 1794614400
DESTINATION = '10.0.2.15'


def mock_journal(monkeypatch, cursor):
    commands = []
    entry = {
        '__CURSOR': cursor,
        '__REALTIME_TIMESTAMP': str(SINCE * 1_000_000),
        'MESSAGE': 'Accepted password for aisoc from 10.0.2.2 port 50100 ssh2',
    }

    class Journal:
        def __enter__(self):
            self.stdout = io.StringIO(json.dumps(entry) + '\n')
            return self

        def __exit__(self, *_):
            self.stdout.close()

        def wait(self):
            return 0

        def poll(self):
            return 0

    def popen(command, **_):
        commands.append(command)
        return Journal()

    monkeypatch.setattr(ssh_journal.subprocess, 'Popen', popen)
    return commands


def journal_positions(command):
    return [arg for arg in command if arg.startswith(('--since=', '--cursor=', '--after-cursor='))]


def test_initial_collection_uses_since_and_saves_cursor(monkeypatch):
    commands = mock_journal(monkeypatch, 'first-cursor')
    with closing(sqlite3.connect(':memory:')) as db:
        ssh_journal.initialize(db, SINCE)

        assert ssh_journal.collect(db, DESTINATION) == 1

        assert journal_positions(commands[0]) == [f'--since=@{SINCE}']
        assert db.execute('SELECT since, cursor FROM checkpoint').fetchone() == (SINCE, 'first-cursor')
        assert db.execute('SELECT count(*) FROM pending').fetchone() == (1,)


def test_resume_uses_only_saved_cursor_and_preserves_pending_events(monkeypatch, tmp_path):
    path = tmp_path / 'queue.sqlite3'
    mock_journal(monkeypatch, 'first-cursor')
    with closing(sqlite3.connect(path)) as db:
        ssh_journal.initialize(db, SINCE)
        assert ssh_journal.collect(db, DESTINATION) == 1
        queued_before = db.execute('SELECT * FROM pending ORDER BY sequence').fetchall()

    commands = mock_journal(monkeypatch, 'next-cursor')
    with closing(sqlite3.connect(path)) as db:
        ssh_journal.initialize(db, SINCE + 60)

        assert ssh_journal.collect(db, DESTINATION) == 1

        assert journal_positions(commands[0]) == ['--after-cursor=first-cursor']
        assert db.execute('SELECT since, cursor FROM checkpoint').fetchone() == (SINCE, 'next-cursor')
        queued_after = db.execute('SELECT * FROM pending ORDER BY sequence').fetchall()
        assert len(queued_after) == 2
        assert queued_after[:1] == queued_before
