"""任务 L1：实现模型请求、工具执行与结果反馈的循环。"""
import json

from core import BudgetExceeded, ProviderError, StudentTask, result
from tools.dispatcher import dispatch

# 可重试的传输层错误最多追加一次尝试；认证/余额错误立即停止。
RETRYABLE_CODES={'NETWORK_OR_TIMEOUT','HTTP_408','HTTP_429','HTTP_500','HTTP_502','HTTP_503','HTTP_504'}
MAX_PROVIDER_RETRIES=1
# 允许模型在收到格式错误反馈后自我修正的次数上限；重试同样计入预算。
MAX_FORMAT_RETRIES=2

def _final_status(message):
    """从模型的最终文本解析 status/message；不是协议 JSON 就不能算完成。"""
    if not isinstance(message,str): return None,None
    text=message.strip()
    if text.startswith('```'):
        # 协议明确不使用 Markdown 围栏；这里只做一次宽松清理用于识别，仍需校验字段。
        lines=[line for line in text.splitlines() if not line.strip().startswith('```')]
        text='\n'.join(lines).strip()
    try:
        data=json.loads(text)
    except ValueError:
        return None,None
    if not isinstance(data,dict): return None,None
    status=data.get('status')
    if not isinstance(status,str): return None,None
    detail=data.get('message')
    if not isinstance(detail,str): detail=''
    return status,detail

def _reject_tool_calls(session,calls,reason):
    """整个批次拒绝：每个调用 ID 都要有一条 ERROR 观察，且不执行任何工具。"""
    for call in calls:
        call_id=call.get('id') if isinstance(call,dict) else None
        session.append_tool(call_id,result('ERROR',code='BATCH_REJECTED',reason=reason,tool=call.get('function',{}).get('name') if isinstance(call,dict) and isinstance(call.get('function'),dict) else None))
    return reason

def _call_ids(calls):
    ids=[]
    for call in calls:
        ids.append(call.get('id') if isinstance(call,dict) else None)
    return ids

def _call_signature(call):
    """一次工具调用的身份：ID + 工具名 + 参数。

    只用 ID 判重会误杀「同一个 ID 换一个动作」的合法后续调用；
    真正需要拦的是「完全相同的一次调用」反复出现，即模型在原地打转。
    """
    if not isinstance(call,dict): return (None,None,None)
    fn=call.get('function')
    if not isinstance(fn,dict): return (call.get('id'),None,None)
    name=fn.get('name')
    args=fn.get('arguments')
    return (call.get('id'),name if isinstance(name,str) else repr(name),args if isinstance(args,str) else repr(args))

