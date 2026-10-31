"""学生必做 D1。模型给的字符串不能直接 eval/exec，也不能作为文件路径。"""
import json

from core import StudentTask, result
from tools.schemas import validate

def _reject_constant(token):
    """json.loads 默认接受 NaN/Infinity；这里把它们变成解析失败。"""
    raise ValueError('non-finite number not allowed: '+token)

def _allowed(session):
    """本会话可见的工具白名单：名称 -> 参数 schema。"""
    return {spec['function']['name']: spec['function']['parameters'] for spec in session.schemas}

def dispatch(session,call):
    """call 是 {id,type:'function',function:{name,arguments:'JSON 字符串'}}。
    1. 检查 ID/type/工具名在 session.schemas 白名单；
    2. json.loads(arguments)，必须是 object；禁止 NaN/Infinity；
    3. 调用 tools.schemas.validate(schema,args) 校验嵌套字段/类型/额外字段；
    4. 只调用 session.execute(name,args)；校验失败也要返回结构化 ERROR。
    所有错误作为观察返回，不伪装 OK。不要吞掉 StudentTask。
    """
    if not isinstance(call,dict): return result('ERROR',code='MALFORMED_CALL')
    call_id=call.get('id')
    if not isinstance(call_id,str) or not call_id.strip(): return result('ERROR',code='MISSING_CALL_ID')
    if call.get('type')!='function': return result('ERROR',code='BAD_CALL_TYPE',call_id=call_id)
    function=call.get('function')
    if not isinstance(function,dict): return result('ERROR',code='MALFORMED_FUNCTION',call_id=call_id)
    name=function.get('name')
    allowed=_allowed(session)
    if not isinstance(name,str) or name not in allowed:
        return result('ERROR',code='TOOL_NOT_ALLOWED',call_id=call_id,tool=name)
    raw=function.get('arguments')
    if not isinstance(raw,str):
        return result('ERROR',code='ARGUMENTS_NOT_JSON_STRING',call_id=call_id,tool=name)
    try:
        args=json.loads(raw,parse_constant=_reject_constant)
    except ValueError:
        return result('ERROR',code='INVALID_JSON_ARGUMENTS',call_id=call_id,tool=name)
    if not isinstance(args,dict):
        return result('ERROR',code='ARGUMENTS_NOT_OBJECT',call_id=call_id,tool=name)
    try:
        validate(allowed[name],args)
    except (ValueError,TypeError,KeyError):
        return result('ERROR',code='SCHEMA_VALIDATION_FAILED',call_id=call_id,tool=name)
    return session.execute(name,args)
