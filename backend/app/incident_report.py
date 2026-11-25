"""Authorized, bounded report snapshots. No writes, inference or external assets."""
import json
from datetime import timedelta
from html import escape
from typing import Literal
from uuid import UUID,uuid4

from fastapi import Depends,HTTPException,Request
from fastapi.responses import Response
from sqlalchemy import func,or_,select
from sqlalchemy.orm import Session

from .ai_analysis import COMPLETED,context_hash,present
from .ai_grounding import build_context
from .incident_assignment import assignment_summaries
from .incident_journal import HISTORY_ACTIONS,NOTE_ACTION,audit_json,note_json
from .models import Alert,AlertEvent,Audit,Event,Incident,Membership,Source,Workspace,now

MAX_EVENTS=1000
MAX_RELATED=1000
MAX_NOTES=500
MAX_HISTORY=2000
MAX_ALERTS=100
MAX_JSON_BYTES=4*1024*1024
MAX_FILE_BYTES=8*1024*1024


def stamp(value):return value.isoformat()+'Z'


def approved(session,identity):
    member=session.scalar(select(Membership.user_id).where(Membership.user_id==identity.user_id,
        Membership.workspace_id==identity.workspace_id,Membership.role.in_(('admin','analyst'))))
    if not member:raise HTTPException(403,'Workspace membership is required')


def bounded(session,query,maximum,label):
    rows=list(session.execute(query.limit(maximum+1)))
    if len(rows)>maximum:raise HTTPException(413,f'This incident exceeds the {label} export limit ({maximum}). No partial report was generated.')
    return rows


def event_json(event,source_name):
    data={'id':event.id,'event_time':stamp(event.event_time),'ingested_at':stamp(event.ingested_at),
        'event_type':event.event_type,'source_id':event.source_id,'source_name':source_name,
        'source_ip':event.source_ip,'destination_ip':event.destination_ip,'destination_port':event.destination_port}
    if event.event_type in ('LOGIN_FAILED','LOGIN_SUCCEEDED'):
        data['username']=event.username
        method=event.raw_data.get('authentication_method')
        data['authentication_method']=method if method in ('password','publickey','keyboard-interactive','keyboard-interactive/pam') else None
    else:
        raw=event.raw_data
        data['protocol']=raw.get('protocol') if raw.get('protocol') in ('TCP','UDP') else None
        data['source_port']=raw.get('source_port') if type(raw.get('source_port')) is int else None
        if event.event_type=='SURICATA_ALERT':
            data['signature_id']=raw.get('signature_id') if type(raw.get('signature_id')) is int else None
            data['severity']=raw.get('severity') if type(raw.get('severity')) is int else None
            data['signature']=raw.get('signature') if isinstance(raw.get('signature'),str) else None
    return data