def run(session):
    """返回 session.end(status, message) 的字典。
    可用接口：session.ask(), session.execute(name,args), session.messages,
    session.schemas, session.route, session.append_tool(call_id,result), session.end().
    dispatcher.dispatch(session, call) 也由学生实现。

    实现顺序：ask/execute 检查预算 → ask → 保留完整 assistant 消息
    → 区分 tool_calls 与最终 JSON → 对每个调用分派/回传 → 再次 ask。
    零工具时解析 {status,message}；不把普通聊天文本自动判为完成。
    length/损坏 JSON/无效动作不得 COMPLETED。允许有限纠错/重试，但算预算。
    retail 一次最多一个工具，不能同时对用户说话；违规批次全部拒绝并回传每个 ID。
    捕获 BudgetExceeded，保存 BUDGET_EXCEEDED；ProviderError 按是否可重试处理。
    WAITING_USER 必须返回，不能 while 循环等“yes”。COMPLETED 仍受读回核验约束。
    详细伪代码、输入输出样例及验收在 tutorial 中。
    """
    provider_retries=0
    format_retries=0
    seen_calls=set()

    while True:
        # 1) 请求模型。预算上限由 session.ask() 统一检查并抛出 BudgetExceeded。
        try:
            response=session.ask()
        except BudgetExceeded as e:
            return session.end('BUDGET_EXCEEDED','预算上限触发，未再发起模型请求：'+str(e))
        except ProviderError as e:
            if e.retryable and e.code in RETRYABLE_CODES and provider_retries<MAX_PROVIDER_RETRIES:
                provider_retries+=1
                continue
            return session.end('TOOL_FAILED','模型服务调用失败：'+str(e.code))

        message=response.get('message')
        if not isinstance(message,dict) or message.get('role')!='assistant':
            return session.end('TOOL_FAILED','模型返回的消息结构无效')

        # 2) 保留完整 assistant 消息（含 tool_call ID 与推理续轮字段）。
        session.messages.append(message)

        finish=response.get('finish_reason')
        tool_calls=message.get('tool_calls')
        if tool_calls is not None and not isinstance(tool_calls,list):
            return session.end('TOOL_FAILED','模型返回的 tool_calls 不是列表')
        tool_calls=tool_calls or []

        if finish=='length':
            # 被长度截断：可能只有半截工具调用，不能执行，也不能判定完成。
            return session.end('TOOL_FAILED','模型响应被长度上限截断，未执行任何工具')

        if tool_calls:
            # 3) 工具请求分支。
            ids=_call_ids(tool_calls)
            if any(not isinstance(i,str) or not i.strip() for i in ids):
                return session.end('TOOL_FAILED','模型返回的工具调用缺少有效 ID')
            # 判重键是「ID + 工具名 + 参数」：同一个 ID 换一个动作是合法的后续调用，
            # 完全相同的一次调用重复出现，才是模型在原地打转。
            signatures=[_call_signature(call) for call in tool_calls]
            repeated=[sig for sig in signatures if signatures.count(sig)>1 or sig in seen_calls]
            if repeated:
                return session.end('TOOL_FAILED','模型重复请求了同一个工具调用：'+','.join(sorted(set(str(sig[0]) for sig in repeated))))

            if session.route=='retail':
                if len(tool_calls)>1:
                    _reject_tool_calls(session,tool_calls,'retail 每轮只允许一个工具调用，整个批次已拒绝')
                    if format_retries<MAX_FORMAT_RETRIES:
                        format_retries+=1
                        continue
                    return session.end('TOOL_FAILED','retail 批次含多个工具调用，已回传错误')
                if message.get('content'):
                    _reject_tool_calls(session,tool_calls,'retail 有工具调用时不能同时对用户说话')
                    if format_retries<MAX_FORMAT_RETRIES:
                        format_retries+=1
                        continue
                    return session.end('TOOL_FAILED','retail 同一轮既发起工具调用又向用户作答，已回传错误')

            # 只把真正进入分派的调用记为已见；被整批拒绝的调用没有执行，
            # 模型修正批次后沿用同一 ID 重发仍是合法修正。
            seen_calls.update(signatures)

            # 4) 逐个分派并回传。每个调用 ID 都要有一条观察，模型才能看到结果。
            for call in tool_calls:
                call_id=call.get('id')
                try:
                    outcome=dispatch(session,call)
                except BudgetExceeded as e:
                    return session.end('BUDGET_EXCEEDED','工具执行预算上限触发：'+str(e))
                except StudentTask:
                    raise
                except Exception:
                    # 分派内部错误不能伪装成成功。
                    outcome=result('ERROR',code='DISPATCH_INTERNAL_ERROR')
                if not isinstance(outcome,dict):
                    outcome=result('ERROR',code='DISPATCH_RETURNED_NON_OBJECT')
                session.append_tool(call_id,outcome)
            continue

        # 5) 无工具：必须解析出协议 JSON 才能结束。
        status,detail=_final_status(message.get('content'))
        if status is None:
            format_retries+=1
            if format_retries<=MAX_FORMAT_RETRIES:
                # 给模型一次格式纠正机会；这次请求同样计入预算。
                session.messages.append({'role':'user','content':'最终回复必须是 JSON 对象 {"status":"终态","message":"解释"}，status 取值仅限 COMPLETED, WAITING_USER, INSUFFICIENT_EVIDENCE, POLICY_BLOCKED, TOOL_FAILED, BUDGET_EXCEEDED。请重新输出。'})
                continue
            return session.end('TOOL_FAILED','模型最终回复不是约定的协议 JSON，不能判定为完成')
        if status not in {'COMPLETED','WAITING_USER','INSUFFICIENT_EVIDENCE','POLICY_BLOCKED','TOOL_FAILED','BUDGET_EXCEEDED'}:
            return session.end('TOOL_FAILED','模型给出的终态不在允许集合内：'+status)
        # 6) COMPLETED 仍受 session.end() 的读回核验约束（核验不通过会被改写为 TOOL_FAILED）。
        return session.end(status,detail)
