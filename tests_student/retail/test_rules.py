import unittest
import json
from core import ROOT,read_json
from domain_rules import retail

class RetailRuleTests(unittest.TestCase):
    def setUp(self):
        self.db=read_json(ROOT/'data/derived/retail.json'); self.task=self.db['task']
        c=read_json(ROOT/'eval/replays/retail_standard.json')[3]['message']['tool_calls'][0]
        self.action=json.loads(c['function']['arguments'])['action']
    def target(self):
        o=self.db['orders'][self.action['order_id']]; old=next(i for i in o['items'] if i['item_id']==self.action['old_item_id'])
        return self.db['products'][old['product_id']]['variants'][self.action['new_item_id']]
    def test_valid_exchange(self):
        for fn in retail.RULES: self.assertEqual(fn(self.action,self.task,self.db)['verdict'],'PASS',fn.__name__)
    def test_other_owner_and_processed(self):
        o=self.db['orders'][self.action['order_id']]; o['user_id']='another-user'
        self.assertEqual(retail.check_owner_status(self.action,self.task,self.db)['verdict'],'FAIL')
        o['user_id']=self.task['user_scope']; o['status']='processed'
        self.assertEqual(retail.check_owner_status(self.action,self.task,self.db)['verdict'],'FAIL')
    def test_unavailable_vs_unknown(self):
        self.target()['available']=False
        self.assertEqual(retail.check_variant_stock(self.action,self.task,self.db)['verdict'],'FAIL')
        self.target()['available']=None
        self.assertEqual(retail.check_variant_stock(self.action,self.task,self.db)['verdict'],'UNKNOWN')
    def test_wrong_product_and_payment(self):
        self.action['new_item_id']='not-an-item'
        self.assertEqual(retail.check_variant_stock(self.action,self.task,self.db)['verdict'],'FAIL')
        self.action['payment_method_id']='another-user-card'
        self.assertEqual(retail.check_payment(self.action,self.task,self.db)['verdict'],'FAIL')
    def test_difference_uses_order_price(self):
        self.assertEqual(retail.check_payment(self.action,self.task,self.db)['details']['difference_usd'],'6.42')

if __name__=='__main__': unittest.main()
