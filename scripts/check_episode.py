"""检查任务终态、相关工具事件和磁盘上的业务结果。"""
import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import ROOT,read_json,digest
from state.session import episode_path
from tools.environment import Environment,fresh_database,target_variant

def objects(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from objects(v)
    elif isinstance(value,list):
        for v in value: yield from objects(v)

def strings(value):
    if isinstance(value,str): yield value
    elif isinstance(value,dict):
        for v in value.values(): yield from strings(v)
    elif isinstance(value,list):
        for v in value: yield from strings(v)

def id_arguments(value):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.endswith('_id') and isinstance(v,str): yield v
            else: yield from id_arguments(v)
    elif isinstance(value,list):
        for v in value: yield from id_arguments(v)

def assess(directory,events_path):
    s=read_json(directory/'checkpoint.json')
    events=[json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    route,case=s['route'],s['case']
    expected={'standard':'COMPLETED','changed':'COMPLETED' if route=='travel' else 'POLICY_BLOCKED','missing':'INSUFFICIENT_EVIDENCE','blocked':'POLICY_BLOCKED','failure':'TOOL_FAILED','limit':'BUDGET_EXCEEDED'}[case]
    results=[e['data'] for e in events if e['event']=='tool_result']
    previous=[]; dependent=False
    for row in results:
        ids=set(id_arguments(row['arguments']))
        if any(name!=row['name'] and ids.intersection(values) for name,values in previous): dependent=True
        if row['result'].get('status')=='OK': previous.append((row['name'],set(strings(row['result'].get('data')))))
    limits=s['config']['limits']
    baseline=fresh_database(route,case); business=read_json(directory/'business.json')
    checks={'terminal_matches_case':s['status']==expected,'within_call_limits':s['model_calls']<=limits['model_calls'] and s['tool_calls']<=limits['tool_calls'],'model_request_recorded':s['model_calls']>0 and sum(e['event']=='model_request' for e in events)==s['model_calls'],'tool_count_matches_log':len(results)==s['tool_calls'],'no_false_success_without_write':s['status']!='COMPLETED' or bool(s.get('written'))}
    write_name='save_itinerary' if route=='travel' else 'apply_action'
    writes=[r for r in results if r['name']==write_name]
    seen=[node for r in results if r['result'].get('status')=='OK' for node in objects(r['result'].get('data'))]
    confirmed=set();approved_write=False
    for e in events:
        if e['event']=='user_confirmation' and e['data'].get('actor')=='host_cli': confirmed.add(e['data'].get('proposal_id'))
        if e['event']=='tool_result' and e['data']['name']=='apply_action' and e['data']['arguments'].get('proposal_id') in confirmed: approved_write=True
    if expected=='COMPLETED':
        host=SimpleNamespace(dir=directory,route=route,state=s,case=case)
        checks['persisted_business_state_matches_readback']=Environment(host).verify_completion()
        checks['different_tools_with_observable_id_dependency']=dependent
        checks['successful_write_event']=any(r['result'].get('status')=='OK' for r in writes)
        if route=='retail':
            checks['matching_confirmation_before_write']=approved_write
            permitted=deepcopy(baseline);oid=baseline['task']['order_id'];row=business.get('orders',{}).get(oid,{})
            permitted['orders'][oid].update(status='exchange requested',course_exchange=row.get('course_exchange'),record_version=baseline['orders'][oid]['record_version']+1)
            checks['only_requested_order_changed']=business==permitted
        else:
            other=deepcopy(business);other.pop('itineraries',None)
            checks['source_business_facts_unchanged']=other==baseline
    else:
        checks['no_unexpected_business_change']=not bool(s.get('written')) and business==baseline
        if case=='failure':
            checks['write_failure_was_actually_observed']=any(r['result'].get('code')=='INJECTED_WRITE_FAILURE' for r in writes)
            if route=='retail': checks['matching_confirmation_before_attempt']=approved_write
        elif case=='limit':
            checks['model_limit_actually_reached']=s['model_calls']==limits['model_calls']
        elif route=='travel':
            if case=='missing':
                checks['missing_price_observed']=any(n.get('kind')=='lodging' and n.get('city')==baseline['task']['destination'] and n.get('price_usd') is None for n in seen) or any(r['name']=='check_plan' and (r['result'].get('data') or {}).get('verdict')=='UNKNOWN' for r in results)
            elif case=='blocked':
                checks['budget_conflict_observed']=any(n.get('rule')=='TR3' and n.get('verdict')=='FAIL' for n in seen) or any(n.get('kind') in ('flight','lodging') and isinstance(n.get('price_usd'),(int,float)) and n['price_usd']>baseline['task']['budget_usd'] for n in seen)
        else:
            if case=='blocked':
                checks['prohibited_order_status_observed']=any(n.get('order_id')==baseline['task']['order_id'] and n.get('status')=='processed' for n in seen) or any(n.get('rule')=='BR1' and n.get('verdict')=='FAIL' for n in seen)
            else:
                _,variant=target_variant(baseline);wanted=None if case=='missing' else False
                checks['target_availability_observed']=any(n.get('item_id')==variant['item_id'] and 'available' in n and n['available'] is wanted for n in seen) or any(n.get('rule')=='BR2' and n.get('verdict')==('UNKNOWN' if case=='missing' else 'FAIL') for n in seen)
    return {'episode_id':s['episode_id'],'route':route,'case':case,'mode':s['mode'],'expected':expected,'actual':s['status'],'checks':checks,'passed':all(checks.values()),'pending_confirmation':s['status']=='WAITING_USER','note':'本检查结合工具事件与业务状态，并复用你编写的规则。还需运行代码测试；mock 记录表示固定模拟响应。'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--episode',required=True);a=p.parse_args()
    out=assess(episode_path(a.episode),ROOT/'runs'/a.episode/'events.jsonl')
    print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out['passed'] else 1

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,KeyError) as e: print('ERROR: '+str(e),file=sys.stderr);sys.exit(1)
