"""学生必做：三个函数；不要用 LLM 代替有限规则。参见 tutorial 第 6 节。"""
from core import StudentTask, rule

def check_route_and_dates(plan,task,records):
    """TR1: 检查 IDs、往返城市/日期、3 个日程日期、景点/餐厅城市。
    plan: outbound_id, return_id, lodging_id, rooms, daily[{date,attraction_id,restaurant_id}]
    不存在的 ID 是 FAIL；存在但必要事实未知是 UNKNOWN。日程不得重复或漏天。
    返回 rule('TR1', 'PASS'/'FAIL'/'UNKNOWN', 可解释原因)。
    """
    raise StudentTask('TODO TR1')

def check_lodging(plan,task,records):
    """TR2: nights=end-start；rooms 为正整数（bool 不算）；
    nights >= min_nights；rooms * capacity >= people；住宿城市匹配。
    缺失容量/最低晚数不得默认 0。返回 rule(...)。
    """
    raise StudentTask('TODO TR2')

def check_budget(plan,task,records):
    """TR3: 用 Decimal 算往返票价*人数 + 房价*房数*晚数 + 每日一餐*人数。
    不信任模型填写的总额；全部所需价格已知才能判断 <= budget_usd。
    PASS 的 details 必须含 total_usd 字符串与 unpriced 非空列表；
    不把门票、市内交通和其他餐费记为 0，不宣称全部真实费用已覆盖。
    """
    raise StudentTask('TODO TR3')

RULES=[check_route_and_dates,check_lodging,check_budget]
