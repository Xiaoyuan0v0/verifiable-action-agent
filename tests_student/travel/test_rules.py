import unittest
from copy import deepcopy
from core import ROOT,read_json
from domain_rules import travel

class TravelRuleTests(unittest.TestCase):
    def setUp(self):
        self.db=read_json(ROOT/'data/derived/travel.json'); self.task=self.db['task']; self.records=self.db['records']
        step=read_json(ROOT/'eval/replays/travel_standard.json')[2]
        import json
        self.plan=json.loads(step['message']['tool_calls'][0]['function']['arguments'])['plan']
    def test_valid_plan_passes(self):
        for fn in travel.RULES: self.assertEqual(fn(self.plan,self.task,self.records)['verdict'],'PASS',fn.__name__)
    def test_wrong_date_or_duplicate_day_fails(self):
        p=deepcopy(self.plan); p['daily'][1]['date']=p['daily'][0]['date']
        self.assertEqual(travel.check_route_and_dates(p,self.task,self.records)['verdict'],'FAIL')
    def test_capacity_and_min_nights(self):
        r=self.records[self.plan['lodging_id']]; r['min_nights']=8
        self.assertEqual(travel.check_lodging(self.plan,self.task,self.records)['verdict'],'FAIL')
        r['min_nights']=1; r['capacity']=None
        self.assertEqual(travel.check_lodging(self.plan,self.task,self.records)['verdict'],'UNKNOWN')
    def test_unknown_price_is_not_zero(self):
        self.records[self.plan['lodging_id']]['price_usd']=None
        self.assertEqual(travel.check_budget(self.plan,self.task,self.records)['verdict'],'UNKNOWN')
    def test_budget_and_total_scope(self):
        r=travel.check_budget(self.plan,self.task,self.records)
        self.assertIn('total_usd',r['details']); self.assertTrue(r['details']['unpriced'])
        self.task['budget_usd']=1
        self.assertEqual(travel.check_budget(self.plan,self.task,self.records)['verdict'],'FAIL')

if __name__=='__main__': unittest.main()
