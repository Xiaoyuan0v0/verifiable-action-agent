"""Course command line. Default is offline; live network requires --mode live."""
import argparse
import json
import shutil
import sys
from datetime import datetime,timezone
from pathlib import Path
from core import ROOT,StudentTask,ProviderError,read_json,write_json,visible
from state.session import Session,episode_path,load_config
from tools.environment import CASE_NAMES

def output(value): print(json.dumps(visible(value),ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser(description='Lab 1 foundation; read ../tutorial.md first')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('doctor')
    t=sub.add_parser('task'); t.add_argument('--route',choices=['travel','retail'],required=True)
    r=sub.add_parser('run'); r.add_argument('--route',choices=['travel','retail'],required=True); r.add_argument('--case',choices=CASE_NAMES,default='standard'); r.add_argument('--mode',choices=['mock','live'],default='mock'); r.add_argument('--config'); r.add_argument('--episode',required=True); r.add_argument('--request',help='可选补充任务文字；不能改变程序绑定的主体、预算与业务约束')
    r=sub.add_parser('resume'); r.add_argument('--episode',required=True); r.add_argument('--reply',default='继续处理已确认提案；如未确认，只解释下一步。')
    for command in ('show','confirm','export','reset'):
        q=sub.add_parser(command); q.add_argument('--episode',required=True)
        if command=='confirm': q.add_argument('--proposal',required=True)
    a=p.parse_args()
    if a.cmd=='doctor':
        if sys.version_info<(3,10): raise ValueError('需要 Python 3.10 或以上')
        from scripts.prepare_data import SOURCES
        import hashlib
        for name,(_,expected) in SOURCES.items():
            assert hashlib.sha256((ROOT/'data/raw'/name).read_bytes()).hexdigest()==expected,name
        manifest=read_json(ROOT/'data/source_manifest.json')
        for row in manifest['derived']:
            assert hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest()==row['sha256'],row['file']
        todo=[]
        for f in ('agent/loop.py','tools/dispatcher.py','domain_rules/travel.py','domain_rules/retail.py'):
            if 'raise StudentTask(' in (ROOT/f).read_text(encoding='utf-8'): todo.append(f)
        output({'infrastructure':'PASS','python':sys.version.split()[0],'student_todo_files':todo,'note':'这里通过不等于实验完成；无需 Key、不发网络请求。'})
    elif a.cmd=='task': output(read_json(ROOT/f'data/derived/{a.route}.json')['task'])
    elif a.cmd in ('run','resume'):
        from agent.loop import run
        s=Session(a.episode,resume=True) if a.cmd=='resume' else Session(a.episode,a.route,a.case,a.mode,load_config(a.config))
        if a.cmd=='resume': s.messages.append({'role':'user','content':a.reply}); s.save()
        elif a.request: s.messages.append({'role':'user','content':a.request}); s.save()
        try: answer=run(s)
        except StudentTask as e:
            s.end('TOOL_FAILED','STUDENT_TODO'); print(str(e)); return 2
        output(answer)
    else:
        directory=episode_path(a.episode); state=read_json(directory/'checkpoint.json')
        if a.cmd=='show':
            output({k:state.get(k) for k in ('episode_id','session_number','mode','route','case','status','model_calls','tool_calls','active_seconds','cost_cny','pending','written','readback','final_message')})
        elif a.cmd=='confirm':
            pending=state.get('pending')
            if state['status']!='WAITING_USER' or not pending or pending['id']!=a.proposal: raise ValueError('当前没有此待确认提案')
            output(pending)
            phrase='CONFIRM '+a.proposal
            if input('核对订单、颜色、价差和支付方式；确认已列出本订单全部换货商品。输入 '+phrase+'：\n').strip()!=phrase:
                print('未确认；没有写入业务数据。'); return 1
            state['confirmation']=a.proposal
            state['messages'].append({'role':'user','content':'宿主用户明确确认具体提案 '+a.proposal+'。'})
            write_json(directory/'checkpoint.json',state)
            event={'time':datetime.now(timezone.utc).isoformat(),'episode_id':a.episode,'event':'user_confirmation','data':{'actor':'host_cli','proposal_id':a.proposal,'action':pending['action']}}
            with (ROOT/'runs'/a.episode/'events.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(event,ensure_ascii=False)+'\n')
            print('已记录具体提案确认。下一步运行 resume；累计预算不会清零。')
        elif a.cmd=='export':
            destination=ROOT/'reports/submission'/a.episode; destination.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/'runs'/a.episode/'events.jsonl',destination/'events.jsonl')
            write_json(destination/'summary.json',visible({k:state.get(k) for k in ('episode_id','mode','route','case','status','model_calls','tool_calls','active_seconds','cost_cny','usage','written','readback','final_message','code_hashes')}))
            db=read_json(directory/'business.json')
            written=state.get('written')
            if written:
                row=db.get('itineraries' if state['route']=='travel' else 'orders',{}).get(written['id'])
                write_json(destination/'artifact.json',visible(row))
            print(str(destination)); print('未导出 Key、完整续轮 messages 或私人检查点。')
        elif a.cmd=='reset':
            archive=ROOT/'state/archive'/f"{a.episode}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
            archive.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(directory),str(archive))
            print('原状态已归档：'+str(archive)); print('重跑使用新 episode；日志保留，不覆盖旧失败。')
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,AssertionError,ProviderError) as e:
        print('ERROR: '+str(e),file=sys.stderr); sys.exit(1)
