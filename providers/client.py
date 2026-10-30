"""OpenAI-compatible wire transport; no agent loop, no automatic retries."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from core import ProviderError

BASES={'deepseek':'https://api.deepseek.com','minimax':'https://api.minimax.cn/v1','kimi':'https://api.moonshot.cn/v1'}
EXTRA_FIELDS={'temperature','top_p','thinking','reasoning_effort','reasoning_split','parallel_tool_calls'}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ProviderError('REDIRECT_REFUSED')

class Client:
    def __init__(self,config,opener=None):
        p=config['provider']; self.profile=config['profiles'][p]
        self.base=self.profile['base_url'].rstrip('/')
        if self.base!=BASES[p] or urlparse(self.base).scheme!='https': raise ValueError('使用所选中国站官方 base_url；不混用 Key')
        self.key=os.environ.get('COURSE_API_KEY')
        if not self.key: raise ValueError('缺少 COURSE_API_KEY 环境变量')
        if not self.profile['model'] or self.profile['model'].startswith('FILL_'): raise ValueError('先在 config.local.json 填写当前可用 model ID')
        self.opener=opener or build_opener(NoRedirect())
        self.config=config

    def complete(self,messages,tools,timeout):
        extra=self.profile.get('extra',{})
        if set(extra)-EXTRA_FIELDS: raise ValueError('extra 包含未经支持的字段')
        capkey=self.profile.get('output_limit_field','max_tokens')
        if capkey not in ('max_tokens','max_completion_tokens'): raise ValueError('错误的生成长度字段')
        payload={'model':self.profile['model'],'messages':messages,'stream':False,capkey:self.config['limits']['max_output_tokens'],**extra}
        if tools: payload['tools']=tools
        req=Request(self.base+'/chat/completions',data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key},method='POST')
        try:
            with self.opener.open(req,timeout=timeout) as response:
                raw=response.read(4_000_001)
            if len(raw)>4_000_000: raise ProviderError('RESPONSE_TOO_LARGE')
            body=json.loads(raw)
        except HTTPError as e:
            # Never print HTTP bodies/headers: they may contain account information.
            raise ProviderError(f'HTTP_{e.code}',e.code in (408,429,500,502,503,504)) from None
        except (URLError,TimeoutError,OSError): raise ProviderError('NETWORK_OR_TIMEOUT',True) from None
        except (json.JSONDecodeError,UnicodeError): raise ProviderError('INVALID_RESPONSE_JSON') from None
        if not isinstance(body,dict) or 'error' in body: raise ProviderError('SERVICE_ERROR')
        try:
            choice=body['choices'][0]; message=choice['message']; finish=choice['finish_reason']
            if not isinstance(message,dict) or message.get('role')!='assistant': raise ValueError()
            if not isinstance(body.get('usage',{}),dict): raise ValueError()
        except (KeyError,IndexError,TypeError,ValueError): raise ProviderError('INVALID_RESPONSE_SHAPE') from None
        # Preserve the complete assistant message for continuation, including
        # tool_call IDs and provider-specific reasoning fields. Only logs redact it.
        return {'message':message,'finish_reason':finish,'usage':body.get('usage',{}),'response_id':body.get('id')}
