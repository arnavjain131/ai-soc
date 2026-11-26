"""Opt-in grouped retrieval proof on the disposable loopback PostgreSQL lab."""
from datetime import datetime,timedelta
from uuid import uuid4

from app.ai_history import similar_incidents,historical_context
from app.models import Workspace,Incident,Alert
from test_assignment_postgres import postgres


def test_grouped_history_query_ranks_and_scopes_on_postgresql(postgres):
    anchor=datetime(2026,6,1)
    with postgres.begin() as db:
        workspace=Workspace(name='Synthetic history PG');other=Workspace(name='Other synthetic workspace')
        db.add_all([workspace,other]);db.flush()
        current=Incident(workspace_id=workspace.id,title='Current synthetic case',created_at=anchor)
        earlier=Incident(workspace_id=workspace.id,title='Earlier synthetic case',created_at=anchor-timedelta(days=1))
        foreign=Incident(workspace_id=other.id,title='Excluded synthetic case',created_at=anchor-timedelta(hours=1))
        future=Incident(workspace_id=workspace.id,title='Future synthetic case',created_at=anchor+timedelta(days=1))
        db.add_all([current,earlier,foreign,future]);db.flush()
        for item in (current,earlier,foreign,future):
            db.add(Alert(workspace_id=item.workspace_id,incident_id=item.id,rule_key='brute_force_v1',
                         dedup_key=uuid4().hex,explanation='Synthetic PG history'))
    with postgres() as db:
        cases=similar_incidents(db,workspace.id,current.id)
        assert [item['id'] for item in cases]==[earlier.id]
        assert cases[0]['shared_rules']==['brute_force_v1']
        assert 'title' not in historical_context(cases)[0]
        assert similar_incidents(db,other.id,current.id)==[]
