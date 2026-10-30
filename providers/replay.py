"""离线调试用固定响应。保存记录的 ID 从先前工具返回中取得。"""
from copy import deepcopy
import json
from core import ROOT, read_json, ProviderError

class ReplayClient:
    def __init__(self,session): self.session=session
    def complete(self,messages,tools,timeout):
        steps=read_json(ROOT/f'eval/replays/{self.session.route}_{self.session.case}.json')
        index=self.session.state['model_calls']-1
        if index>=len(steps): raise ProviderError('REPLAY_EXHAUSTED')
        answer=deepcopy(steps[index])
        tokens={}
        for m in messages:
            if m.get('role')!='tool': continue
            try: data=json.loads(m['content']).get('data')
            except (ValueError,TypeError): continue
            if isinstance(data,dict):
                for key,label in [('proposal_id','$PROPOSAL'),('itinerary_id','$ITINERARY')]:
                    if key in data: tokens[label]=data[key]
        def sub(v):
            if isinstance(v,dict): return {k:sub(x) for k,x in v.items()}
            if isinstance(v,list): return [sub(x) for x in v]
            if isinstance(v,str):
                for token,actual in tokens.items(): v=v.replace(token,actual)
            return v
        return sub(answer)
