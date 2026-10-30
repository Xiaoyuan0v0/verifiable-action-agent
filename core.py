"""Small shared contracts. These persist through all four labs."""
import hashlib
import json
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATUSES={'COMPLETED','WAITING_USER','INSUFFICIENT_EVIDENCE','POLICY_BLOCKED','TOOL_FAILED','BUDGET_EXCEEDED'}

class BudgetExceeded(RuntimeError): pass
class StudentTask(NotImplementedError): pass
class ProviderError(RuntimeError):
    def __init__(self,code,retryable=False):
        super().__init__(code); self.code=code; self.retryable=retryable

def canonical(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp'); temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(temp,0o600); temp.replace(path)

def rule(code,verdict,reason,**details):
    assert verdict in {'PASS','FAIL','UNKNOWN'}
    return {'rule':code,'verdict':verdict,'reason':reason,'details':details}

def combine(results):
    verdict='FAIL' if any(r['verdict']=='FAIL' for r in results) else 'UNKNOWN' if any(r['verdict']=='UNKNOWN' for r in results) else 'PASS'
    return {'verdict':verdict,'rules':results}

def safe_rules(functions,*args):
    results=[]
    for f in functions:
        try: results.append(f(*args))
        except StudentTask: results.append(rule(f.__name__,'UNKNOWN','STUDENT_TODO: 此规则尚未实现'))
        except (KeyError,TypeError,ValueError,IndexError,ArithmeticError): results.append(rule(f.__name__,'UNKNOWN','规则所需字段缺失、类型不正确或金额无法计算'))
    return combine(results)

def result(status,data=None,code=None,**meta):
    assert status in {'OK','ERROR','UNKNOWN'}
    return {'status':status,'data':data,'code':code,**meta}

def visible(value):
    """Redact exported logs; keep in-memory continuation messages intact."""
    if isinstance(value,dict):
        return {k:('[REDACTED]' if k.lower() in {'authorization','api_key','reasoning_content','reasoning','thinking','reasoning_details'} else visible(v)) for k,v in value.items()}
    if isinstance(value,list): return [visible(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'<think>.*?</think>','[THINKING OMITTED]',value,flags=re.S)
        # If a response was truncated inside a think block, do not log its tail.
        value=re.sub(r'<think>.*','[THINKING OMITTED]',value,flags=re.S)
        for key in ('COURSE_API_KEY','DEEPSEEK_API_KEY','MINIMAX_API_KEY','KIMI_API_KEY'):
            secret=os.getenv(key)
            if secret: value=value.replace(secret,'[REDACTED]')
        return value
    return value