def read_report(session,identity,incident_id,settings,include_ai):
    approved(session,identity)
    incident=session.scalar(select(Incident).where(Incident.id==incident_id,Incident.workspace_id==identity.workspace_id))
    if not incident:raise HTTPException(404,'Incident not found')
    workspace=session.get(Workspace,identity.workspace_id)
    alerts=[row[0] for row in bounded(session,select(Alert).where(Alert.workspace_id==identity.workspace_id,
        Alert.incident_id==incident_id).order_by(Alert.id),MAX_ALERTS,'detection alerts')]
    linked_ids=select(AlertEvent.event_id).join(Alert,Alert.id==AlertEvent.alert_id).where(
        Alert.workspace_id==identity.workspace_id,Alert.incident_id==incident_id)
    query=select(Event,Source.name).join(Source,(Source.id==Event.source_id)&(Source.workspace_id==Event.workspace_id)).where(Event.workspace_id==identity.workspace_id)
    linked=bounded(session,query.where(Event.id.in_(linked_ids)).order_by(Event.event_time,Event.id),MAX_EVENTS,'linked evidence')
    evidence=[event_json(event,name) for event,name in linked]
    groups={}
    for event,_ in linked:
        if event.event_type!='LOGIN_FAILED':continue
        key=(event.source_ip,event.destination_ip,event.destination_port)
        times=groups.setdefault(key,[event.event_time,event.event_time])
        times[0]=min(times[0],event.event_time);times[1]=max(times[1],event.event_time)
    if len(groups)>100:raise HTTPException(413,'This incident has too many endpoint groups for a bounded report. No partial report was generated.')
    related=[]
    if groups:
        windows=[(Event.source_ip==src)&(Event.destination_ip==dst)&(Event.destination_port==port)&
            Event.event_time.between(times[0]-timedelta(minutes=2),times[1]+timedelta(minutes=2))
            for (src,dst,port),times in groups.items()]
        related=bounded(session,query.where(Event.event_type.in_(('NETWORK_FLOW','SURICATA_ALERT')),
            Event.raw_data['protocol'].as_string()=='TCP',or_(*windows),Event.id.not_in([event.id for event,_ in linked]))
            .order_by(Event.event_time,Event.id),MAX_RELATED,'related network records')
    context=[event_json(event,name) for event,name in related]
    audit=select(Audit).where(Audit.workspace_id==identity.workspace_id,Audit.target_id==incident_id)
    notes=[note_json(row[0]) for row in bounded(session,audit.where(Audit.action==NOTE_ACTION)
        .order_by(Audit.created_at,Audit.id),MAX_NOTES,'analyst notes')]
    history=[audit_json(row[0]) for row in bounded(session,audit.where(Audit.action.in_(HISTORY_ACTIONS))
        .order_by(Audit.created_at,Audit.id),MAX_HISTORY,'history entries')]
    incident_data={key:getattr(incident,key) for key in ('id','title','status','severity','risk_score','score_components')}
    incident_data.update(created_at=stamp(incident.created_at),updated_at=stamp(incident.updated_at))
    detail={**incident_data,'events':evidence,'related_network_events':context,
        'alerts':[{'id':a.id,'rule_key':a.rule_key,'explanation':a.explanation} for a in alerts]}
    saved=None
    if include_ai:
        latest=session.scalar(audit.where(Audit.action==COMPLETED).order_by(Audit.created_at.desc(),Audit.id.desc()).limit(1))
        if latest:
            try:digest=context_hash(build_context(detail),settings.ai_model)
            except ValueError:digest=None
            saved=present(latest,digest)
    return {'report_version':1,'report_id':str(uuid4()),'generated_at':stamp(now()),'prepared_for_user_id':identity.user_id,
        'workspace':{'id':workspace.id,'name':workspace.name},'incident':incident_data,
        'assignment':assignment_summaries(session,identity.workspace_id,[incident_id],identity.user_id)[incident_id],
        'alerts':detail['alerts'],'linked_evidence':evidence,'related_network_context':context,
        'analyst_notes':notes,'investigation_history':history,'saved_ai_analysis':saved,'ai_included':include_ai,
        'counts':{'linked_evidence':len(evidence),'related_network_context':len(context),'analyst_notes':len(notes),'history':len(history),'alerts':len(alerts)},
        'scope':['Private workspace report. Contains usernames, network addresses and analyst notes; no collector credentials or arbitrary raw payloads.',
            'Related network records match TCP endpoints and a two-minute window around linked failed logins; this does not prove session attribution.',
            'Risk scores are rule-based priorities, not probabilities. AI output is advisory and needs analyst review.',
            'Only the latest saved AI analysis is included when requested. Export never generates a new analysis.',
            'This is an application investigation report, not a full packet capture, database backup, digital signature or proof of compromise.']}


