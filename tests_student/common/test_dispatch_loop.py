import json
import unittest
from core import canonical,result,BudgetExceeded
from tools.schemas import specs
from tools.dispatcher import dispatch
from agent.loop import run

class FakeSession:
    route='travel'
    def __init__(self):
        self.schemas=specs('travel'); self.messages=[]; self.executed=[]; self.asked=0
    def save(self): pass
    def ask(self):
        self.asked+=1
        if self.asked==1:
            return {'message':{'role':'assistant','content':None,'reasoning_content':'keep-me','tool_calls':[{'id':'id1','type':'function','function':{'name':'get_option','arguments':'{"option_id":"abc"}'}}]},'finish_reason':'tool_calls','usage':{}}
        assert self.messages[0]['reasoning_content']=='keep-me'
        assert self.messages[1]['tool_call_id']=='id1'
        assert json.loads(self.messages[1]['content'])['status']=='UNKNOWN'
        return {'message':{'role':'assistant','content':canonical({'status':'INSUFFICIENT_EVIDENCE','message':'条目未找到，不编造'})},'finish_reason':'stop','usage':{}}
    def execute(self,name,args): self.executed.append((name,args)); return result('UNKNOWN',code='NOT_FOUND')
    def append_tool(self,i,out): self.messages.append({'role':'tool','tool_call_id':i,'content':canonical(out)})
    def end(self,status,message): return {'status':status,'message':message}

class StudentCommonTests(unittest.TestCase):
    def call(self,name,args): return {'id':'c1','type':'function','function':{'name':name,'arguments':args}}
    def test_dispatch_rejects_unknown_and_extra(self):
        s=FakeSession()
        self.assertEqual(dispatch(s,self.call('shell','{}'))['status'],'ERROR')
        self.assertEqual(dispatch(s,self.call('get_option','{"option_id":"a","user_id":"other"}'))['status'],'ERROR')
        self.assertEqual(s.executed,[])
    def test_dispatch_rejects_malformed_json(self):
        s=FakeSession(); self.assertEqual(dispatch(s,self.call('get_option','not json'))['status'],'ERROR')
    def test_loop_uses_return_and_preserves_message(self):
        s=FakeSession(); self.assertEqual(run(s)['status'],'INSUFFICIENT_EVIDENCE'); self.assertEqual(s.asked,2)
    def test_loop_rejects_truncated_tool(self):
        s=ScriptedSession([{'message':{'role':'assistant','tool_calls':[self.call('get_option','{"option_id":"x"}')]},'finish_reason':'length'}])
        self.assertEqual(run(s)['status'],'TOOL_FAILED'); self.assertEqual(s.executed,[])
    def test_loop_retail_batch_returns_all_ids_without_execution(self):
        calls=[self.call('get_order','{"order_id":"x"}'),{**self.call('get_order','{"order_id":"y"}'),'id':'c2'}]
        s=ScriptedSession([{'message':{'role':'assistant','content':None,'tool_calls':calls},'finish_reason':'tool_calls'},final('TOOL_FAILED')],route='retail')
        run(s); observed=[m for m in s.messages if m['role']=='tool']
        self.assertEqual({m['tool_call_id'] for m in observed},{'c1','c2'}); self.assertEqual(len(observed),2)
        self.assertTrue(all(json.loads(m['content'])['status']=='ERROR' for m in observed));self.assertEqual(s.executed,[])
    def test_loop_retail_user_text_plus_tool_is_rejected(self):
        s=ScriptedSession([{'message':{'role':'assistant','content':'我现在提交','tool_calls':[self.call('get_order','{"order_id":"x"}')]},'finish_reason':'tool_calls'},final('TOOL_FAILED')],route='retail')
        run(s);self.assertEqual(s.executed,[])
    def test_loop_waiting_user_stops(self):
        s=ScriptedSession([final('WAITING_USER')]); self.assertEqual(run(s)['status'],'WAITING_USER');self.assertEqual(s.asked,1)
    def test_loop_reused_id_stops(self):
        msg={'message':{'role':'assistant','content':None,'tool_calls':[self.call('get_option','{"option_id":"x"}')]},'finish_reason':'tool_calls'}
        s=ScriptedSession([msg,msg]); self.assertEqual(run(s)['status'],'TOOL_FAILED');self.assertEqual(len(s.executed),1)
    def test_loop_budget_stops(self):
        s=ScriptedSession([]);self.assertEqual(run(s)['status'],'BUDGET_EXCEEDED')
    def test_dispatch_rejects_non_object_or_nonfinite(self):
        s=FakeSession()
        for args in ('[]','{"option_id":true}','{"option_id":NaN}'):
            self.assertEqual(dispatch(s,self.call('get_option',args))['status'],'ERROR')
        self.assertEqual(s.executed,[])

def final(status):
    return {'message':{'role':'assistant','content':canonical({'status':status,'message':'public protocol fixture'})},'finish_reason':'stop'}

class ScriptedSession(FakeSession):
    def __init__(self,responses,route='travel'):
        super().__init__();self.responses=responses;self.route=route;self.schemas=specs(route)
    def ask(self):
        if self.asked>=len(self.responses): raise BudgetExceeded('script exhausted')
        out=self.responses[self.asked];self.asked+=1;return out

if __name__=='__main__': unittest.main()
