import io
import json
import sqlite3
from contextlib import closing
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

from collector import ssh_journal, suricata_forwarder


@pytest.mark.parametrize('collector', [ssh_journal, suricata_forwarder])
def test_http_429_preserves_pending_events_and_checkpoint_until_ack(collector):
    with closing(sqlite3.connect(':memory:')) as db:
        if collector is ssh_journal:
            collector.initialize(db, 100)
            db.execute("UPDATE checkpoint SET cursor='saved-cursor' WHERE id=1")
            checkpoint = 'checkpoint'
        else:
            collector.initialize(db)
            db.execute("INSERT INTO eve_position VALUES (1,2,3,100,X'6162')")
            checkpoint = 'eve_position'
        payload = json.dumps({'external_event_id': 'synthetic-event'})
        db.execute('INSERT INTO pending(event_id,payload) VALUES (?,?)', ('synthetic-event',payload))
        db.commit()
        before = db.execute('SELECT * FROM pending').fetchall()
        position = db.execute('SELECT * FROM ' + checkpoint).fetchall()
        opener = MagicMock()
        opener.open.side_effect = HTTPError('https://example.test/api/events/batch',429,'Too Many Requests',{'Retry-After':'1'},None)
        with pytest.raises(HTTPError):
            collector.deliver(db,'https://example.test/api/events/batch','synthetic-token',opener)
        assert db.execute('SELECT * FROM pending').fetchall() == before
        assert db.execute('SELECT * FROM ' + checkpoint).fetchall() == position
        opener.open.side_effect = None
        opener.open.return_value = io.BytesIO(b'{"accepted":1,"duplicates":0}')
        assert collector.deliver(db,'https://example.test/api/events/batch','synthetic-token',opener) == 1
        assert db.execute('SELECT count(*) FROM pending').fetchone()[0] == 0
        assert db.execute('SELECT * FROM ' + checkpoint).fetchall() == position
