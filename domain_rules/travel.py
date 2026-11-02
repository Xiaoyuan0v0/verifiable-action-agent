"""学生必做：三个函数；不要用 LLM 代替有限规则。参见 tutorial 第 6 节。"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from core import StudentTask, rule

def _dates(task):
    """任务给定的到达/离开日期；无法解析时返回 (None, None)。"""
    try:
        return date.fromisoformat(task['start']), date.fromisoformat(task['end'])
    except (KeyError, TypeError, ValueError):
        return None, None

def _record(records,record_id,kind):
    """按 ID 取记录；不存在或类型不符返回 None。"""
    if not isinstance(record_id,str): return None
    row=records.get(record_id)
    if not isinstance(row,dict) or row.get('kind')!=kind: return None
    return row

def _nights(task):
    """计划晚数 = 离开日期 - 到达日期。"""
    start,end=_dates(task)
    if start is None or end is None: return None
    return (end-start).days

def _money(value):
    """金额转 Decimal；None 或非数值返回 None（未知，不等于 0）。"""
    if value is None or isinstance(value,bool): return None
    if not isinstance(value,(int,float,str)): return None
    try:
        amount=Decimal(str(value))
    except (InvalidOperation,ValueError):
        return None
    return amount if amount.is_finite() else None

def check_route_and_dates(plan,task,records):
    """TR1: 检查 IDs、往返城市/日期、3 个日程日期、景点/餐厅城市。
    plan: outbound_id, return_id, lodging_id, rooms, daily[{date,attraction_id,restaurant_id}]
    不存在的 ID 是 FAIL；存在但必要事实未知是 UNKNOWN。日程不得重复或漏天。
    返回 rule('TR1', 'PASS'/'FAIL'/'UNKNOWN', 可解释原因)。
    """
    if not isinstance(plan,dict): return rule('TR1','FAIL','plan 不是对象')
    start,end=_dates(task)
    if start is None or end is None:
        return rule('TR1','UNKNOWN','任务的出发或返回日期缺失或格式不正确',start=str(task.get('start')),end=str(task.get('end')))
    if end<=start:
        return rule('TR1','FAIL','任务返回日期不晚于出发日期',start=str(start),end=str(end))

    daily=plan.get('daily')
    if not isinstance(daily,list) or not daily:
        return rule('TR1','FAIL','日程 daily 缺失或为空')
    expected_days=(end-start).days
    expected_dates=[start+timedelta(days=i) for i in range(expected_days+1)]
    dates=[]
    for item in daily:
        if not isinstance(item,dict): return rule('TR1','FAIL','日程条目不是对象')
        try: dates.append(date.fromisoformat(item['date']))
        except (KeyError,TypeError,ValueError): return rule('TR1','FAIL','日程日期缺失或不是 ISO 日期',date=str(item.get('date')))
    if len(set(dates))!=len(dates):
        return rule('TR1','FAIL','日程日期重复',dates=[str(d) for d in dates])
    if sorted(dates)!=sorted(expected_dates):
        return rule('TR1','FAIL','日程未覆盖全部日期或含有范围外日期',expected=[str(d) for d in expected_dates],actual=[str(d) for d in sorted(dates)])

    # 往返航班：存在性 -> 城市 -> 日期。
    origin,city=task.get('origin'),task.get('destination')
    for label,record_id,expected_origin,expected_city,expected_date in (
        ('去程',plan.get('outbound_id'),origin,city,start),
        ('回程',plan.get('return_id'),city,origin,end),
    ):
        row=_record(records,record_id,'flight')
        if row is None:
            return rule('TR1','FAIL',f'{label}航班 ID 不存在或不是航班记录',option_id=record_id)
        if row.get('origin')!=expected_origin or row.get('city')!=expected_city:
            return rule('TR1','FAIL',f'{label}航班城市不匹配',option_id=record_id,origin=row.get('origin'),city=row.get('city'),expected_origin=expected_origin,expected_city=expected_city)
        try: actual=date.fromisoformat(row['date'])
        except (KeyError,TypeError,ValueError):
            return rule('TR1','UNKNOWN',f'{label}航班日期缺失或无法解析',option_id=record_id,date=str(row.get('date')))
        if actual!=expected_date:
            return rule('TR1','FAIL',f'{label}航班日期与任务不符',option_id=record_id,date=str(actual),expected=str(expected_date))

    # 景点与餐厅必须属于目的城市。
    for item in daily:
        for key,kind,label in (('attraction_id','attraction','景点'),('restaurant_id','restaurant','餐厅')):
            row=_record(records,item.get(key),kind)
            if row is None:
                return rule('TR1','FAIL',f'{label} ID 不存在或不是{label}记录',option_id=item.get(key))
            if row.get('city')!=city:
                return rule('TR1','FAIL',f'{label}不在目的城市',option_id=item.get(key),city=row.get('city'),expected_city=city)

    # 住宿记录存在性在此确认（容量与最低晚数属于 TR2）。
    if _record(records,plan.get('lodging_id'),'lodging') is None:
        return rule('TR1','FAIL','住宿 ID 不存在或不是住宿记录',option_id=plan.get('lodging_id'))

    return rule('TR1','PASS','往返航班城市与日期匹配，日程日期完整不重复，景点与餐厅均属目的城市',nights=expected_days,daily_dates=[str(d) for d in sorted(dates)],daily_count=len(dates))

def check_lodging(plan,task,records):
    """TR2: nights=end-start；rooms 为正整数（bool 不算）；
    nights >= min_nights；rooms * capacity >= people；住宿城市匹配。
    缺失容量/最低晚数不得默认 0。返回 rule(...)。
    """
    if not isinstance(plan,dict): return rule('TR2','FAIL','plan 不是对象')
    row=_record(records,plan.get('lodging_id'),'lodging')
    if row is None:
        return rule('TR2','FAIL','住宿 ID 不存在或不是住宿记录',option_id=plan.get('lodging_id'))
    city=task.get('destination')
    if row.get('city')!=city:
        return rule('TR2','FAIL','住宿城市与目的城市不一致',option_id=row.get('id'),city=row.get('city'),expected_city=city)

    rooms=plan.get('rooms')
    if isinstance(rooms,bool) or not isinstance(rooms,int) or rooms<1:
        return rule('TR2','FAIL','房数不是正整数',rooms=repr(rooms))

    nights=_nights(task)
    if nights is None:
        return rule('TR2','UNKNOWN','任务日期缺失或格式不正确，无法计算晚数',start=str(task.get('start')),end=str(task.get('end')))
    if nights<1:
        return rule('TR2','FAIL','计划晚数不是正整数',nights=nights)

    min_nights=row.get('min_nights')
    if min_nights is None:
        return rule('TR2','UNKNOWN','住宿记录缺少最低入住晚数，无法判断',option_id=row.get('id'))
    if isinstance(min_nights,bool) or not isinstance(min_nights,int):
        return rule('TR2','UNKNOWN','最低入住晚数类型不正确',option_id=row.get('id'),min_nights=repr(min_nights))
    if nights<min_nights:
        return rule('TR2','FAIL','计划晚数低于住宿最低入住晚数',option_id=row.get('id'),nights=nights,min_nights=min_nights)

    capacity=row.get('capacity')
    if capacity is None:
        return rule('TR2','UNKNOWN','住宿记录缺少容量，无法判断是否住得下',option_id=row.get('id'))
    if isinstance(capacity,bool) or not isinstance(capacity,int) or capacity<1:
        return rule('TR2','UNKNOWN','住宿容量类型不正确或不是正整数',option_id=row.get('id'),capacity=repr(capacity))

    people=task.get('people')
    if isinstance(people,bool) or not isinstance(people,int) or people<1:
        return rule('TR2','UNKNOWN','任务人数缺失或类型不正确',people=repr(people))
    if rooms*capacity<people:
        return rule('TR2','FAIL','房数乘容量小于人数',rooms=rooms,capacity=capacity,people=people)

    return rule('TR2','PASS','住宿城市正确，房数为正整数，人数不超房数乘容量，晚数满足最低入住要求',option_id=row.get('id'),rooms=rooms,capacity=capacity,nights=nights,min_nights=min_nights,people=people)

def check_budget(plan,task,records):
    """TR3: 用 Decimal 算往返票价*人数 + 房价*房数*晚数 + 每日一餐*人数。
    不信任模型填写的总额；全部所需价格已知才能判断 <= budget_usd。
    PASS 的 details 必须含 total_usd 字符串与 unpriced 非空列表；
    不把门票、市内交通和其他餐费记为 0，不宣称全部真实费用已覆盖。
    """
    unpriced=['attraction tickets','local transport','other meals']
    if not isinstance(plan,dict): return rule('TR3','FAIL','plan 不是对象',unpriced=unpriced)
    budget=_money(task.get('budget_usd'))
    if budget is None:
        return rule('TR3','UNKNOWN','任务预算缺失或不是数值，无法比较',budget_usd=repr(task.get('budget_usd')),unpriced=unpriced)

    people=task.get('people')
    if isinstance(people,bool) or not isinstance(people,int) or people<1:
        return rule('TR3','UNKNOWN','任务人数缺失或类型不正确',people=repr(people),unpriced=unpriced)
    nights=_nights(task)
    if nights is None:
        return rule('TR3','UNKNOWN','任务日期缺失或格式不正确，无法计算晚数',start=str(task.get('start')),end=str(task.get('end')),unpriced=unpriced)
    rooms=plan.get('rooms')
    if isinstance(rooms,bool) or not isinstance(rooms,int) or rooms<1:
        return rule('TR3','UNKNOWN','房数不是正整数，无法计价',rooms=repr(rooms),unpriced=unpriced)

    total=Decimal('0'); missing=[]
    for label,record_id in (('去程票价',plan.get('outbound_id')),('回程票价',plan.get('return_id'))):
        row=_record(records,record_id,'flight')
        if row is None:
            return rule('TR3','FAIL',f'{label}对应的航班 ID 不存在或不是航班记录',option_id=record_id,unpriced=unpriced)
        price=_money(row.get('price_usd'))
        if price is None: missing.append(f'{label}:{record_id}')
        else: total+=price*people
    lodging=_record(records,plan.get('lodging_id'),'lodging')
    if lodging is None:
        return rule('TR3','FAIL','住宿 ID 不存在或不是住宿记录',option_id=plan.get('lodging_id'),unpriced=unpriced)
    price=_money(lodging.get('price_usd'))
    if price is None: missing.append(f'房价:{lodging.get("id")}')
    else: total+=price*rooms*nights

    daily=plan.get('daily')
    if not isinstance(daily,list) or not daily:
        return rule('TR3','FAIL','日程 daily 缺失或为空，无法计价餐费',unpriced=unpriced)
    for item in daily:
        row=_record(records,item.get('restaurant_id'),'restaurant')
        if row is None:
            return rule('TR3','FAIL','餐厅 ID 不存在或不是餐厅记录',option_id=item.get('restaurant_id'),unpriced=unpriced)
        price=_money(row.get('price_usd'))
        if price is None: missing.append(f'餐费:{row.get("id")}')
        else: total+=price*people

    if missing:
        return rule('TR3','UNKNOWN','必要价格未知，不能把未知当作 0 计算总额',missing_prices=missing,unpriced=unpriced)
    total_usd=str(total)
    if total>budget:
        return rule('TR3','FAIL','按原始价格重算的课程范围总额超出预算',total_usd=total_usd,budget_usd=str(budget),unpriced=unpriced)
    return rule('TR3','PASS','按往返票价、房价与每日一餐重算的课程范围总额在预算内',total_usd=total_usd,budget_usd=str(budget),people=people,rooms=rooms,nights=nights,unpriced=unpriced)

RULES=[check_route_and_dates,check_lodging,check_budget]
