"""固定一轮或两轮接入探针，不是业务 Agent，也不替代学生手写 loop。"""
import argparse
import json
import math
from pathlib import Path
import secrets
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import ROOT,ProviderError,visible,write_json
from providers.client import Client
from state.session import load_config
from tools.schemas import spec,obj,S

def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',default='config.local.json'); p.add_argument('--tools',action='store_true'); a=p.parse_args()
    cfg=load_config(a.config)
    # Explicitly tiny probe cap, all attempts are visible; transport never retries.
    calls=[]; price=cfg['pricing']; max_cost=cfg['limits']['max_cost_cny']
    if any(type(price[k]) not in (int,float) or not math.isfinite(price[k]) or price[k]<0 for k in ('input_cny_per_million','output_cny_per_million')): raise ValueError('先填人民币 token 单价')
    if not price.get('source_url','').startswith('https://') or price.get('verified_on','').startswith('FILL'): raise ValueError('先填价格核验日期与来源')
    client=Client(cfg); reserved_total=0.0
    started=time.monotonic()
    nonce=secrets.token_hex(8)
    tool=[spec('read_probe','读取由本地程序生成的接入探针值。',obj({'label':S}))]
    messages=[{'role':'user','content':'请调用 read_probe，label 填 lab1。收到结果后准确复述返回的 nonce。' if a.tools else '请只回答：API connection OK'}]
    path=ROOT/'runs'/f"smoke-{time.time_ns()}"/'probe.json'
    def ask():
        nonlocal reserved_total
        remaining=cfg['limits']['active_seconds']-(time.monotonic()-started)
        size=len(json.dumps({'messages':messages,'tools':tool if a.tools else []},ensure_ascii=False).encode())
        if len(calls)>=cfg['limits']['model_calls'] or remaining<=0 or size>cfg['limits']['max_context_bytes']: raise ValueError('探针达到调用、时间或上下文上限')
        reserve=(size*price['input_cny_per_million']+cfg['limits']['max_output_tokens']*price['output_cny_per_million'])/1e6
        if reserved_total+reserve>max_cost: raise ValueError('探针预算不足；未继续调用')
        reserved_total+=reserve
        start=time.monotonic()
        try: r=client.complete(messages,tool if a.tools else [],min(remaining,cfg['limits']['request_timeout_seconds']))
        except ProviderError as e:
            calls.append({'error':e.code,'usage_unknown':True}); write_json(path,visible({'mode':'live','probe_only':True,'calls':calls})); raise
        calls.append({'response':r,'seconds':time.monotonic()-start,'reserved_cny':reserve})
        write_json(path,visible({'mode':'live','probe_only':True,'provider':cfg['provider'],'model':cfg['profiles'][cfg['provider']]['model'],'calls':calls}))
        if r['finish_reason']=='length': raise ValueError('模型输出被截断，不能算探针通过')
        return r
    first=ask()
    if a.tools:
        message=first['message']; requests=message.get('tool_calls') or []
        if len(requests)!=1 or requests[0]['function']['name']!='read_probe': raise ValueError('未产生预期工具请求，见 probe.json')
        params=json.loads(requests[0]['function']['arguments'])
        if params!={'label':'lab1'}: raise ValueError('工具参数不符合探针约定')
        messages.append(message)
        messages.append({'role':'tool','tool_call_id':requests[0]['id'],'content':json.dumps({'nonce':nonce})})
        second=ask()
        if second['message'].get('tool_calls') or nonce not in (visible(second['message']).get('content') or ''): raise ValueError('第二次响应未复述真实工具返回，不能算通过')
    elif not first['message'].get('content'): raise ValueError('未返回文本')
    shown=second if a.tools else first
    print('模型回答：'+str(visible(shown['message']).get('content') or ''))
    print('PASS 接入检查。记录：'+str(path))

if __name__=='__main__':
    try: main()
    except (ValueError,ProviderError,OSError) as e: print('ERROR: '+str(e),file=sys.stderr); sys.exit(1)
