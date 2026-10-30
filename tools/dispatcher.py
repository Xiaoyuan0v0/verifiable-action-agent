"""学生必做 D1。模型给的字符串不能直接 eval/exec，也不能作为文件路径。"""
from core import StudentTask

def dispatch(session,call):
    """call 是 {id,type:'function',function:{name,arguments:'JSON 字符串'}}。
    1. 检查 ID/type/工具名在 session.schemas 白名单；
    2. json.loads(arguments)，必须是 object；禁止 NaN/Infinity；
    3. 调用 tools.schemas.validate(schema,args) 校验嵌套字段/类型/额外字段；
    4. 只调用 session.execute(name,args)；校验失败也要返回结构化 ERROR。
    所有错误作为观察返回，不伪装 OK。不要吞掉 StudentTask。
    """
    raise StudentTask('TODO D1: 实现工具分派与参数检查')