def html_report(report):
    def text(value):return escape(str(value) if value is not None else 'Not recorded',quote=True)
    def table(columns,rows):
        if not rows:return '<p class="muted">None recorded.</p>'
        return '<div class="table"><table><thead><tr>'+''.join('<th>'+text(name)+'</th>' for name in columns)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td>'+text(cell)+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    def heading(title,body):return '<section><h2>'+text(title)+'</h2>'+body+'</section>'
    incident=report['incident'];owner=report['assignment']
    metadata=[['Report ID',report['report_id']],['Generated (UTC)',report['generated_at']],['Workspace',report['workspace']['name']],
        ['Incident ID',incident['id']],['Status',incident['status']],['Severity',incident['severity']],['Risk (priority / 100)',incident['risk_score']],
        ['Created (UTC)',incident['created_at']],['Updated (UTC)',incident['updated_at']],['Prepared for account',report['prepared_for_user_id']],
        ['Assignee',owner['assignee_id'] or 'Unassigned'],['Assignee access',('Active' if owner['active'] else 'Inactive') if owner['assignee_id'] else 'Unassigned']]
    body=heading('Incident summary',table(['Field','Value'],metadata))
    body+=heading('Risk breakdown',table(['Component','Points'],incident['score_components'].items()))
    body+=heading('Detection rationale',table(['Alert ID','Rule','Explanation'],[[a['id'],a['rule_key'],a['explanation']] for a in report['alerts']]))
    def events(items):
        return ''.join('<article id="event-'+text(e['id'])+'"><h3>'+text(e['event_type'])+'</h3>'+table(['Field','Value'],
            [[k,v] for k,v in e.items()])+'</article>' for e in items) or '<p class="muted">None recorded.</p>'
    body+=heading('Linked evidence ('+str(len(report['linked_evidence']))+')',events(report['linked_evidence']))
    body+=heading('Related network context ('+str(len(report['related_network_context']))+')',
        '<p>Contextual endpoint/time matches; not additional rule evidence or proof of session identity.</p>'+events(report['related_network_context']))
    body+=heading('Analyst notes',table(['Time (UTC)','Author account','Note ID','Note'],[[n['created_at'],n['actor_id'],n['id'],n['body']] for n in report['analyst_notes']]))
    actions=[]
    for entry in report['investigation_history']:
        d=entry['details'];before=d.get('before');after=d.get('after')
        change='Added analyst note' if entry['action']==NOTE_ACTION else str(before or 'Unassigned')+' → '+str(after or 'Unassigned')
        actions.append([entry['created_at'],entry['actor_id'],entry['id'],entry['action'],change])
    body+=heading('Investigation history',table(['Time (UTC)','Actor account','Entry ID','Action','Change'],actions))
    ai=report['saved_ai_analysis']
    if ai:
        answer=ai['answer'];known={e['id'] for e in report['linked_evidence']+report['related_network_context']}
        ai_body='<p><strong>Saved AI interpretation — analyst review required.</strong></p>'
        if ai['outdated']:ai_body+='<p class="warning">Evidence or model configuration has changed since this analysis.</p>'
        ai_body+=table(['Field','Value'],[['Model',ai['model']],['Generated (UTC)',ai['generated_at']],['Saved analysis ID',ai['id']],['Knowledge version',ai['knowledge_version']],['Context fingerprint',ai['context_hash']]])
        ai_body+='<h3>Summary</h3><p>'+text(answer['summary'])+'</p><h3>Observations</h3>'
        for observation in answer['observations']:
            links=[('<a href="#event-'+text(i)+'">'+text(i)+'</a>') if i in known else text(i)+' (not in current report evidence)' for i in observation['event_ids']]
            ai_body+='<article><p>'+text(observation['text'])+'</p><p class="muted">Evidence: '+', '.join(links)+'</p></article>'
        ai_body+='<h3>Interpretation</h3><p>'+text(answer['interpretation'])+'</p><h3>Suggested investigation</h3><ol>'
        ai_body+=''.join('<li>'+text(s['text'])+'<p class="muted">References: '+text(', '.join(s['reference_ids']))+'</p></li>' for s in answer['investigation_steps'])+'</ol>'
        ai_body+=table(['Reference ID','Title','URL'],[[r['id'],r['title'],r.get('url')] for r in ai['references']])
        ai_body+='<h3>Limitations</h3><ul>'+''.join('<li>'+text(s)+'</li>' for s in answer['limitations']+ai['context_limitations'])+'</ul>'
        ai_body+='<p>AI input omitted '+str(ai['omitted_linked_events'])+' linked and '+str(ai['omitted_related_events'])+' related records to meet input bounds. The current report evidence is independent of these model input limits.</p>'
    else:ai_body='<p>'+('No saved AI analysis is available. No new analysis was generated.' if report['ai_included'] else 'Saved AI analysis was excluded by the exporter.')+'</p>'
    body+=heading('Saved AI analysis',ai_body)
    body+=heading('Report scope and limitations','<ul>'+''.join('<li>'+text(s)+'</li>' for s in report['scope'])+'</ul>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>AISOC incident report</title><style>'+REPORT_CSS+'</style></head><body><header><div class="brand">AISOC · PRIVATE INVESTIGATION REPORT</div><h1>'+text(incident['title'])+'</h1><p>Report version 1 · All report timestamps are UTC · '+text(report['generated_at'])+'</p></header>'+body+'<footer>Generated from saved AISOC records. To save a PDF, use your browser’s Print → Save as PDF.</footer></body></html>'


REPORT_CSS='''*{box-sizing:border-box}body{font:14px/1.6 system-ui,sans-serif;color:#172c39;background:#fff;max-width:1100px;margin:36px auto;padding:0 28px}header{border-bottom:3px solid #287e78;padding-bottom:20px}.brand{font-size:11px;letter-spacing:2px;color:#287e78}h1{font-size:28px;line-height:1.3;overflow-wrap:anywhere}h2{font-size:20px;border-bottom:1px solid #cbd7da;padding-bottom:8px}h3{font-size:15px}section{margin-top:32px}p,td,li{overflow-wrap:anywhere;white-space:pre-wrap}.muted,footer{color:#536976;font-size:12px}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{text-align:left;vertical-align:top;border:1px solid #ced9dd;padding:8px;font-size:12px}th{background:#eef4f4}article{margin:18px 0}a{color:#176860}.warning{border-left:4px solid #a67416;padding:10px;background:#fff9e9}footer{margin:40px 0 20px;border-top:1px solid #ced9dd;padding-top:15px}@page{size:A4;margin:15mm}@media print{body{max-width:none;margin:0;padding:0;font-size:11px}thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}a{color:inherit;text-decoration:none}th,td{font-size:9px}section{margin-top:20px}}'''


def install_report_routes(api,member,session_dependency):
    @api.get('/api/incidents/{incident_id}/report')
    def report(incident_id:str,request:Request,format:Literal['html','json']='html',include_ai:bool=True,
               identity=Depends(member),auth_session=Depends(session_dependency)):
        try:incident_id=str(UUID(incident_id))
        except ValueError:raise HTTPException(404,'Incident not found') from None
        # The cached membership dependency only reads. Return its connection
        # before taking a report snapshot, even when the pool has one slot.
        auth_session.rollback()
        engine=request.app.state.engine
        with engine.connect() as connection:
            if engine.dialect.name=='postgresql':connection=connection.execution_options(isolation_level='REPEATABLE READ')
            with connection.begin():
                if engine.dialect.name=='postgresql':connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                with Session(bind=connection) as session:
                    payload=read_report(session,identity,incident_id,request.app.state.settings,include_ai)
        encoded=json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8')
        if len(encoded)>MAX_JSON_BYTES:raise HTTPException(413,'Report exceeds the export size limit. No partial report was generated.')
        content=html_report(payload).encode('utf-8') if format=='html' else encoded
        if len(content)>MAX_FILE_BYTES:raise HTTPException(413,'Report exceeds the download size limit. No partial report was generated.')
        # Recheck current access after the read snapshot has closed, before delivery.
        with request.app.state.sessions() as session:approved(session,identity)
        return Response(content,media_type='text/html' if format=='html' else 'application/json',headers={
            'Content-Disposition':f'attachment; filename="aisoc-incident-{incident_id}.{format}"',
            'Cache-Control':'no-store, private','Pragma':'no-cache','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; sandbox"})
