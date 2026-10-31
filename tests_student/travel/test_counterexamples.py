"""本组自增反例：公开测试未覆盖的边界。参见 tutorial 第 6 节与报告第 4 节。

公开测试的任务只有 1 人、房数固定为 1，因此它无法发现"漏乘人数"和
"布尔值被当成整数 1"这类错误。本文件专门补上这些反例。
"""
import json
import unittest
from copy import deepcopy
from decimal import Decimal

from core import ROOT, read_json
from domain_rules import travel


class TravelCounterExampleTests(unittest.TestCase):
    def setUp(self):
        self.db=read_json(ROOT/'data/derived/travel.json')
        self.task=self.db['task']
        self.records=self.db['records']
        step=read_json(ROOT/'eval/replays/travel_standard.json')[2]
        self.plan=json.loads(step['message']['tool_calls'][0]['function']['arguments'])['plan']

    # 反例 1：两人出行的费用必须乘人数。
    # 公开样例只有 1 人，若 TR3 漏乘人数，本例会算出 1300（单人总额）而不是 2180。
    def test_two_people_cost_is_multiplied_by_headcount(self):
        task=deepcopy(self.task)
        task['people']=2
        task['budget_usd']=3000  # 放宽预算，隔离"是否乘人数"这一个变量
        result=travel.check_budget(self.plan,task,self.records)
        self.assertEqual(result['verdict'],'PASS',result)
        # 去程 474 + 回程 346 = 820/人；住宿 210×1房×2晚 = 420；三餐 20×3 = 60/人
        # 两人合计 = (820+60)×2 + 420 = 1760+420 = 2180
        self.assertEqual(Decimal(result['details']['total_usd']),Decimal('2180'))
        # 若漏乘人数会得到 1300（单人总额），这个断言是本反例的核心。
        self.assertNotEqual(Decimal(result['details']['total_usd']),Decimal('1300'))

    # 反例 2：住宿需要更多房间时，TR3 的房价项也要乘房数。
    def test_more_rooms_multiplies_lodging_price(self):
        task=deepcopy(self.task)
        task['people']=2
        task['budget_usd']=3000
        plan=deepcopy(self.plan)
        plan['rooms']=2
        result=travel.check_budget(plan,task,self.records)
        self.assertEqual(result['verdict'],'PASS',result)
        # 房价项由 420 变成 840，总额 2180 -> 2600
        self.assertEqual(Decimal(result['details']['total_usd']),Decimal('2600'))
        # 若漏乘房数会退回 2180
        self.assertNotEqual(Decimal(result['details']['total_usd']),Decimal('2180'))

    # 反例 3：True 不是正整数 1。房数用 True 冒充时必须 FAIL。
    def test_boolean_rooms_is_not_an_integer(self):
        plan=deepcopy(self.plan)
        plan['rooms']=True
        self.assertEqual(travel.check_lodging(plan,self.task,self.records)['verdict'],'FAIL')
        # 同一错误不能被 TR3 当成 1 间房来计价。
        self.assertNotEqual(travel.check_budget(plan,self.task,self.records)['verdict'],'PASS')

    # 反例 4：回程日期错误必须 FAIL，而不是只核对城市。
    def test_wrong_return_flight_date_fails(self):
        records=deepcopy(self.records)
        records['T01-07-000']['date']='2022-03-19'
        self.assertEqual(travel.check_route_and_dates(self.plan,self.task,records)['verdict'],'FAIL')

    # 反例 5：回程城市错误（去了别的城市）必须 FAIL。
    def test_wrong_return_flight_city_fails(self):
        records=deepcopy(self.records)
        records['T01-07-000']['city']='Pensacola'
        self.assertEqual(travel.check_route_and_dates(self.plan,self.task,records)['verdict'],'FAIL')

    # 反例 6：日程漏一天必须 FAIL（不能因为"少一天也算安排过"而通过）。
    def test_missing_day_fails(self):
        plan=deepcopy(self.plan)
        plan['daily']=plan['daily'][:2]
        self.assertEqual(travel.check_route_and_dates(plan,self.task,self.records)['verdict'],'FAIL')

    # 反例 7：景点属于别的城市必须 FAIL（不能只查 ID 存在）。
    def test_attraction_in_other_city_fails(self):
        records=deepcopy(self.records)
        # 把被引用的景点记录本身改成另一个城市：ID 仍存在，但城市不匹配。
        records[self.plan['daily'][0]['attraction_id']]['city']='Pensacola'
        self.assertEqual(travel.check_route_and_dates(self.plan,self.task,records)['verdict'],'FAIL')

    # 反例 8：容量缺失是 UNKNOWN，不能默认成 0 或 True 而 FAIL/PASS。
    def test_missing_capacity_is_unknown_not_fail(self):
        records=deepcopy(self.records)
        records[self.plan['lodging_id']]['capacity']=None
        self.assertEqual(travel.check_lodging(self.plan,self.task,records)['verdict'],'UNKNOWN')

    # 反例 9：未知餐价是 UNKNOWN，不能当作 0 餐费从而 PASS。
    def test_unknown_meal_price_is_unknown(self):
        records=deepcopy(self.records)
        records[self.plan['daily'][0]['restaurant_id']]['price_usd']=None
        result=travel.check_budget(self.plan,self.task,records)
        self.assertEqual(result['verdict'],'UNKNOWN')
        self.assertTrue(result['details']['unpriced'])

    # 反例 10：PASS 时 total_usd 是字符串，unpriced 必须非空（不能宣称覆盖全部费用）。
    def test_pass_reports_total_as_string_and_keeps_unpriced(self):
        result=travel.check_budget(self.plan,self.task,self.records)
        self.assertEqual(result['verdict'],'PASS')
        self.assertIsInstance(result['details']['total_usd'],str)
        self.assertTrue(result['details']['unpriced'])

    # 反例 11：不存在的 ID 是 FAIL，不是 UNKNOWN（事实明确缺失）。
    def test_unknown_id_is_fail_not_unknown(self):
        plan=deepcopy(self.plan)
        plan['lodging_id']='T01-03-999'
        self.assertEqual(travel.check_route_and_dates(plan,self.task,self.records)['verdict'],'FAIL')
        self.assertEqual(travel.check_lodging(plan,self.task,self.records)['verdict'],'FAIL')
        self.assertEqual(travel.check_budget(plan,self.task,self.records)['verdict'],'FAIL')


if __name__=='__main__':
    unittest.main()
