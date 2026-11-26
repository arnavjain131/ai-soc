import json
from dataclasses import replace

import httpx
import pytest

from app import ai_provider
from app.ai_grounding import build_context
from app.config import Settings
from test_ai_grounding import incident, answer


def mocked_client(monkeypatch, handler):
    original=httpx.Client
    monkeypatch.setattr(ai_provider.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def provider_response(context):
    return {'status':'completed','model':'gpt-5.4-mini-2026-03-17','usage':{'input_tokens':100,'output_tokens':90},
        'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(answer(context))}]}]}


def test_request_uses_fixed_endpoint_schema_no_tools_and_no_storage(monkeypatch):
    context=build_context(incident())
    seen=[]
    def handler(request):
        seen.append(request)
        assert str(request.url)=='https://api.openai.com/v1/responses'
        payload=json.loads(request.content)
        assert payload['store'] is False and payload['tools']==[]
        assert payload['reasoning']=={'effort':'none'}
        assert payload['max_output_tokens']==2000
        assert payload['text']['format']['strict'] is True
        assert payload['text']['format']['schema']['additionalProperties'] is False
        definitions=payload['text']['format']['schema']['$defs']
        assert definitions['CitedObservation']['properties']['event_ids']['items']['enum']==sorted(e['id'] for e in context['evidence'])
        assert definitions['InvestigationStep']['properties']['reference_ids']['items']['enum']==sorted(r['id'] for r in context['references'])
        assert 'private-account-name' not in payload['input']
        return httpx.Response(200,json=provider_response(context))
    mocked_client(monkeypatch,handler)
    settings=Settings(openai_api_key='synthetic-private-key')
    result=ai_provider.call_openai(settings,context)
    assert result['answer']['summary']=='Failures were observed.' and len(seen)==1
    assert result['usage']=={'input_tokens':100,'output_tokens':90}
    assert 'synthetic-private-key' not in repr(settings)


@pytest.mark.parametrize('status,code',[(401,'provider_configuration'),(403,'provider_configuration'),
    (429,'provider_rate_limited'),(500,'provider_unavailable'),(302,'provider_unavailable')])
def test_errors_are_sanitized_and_never_retried(monkeypatch,status,code):
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(status,text='private provider error or credential',headers={'Location':'https://untrusted.test'})
    mocked_client(monkeypatch,handler)
    with pytest.raises(ai_provider.AIProviderError) as failure:
        ai_provider.call_openai(Settings(openai_api_key='synthetic'),build_context(incident()))
    assert failure.value.code==code and len(calls)==1
    assert 'private provider error' not in str(failure.value)


@pytest.mark.parametrize('kind',['refused','incomplete','bad_citation','tool_call','oversized','invalid_json'])
def test_provider_failures_do_not_become_accepted_analysis(monkeypatch,kind):
    context=build_context(incident())
    data=provider_response(context)
    if kind=='refused': data['output'][0]['content']=[{'type':'refusal','refusal':'private raw refusal'}]
    if kind=='incomplete': data['status']='incomplete'
    if kind=='bad_citation':
        payload=answer(context);payload['observations'][0]['event_ids']=['fabricated']
        data['output'][0]['content'][0]['text']=json.dumps(payload)
    if kind=='tool_call': data['output']=[{'type':'function_call','name':'execute'}]
    def handler(request):
        if kind=='oversized':return httpx.Response(200,content=b'x'*131073)
        if kind=='invalid_json':return httpx.Response(200,content=b'not-json')
        return httpx.Response(200,json=data)
    mocked_client(monkeypatch,handler)
    with pytest.raises(ai_provider.AIProviderError):
        ai_provider.call_openai(Settings(openai_api_key='synthetic'),context)


def test_missing_key_enabled_model_and_limits_fail_before_calls():
    with pytest.raises(ValueError):Settings(ai_enabled=True,openai_api_key='').validate()
    with pytest.raises(ValueError):Settings(ai_model='unreviewed-model').validate()
    with pytest.raises(ValueError):Settings(ai_daily_limit=0).validate()


@pytest.mark.parametrize('rule,event_type,count,reference',[
    ('brute_force_v1','LOGIN_FAILED',5,'rb.password_guessing'),
    ('password_spray_v1','LOGIN_FAILED',5,'rb.password_spraying'),
    ('tcp_port_scan_v1','NETWORK_FLOW',8,'rb.service_discovery'),
    ('suricata_priority_alert_v1','SURICATA_ALERT',1,'rb.sensor_alert'),
])
def test_each_detection_uses_only_its_own_citation_choices(monkeypatch,rule,event_type,count,reference):
    detail=incident(count)
    detail['alerts']=[{'rule_key':rule}]
    for index,event in enumerate(detail['events']):
        event.update(event_type=event_type,protocol='TCP',destination_port=18080+index,
                     signature_id=1000491,severity=1)
    context=build_context(detail)
    def handler(request):
        schema=json.loads(request.content)['text']['format']['schema']
        allowed=schema['$defs']['InvestigationStep']['properties']['reference_ids']['items']['enum']
        assert reference in allowed
        assert allowed==sorted(ref['id'] for ref in context['references'])
        assert all(value==reference or value.startswith('kb.') for value in allowed)
        assert schema['$defs']['CitedObservation']['properties']['event_ids']['items']['enum']==sorted(e['id'] for e in context['evidence'])
        payload=provider_response(context)
        output=answer(context)
        output['summary']='Stored evidence requires review.'
        output['observations'][0]['text']='Review the supplied event types and timestamps.'
        output['observations'][0]['event_ids']=[e['id'] for e in context['evidence']]
        payload['output'][0]['content'][0]['text']=json.dumps(output)
        return httpx.Response(200,json=payload)
    mocked_client(monkeypatch,handler)
    result=ai_provider.call_openai(Settings(openai_api_key='synthetic'),context)
    assert len(result['answer']['observations'][0]['event_ids'])==count


@pytest.mark.parametrize('kind,code',[
    ('evidence','invalid_evidence_citation'),('reference','invalid_reference_citation'),
    ('structure','invalid_answer_schema'),('json','invalid_answer_json'),
    ('envelope','invalid_provider_json'),
])
def test_failure_categories_are_precise_without_exposing_rejected_text(monkeypatch,kind,code):
    context=build_context(incident())
    data=provider_response(context)
    output=answer(context)
    if kind=='evidence':output['observations'][0]['event_ids']=['private-invalid-citation']
    if kind=='reference':output['investigation_steps'][0]['reference_ids']=['private-invalid-reference']
    if kind=='structure':output['summary']=''
    data['output'][0]['content'][0]['text']='private-invalid-json' if kind=='json' else json.dumps(output)
    mocked_client(monkeypatch,lambda _:httpx.Response(200,content=b'private-envelope') if kind=='envelope' else httpx.Response(200,json=data))
    with pytest.raises(ai_provider.AIProviderError) as error:
        ai_provider.call_openai(Settings(openai_api_key='synthetic'),context)
    assert error.value.code==code and 'private-' not in str(error.value)
