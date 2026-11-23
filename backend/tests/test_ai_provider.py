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
