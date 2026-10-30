"""任务 L1：实现模型请求、工具执行与结果反馈的循环。"""
from core import StudentTask

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
    raise StudentTask('TODO L1: 实现 agent/loop.py:run')
