import io
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from copy import deepcopy
import core
import state.session as state_module
from core import result,visible,BudgetExceeded,ProviderError
from providers.client import Client
from state.session import Session,load_config
from tools.schemas import validate,PLAN
from scripts.check_episode import assess

class InfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        # Small copies work on Windows without symlink/admin permissions.
        for name in ('data/source_manifest.json','config.example.json','agent/loop.py','tools/dispatcher.py','domain_rules/travel.py','domain_rules/retail.py'):
            destination=self.root/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(core.ROOT/name,destination)
        self.patch=patch.object(state_module,'ROOT',self.root); self.patch.start()
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()
    def session(self,route='retail',case='standard',ep='test'): return Session(ep,route,case,config=load_config())

    def test_no_read_before_identify(self):
        s=self.session(); out=s.execute('get_order',{'order_id':s.env.task['order_id']}); self.assertEqual(out['code'],'IDENTIFY_FIRST')
    def test_scope_not_selected_by_model(self):
        s=self.session(); other=next(u for uid,u in s.env.db['users'].items() if uid!=s.env.scope)
        self.assertEqual(s.execute('identify_customer',{'email':other['email']})['code'],'SCOPE_DENIED')
    def test_no_model_confirmation_boolean(self):
        s=self.session(); out=s.execute('apply_action',{'proposal_id':'x','confirmed':True}); self.assertEqual(out['status'],'ERROR'); self.assertIsNone(s.state['written'])
    def test_unknown_tool_is_rejected(self):
        s=self.session(); self.assertEqual(s.execute('shell',{'cmd':'anything'})['code'],'TOOL_NOT_ALLOWED')
    def test_completed_requires_write_and_readback(self):
        s=self.session(); self.assertEqual(s.end('COMPLETED','模型自报成功')['status'],'TOOL_FAILED')
    def test_resume_budget_is_cumulative(self):
        s=self.session(case='limit'); s.ask(); s.end('WAITING_USER','等待回复')
        s2=Session('test',resume=True)
        self.assertEqual(s2.state['model_calls'],1)
        with self.assertRaises(BudgetExceeded): s2.ask()
    def test_episode_cannot_be_overwritten(self):
        self.session()
        with self.assertRaises(ValueError): self.session()
    def test_directory_traversal_rejected(self):
        with self.assertRaises(ValueError): self.session(ep='../oops')
    def test_required_field_and_extra_field(self):
        s=self.session()
        self.assertEqual(s.execute('get_order',{})['status'],'ERROR')
        self.assertEqual(s.execute('get_order',{'order_id':'x','user_id':'other'})['status'],'ERROR')
    def test_bool_not_integer(self):
        with self.assertRaises(ValueError): validate({'type':'integer','minimum':1},True)
    def test_empty_and_nonfinite_not_allowed(self):
        with self.assertRaises(ValueError): validate({'type':'string','minLength':1},'')
        with self.assertRaises(ValueError): validate({'type':'number'},float('nan'))
    def test_log_redaction_keeps_continuation_original(self):
        raw={'role':'assistant','content':'<think>private</think>visible','reasoning_content':'private','tool_calls':[{'id':'call1'}]}
        with patch.dict(os.environ,{'COURSE_API_KEY':'example-secret-not-real'}):
            red=visible({**raw,'x':'example-secret-not-real'})
        self.assertNotIn('private',json.dumps(red)); self.assertNotIn('example-secret-not-real',json.dumps(red)); self.assertEqual(raw['reasoning_content'],'private')
    def test_unclosed_thinking_redacted(self): self.assertEqual(visible('ok<think>private'),'ok[THINKING OMITTED]')
    def test_api_roundtrip_preserves_complete_message(self):
        cfg=load_config(); cfg['profiles']['deepseek']['model']='test-model'
        msg={'role':'assistant','content':None,'reasoning_content':'required-for-roundtrip','tool_calls':[{'id':'unique1','type':'function','function':{'name':'read','arguments':'{}'}}]}
        class Opener:
            def open(self,req,timeout):
                self.payload=json.loads(req.data)
                return io.BytesIO(json.dumps({'choices':[{'message':msg,'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':2,'completion_tokens':3}}).encode())
        op=Opener()
        with patch.dict(os.environ,{'COURSE_API_KEY':'fake-test-key'}):
            c=Client(cfg,op); reply=c.complete([{'role':'user','content':'x'}],[],30)
            c.complete([reply['message'],{'role':'tool','tool_call_id':'unique1','content':'42'}],[],30)
        self.assertEqual(op.payload['messages'][0],msg)
        self.assertEqual(op.payload['messages'][1]['tool_call_id'],'unique1')
    def test_mock_logs_are_explicitly_labeled(self):
        s=self.session(); s.ask()
        text=(self.root/'runs/test/events.jsonl').read_text()
        self.assertIn('"mode":"mock"',text); self.assertIn('COURSE_SCRIPT_NOT_MODEL',text)
    def test_http_errors_are_normalized_without_retry_or_body(self):
        cfg=load_config(); cfg['profiles']['deepseek']['model']='test-model'
        for status,retryable in [(401,False),(402,False),(429,True),(503,True)]:
            class Opener:
                count=0
                def open(self,req,timeout):
                    self.count+=1
                    raise HTTPError(req.full_url,status,'private body',{},None)
            op=Opener()
            with patch.dict(os.environ,{'COURSE_API_KEY':'fake-test-key'}):
                c=Client(cfg,op)
                with self.assertRaises(ProviderError) as error: c.complete([],[],30)
            self.assertEqual(error.exception.retryable,retryable); self.assertEqual(op.count,1)
            self.assertNotIn('private',str(error.exception))
    def test_three_provider_payloads_respect_separate_config(self):
        for provider,field in [('deepseek','max_tokens'),('minimax','max_completion_tokens'),('kimi','max_tokens')]:
            cfg=load_config(); cfg['provider']=provider; cfg['profiles'][provider]['model']='test-model'
            class Opener:
                def open(self,req,timeout):
                    self.url=req.full_url; self.payload=json.loads(req.data)
                    return io.BytesIO(json.dumps({'choices':[{'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}]}).encode())
            op=Opener()
            with patch.dict(os.environ,{'COURSE_API_KEY':'fake-test-key'}): Client(cfg,op).complete([],[],30)
            self.assertIn(field,op.payload); self.assertNotIn('temperature',op.payload)
            self.assertEqual(op.url,cfg['profiles'][provider]['base_url']+'/chat/completions')
    def test_tool_budget_blocks_before_execution(self):
        s=self.session(); s.config['limits']['tool_calls']=0
        with self.assertRaises(BudgetExceeded): s.execute('identify_customer',{'email':s.env.task['email']})
    def test_deadline_blocks_before_execution(self):
        s=self.session(); s.config['limits']['active_seconds']=0
        with self.assertRaises(BudgetExceeded): s.ask()
    def test_terminal_label_alone_does_not_pass_case(self):
        for case,status in [('blocked','POLICY_BLOCKED'),('missing','INSUFFICIENT_EVIDENCE'),('failure','TOOL_FAILED')]:
            s=self.session(case=case,ep=case);s.ask();s.end(status,'没有查询或执行，仅输出状态')
            self.assertFalse(assess(s.dir,self.root/'runs'/case/'events.jsonl')['passed'])
    def test_failed_case_checks_actual_business_bytes(self):
        s=self.session(case='blocked');s.ask()
        s.execute('identify_customer',{'email':s.env.task['email']})
        s.execute('get_order',{'order_id':s.env.task['order_id']});s.end('POLICY_BLOCKED','状态不允许')
        events=self.root/'runs/test/events.jsonl'
        self.assertTrue(assess(s.dir,events)['passed'])
        s.env.db['orders'][s.env.task['order_id']]['status']='cancelled';s.env.persist()
        checks=assess(s.dir,events)['checks'];self.assertFalse(checks['no_unexpected_business_change'])
    def test_deepseek_example_is_configured_for_non_thinking_tools(self):
        cfg=load_config();self.assertEqual(cfg['provider'],'deepseek')
        self.assertEqual(cfg['profiles']['deepseek']['model'],'deepseek-flash')
        self.assertEqual(cfg['profiles']['deepseek']['extra']['thinking'],{'type':'disabled'})
        self.assertGreater(cfg['limits']['model_calls'],8)

if __name__=='__main__': unittest.main()
