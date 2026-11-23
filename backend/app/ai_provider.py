"""Small, explicit OpenAI Responses adapter. No retries, tools or raw logs."""
import json
import re
import time

import httpx

from .ai_grounding import GroundedAnswer, SYSTEM_INSTRUCTIONS, validate_answer

PROMPT_VERSION='1'
REQUEST_INSTRUCTIONS=SYSTEM_INSTRUCTIONS+' Keep the answer concise and within the output budget.'


class AIProviderError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def call_openai(settings, context):
    payload = {'model': settings.ai_model, 'store': False, 'tools': [],
        'reasoning': {'effort': 'none'}, 'max_output_tokens': settings.ai_output_tokens,
        'instructions': REQUEST_INSTRUCTIONS,
        'input': json.dumps(context, sort_keys=True),
        'text': {'format': {'type':'json_schema','name':'aisoc_incident_analysis','strict':True,
                           'schema':GroundedAnswer.model_json_schema()}}}
    try:
        deadline = time.monotonic() + 30
        with httpx.Client(timeout=httpx.Timeout(20.0,connect=5.0),follow_redirects=False) as client:
            with client.stream('POST','https://api.openai.com/v1/responses',
                headers={'Authorization':'Bearer '+settings.openai_api_key,'Accept-Encoding':'identity'},json=payload) as response:
                if response.status_code in (401,403):
                    raise AIProviderError('provider_configuration')
                if response.status_code == 429:
                    raise AIProviderError('provider_rate_limited')
                if response.status_code != 200:
                    raise AIProviderError('provider_unavailable')
                body=bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic()>deadline or len(body)+len(chunk)>131072:
                        raise AIProviderError('provider_response_limit')
                    body.extend(chunk)
        data=json.loads(body)
        if data.get('status') != 'completed':
            raise AIProviderError('provider_incomplete')
        texts=[]
        for item in data.get('output',[]):
            if item.get('type') == 'reasoning':
                continue
            if item.get('type') != 'message' or item.get('role') != 'assistant':
                raise AIProviderError('unexpected_provider_output')
            for part in item.get('content',[]):
                if part.get('type') == 'refusal':
                    raise AIProviderError('provider_refused')
                if part.get('type') != 'output_text':
                    raise AIProviderError('unexpected_provider_output')
                texts.append(part['text'])
        if len(texts)!=1:
            raise AIProviderError('unexpected_provider_output')
        answer=validate_answer(json.loads(texts[0]),context).model_dump()
        actual_model=data.get('model','')
        if not isinstance(actual_model,str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',actual_model):
            raise AIProviderError('unexpected_provider_output')
        usage=data.get('usage',{})
        token_usage={key:usage.get(key) for key in ('input_tokens','output_tokens')
                     if type(usage.get(key)) is int and usage[key]>=0}
        return {'answer':answer,'model':actual_model,'usage':token_usage}
    except AIProviderError:
        raise
    except httpx.HTTPError:
        raise AIProviderError('provider_unavailable') from None
    except (ValueError,TypeError,KeyError,AttributeError):
        raise AIProviderError('invalid_provider_output') from None
