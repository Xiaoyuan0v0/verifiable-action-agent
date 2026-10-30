"""本地业务工具：读取事实、检查规则、保存并读取结果。"""
from copy import deepcopy
from core import ROOT, read_json, write_json, digest, safe_rules, result
from domain_rules import travel, retail

CASE_NAMES=('standard','changed','missing','blocked','failure','limit')

def target_variant(db):
    t=db['task']; o=db['orders'][t['order_id']]
    item=next(i for i in o['items'] if i['item_id']==t['old_item_id'])
    p=db['products'][item['product_id']]
    choices=[v for _,v in sorted(p['variants'].items()) if v['options'].get('color')==t['target_color'] and all(v['options'].get(k)==val for k,val in t['keep_options'].items())]
    return p,choices[0]

def fresh_database(route,case):
    if case not in CASE_NAMES: raise ValueError('case not enabled')
    db=read_json(ROOT/f'data/derived/{route}.json')
    db['overlay']={'id':case,'course_authored':case!='standard','derived_from':db['version'],'description':'See eval/dev/cases.json; raw source bytes stay unchanged.'}
    if route=='travel':
        hotels=[r for r in db['records'].values() if r['kind']=='lodging' and r['city']==db['task']['destination']]
        valid=sorted([r for r in hotels if r['min_nights']<=2 and r['capacity']>=1],key=lambda r:(r['price_usd'],r['id']))
        if case=='changed': valid[0]['min_nights']=5; valid[0]['record_version']+=1
        if case=='missing':
            for r in hotels: r['price_usd']=None; r['record_version']+=1
        if case=='blocked': db['task']['budget_usd']=1
    else:
        product,v=target_variant(db)
        if case=='changed': v['available']=False
        if case=='missing': v['available']=None
        if case in ('changed','missing'): product['record_version']+=1
        if case=='blocked':
            db['orders'][db['task']['order_id']]['status']='processed'
            db['orders'][db['task']['order_id']]['record_version']+=1
    return db

class Environment:
    def __init__(self,session):
        self.session=session; self.route=session.route
        self.path=session.dir/'business.json'
        self.db=read_json(self.path)
        self.task=self.db['task']
        self.scope=self.task.get('user_scope','travel_student')

    def persist(self): write_json(self.path,self.db); self.session.save()
    def guarded_order(self,oid):
        if not self.session.state.get('identified'): return None,result('ERROR',code='IDENTIFY_FIRST')
        row=self.db['orders'].get(oid)
        if row is None: return None,result('UNKNOWN',code='ORDER_NOT_FOUND')
        if row['user_id']!=self.scope: return None,result('ERROR',code='SCOPE_DENIED')
        return row,None

    def invoke(self,name,args):
        handler=getattr(self,'tool_'+name,None)
        if handler is None: return result('ERROR',code='TOOL_NOT_ALLOWED')
        out=handler(**args)
        out.update(snapshot=self.db['version'],overlay=self.db['overlay']['id'])
        return out

    def tool_search_options(self,kind,city,origin=None,date=None,limit=5,offset=0):
        rows=[r for r in self.db['records'].values() if r['kind']==kind and r['city']==city and (origin is None or r.get('origin')==origin) and (date is None or r.get('date')==date)]
        rows.sort(key=lambda r:(r.get('price_usd') if r.get('price_usd') is not None else float('inf'),r['id']))
        return result('OK',{'records':rows[offset:offset+limit],'total':len(rows),'has_more':offset+limit<len(rows),'scope':self.task['scope'],'units':self.db['units_overlay']})

    def tool_get_option(self,option_id):
        row=self.db['records'].get(option_id)
        return result('OK',row,record_id=option_id,record_version=row['record_version']) if row else result('UNKNOWN',code='OPTION_NOT_FOUND')

    def check_travel(self,plan): return safe_rules(travel.RULES,plan,self.task,self.db['records'])
    def tool_check_plan(self,plan): return result('OK',self.check_travel(plan))
    def tool_save_itinerary(self,plan):
        check=self.check_travel(plan)
        if check['verdict']!='PASS': return result('ERROR' if check['verdict']=='FAIL' else 'UNKNOWN',check,code='WRITE_REJECTED')
        if self.session.case=='failure': return result('ERROR',code='INJECTED_WRITE_FAILURE',injected=True)
        ident='I-'+digest({'episode':self.session.state['episode_id'],'plan':plan})[:16]
        row={'id':ident,'user_scope':self.scope,'plan':deepcopy(plan),'check':check,'record_version':1,'kind':'teaching_itinerary','scope':self.task['scope'],'unpriced':self.db['units_overlay']['unpriced']}
        self.db.setdefault('itineraries',{})[ident]=row
        self.session.state['written']={'id':ident,'digest':digest(row)}
        self.session.state['readback']=None; self.persist()
        return result('OK',{'itinerary_id':ident,'saved':True},record_id=ident,record_version=1)

    def tool_get_itinerary(self,itinerary_id):
        row=self.db.get('itineraries',{}).get(itinerary_id)
        if not row: return result('UNKNOWN',code='ITINERARY_NOT_FOUND')
        if row['user_scope']!=self.scope: return result('ERROR',code='SCOPE_DENIED')
        self.session.state['readback']={'id':itinerary_id,'digest':digest(row)}; self.session.save()
        return result('OK',row,record_id=itinerary_id,record_version=row['record_version'])

    def tool_identify_customer(self,email):
        uid=next((k for k,u in self.db['users'].items() if u['email']==email),None)
        if uid is None: return result('UNKNOWN',code='CUSTOMER_NOT_FOUND')
        if uid!=self.scope: return result('ERROR',code='SCOPE_DENIED')
        self.session.state['identified']=True; self.session.save()
        user=self.db['users'][uid]
        return result('OK',{'user_id':uid,'order_ids':user['orders'],'source':user['source'],'source_version':user['source_version']},record_id=uid,record_version=user['record_version'])

    def tool_get_order(self,order_id):
        row,error=self.guarded_order(order_id)
        if error: return error
        if (self.session.state.get('written') or {}).get('id')==order_id:
            self.session.state['readback']={'id':order_id,'digest':digest(row)}; self.session.save()
        return result('OK',row,record_id=order_id,record_version=row['record_version'])

    def tool_get_product(self,product_id):
        if not self.session.state.get('identified'): return result('ERROR',code='IDENTIFY_FIRST')
        allowed={i['product_id'] for o in self.db['orders'].values() if o['user_id']==self.scope for i in o['items']}
        if product_id not in allowed: return result('ERROR',code='SCOPE_DENIED')
        row=self.db['products'].get(product_id)
        return result('OK',row,record_id=product_id,record_version=row['record_version']) if row else result('UNKNOWN',code='PRODUCT_NOT_FOUND')

    def check_retail(self,action): return safe_rules(retail.RULES,action,self.task,self.db)
    def tool_check_action(self,action):
        row,error=self.guarded_order(action['order_id'])
        if error: return error
        check=self.check_retail(action)
        if check['verdict']!='PASS': return result('OK',check)
        # Confirmation is bound to content + original order state + this subject.
        payload={'action':deepcopy(action),'order_digest':digest(row),'user_scope':self.scope,'check':check}
        pid='P-'+digest(payload)[:20]
        old=self.session.state.get('pending')
        if old is None or old['id']!=pid: self.session.state['confirmation']=None
        self.session.state['pending']={'id':pid,**payload}; self.session.save()
        return result('OK',{**check,'proposal_id':pid,'action':action,'needs_user_confirmation':True,'reminder':'确认这是本订单所有要换的商品；本次仅支持换一件。尚未提交。'})

    def tool_apply_action(self,proposal_id):
        pending=self.session.state.get('pending')
        if not pending or pending['id']!=proposal_id: return result('ERROR',code='PROPOSAL_NOT_FOUND')
        confirmed=self.session.state.get('confirmation')
        if confirmed!=proposal_id: return result('ERROR',code='EXPLICIT_CONFIRMATION_REQUIRED')
        a=pending['action']; row,error=self.guarded_order(a['order_id'])
        if error: return error
        if digest(row)!=pending['order_digest']: return result('ERROR',code='PROPOSAL_STALE')
        check=self.check_retail(a)
        if check['verdict']!='PASS': return result('ERROR' if check['verdict']=='FAIL' else 'UNKNOWN',check,code='WRITE_REJECTED')
        # A confirmation covers the quoted terms, including the price difference.
        if digest(check)!=digest(pending['check']):
            self.session.state['confirmation']=None; self.session.save()
            return result('ERROR',code='PROPOSAL_TERMS_CHANGED',data={'message':'价格或其他条款已变化，请重新 check_action 并确认新提案。'})
        if self.session.case=='failure': return result('ERROR',code='INJECTED_WRITE_FAILURE',injected=True)
        row['status']='exchange requested'
        row['course_exchange']={'action':a,'check':check,'confirmation':proposal_id,'note':'Local request only; no real payment, email, delivery or completed exchange.'}
        row['record_version']+=1
        self.session.state['written']={'id':row['order_id'],'digest':digest(row)}
        self.session.state['readback']=None; self.session.state['confirmation']=None; self.persist()
        return result('OK',{'order_id':row['order_id'],'status':row['status']},record_id=row['order_id'],record_version=row['record_version'])

    def verify_completion(self):
        # Reload actual bytes; neither model text nor stale in-memory return is proof.
        self.db=read_json(self.path)
        written=self.session.state.get('written'); readback=self.session.state.get('readback')
        if not written or written!=readback: return False
        row=self.db.get('itineraries' if self.route=='travel' else 'orders',{}).get(written['id'])
        if not row or digest(row)!=written['digest']: return False
        if self.route=='travel': return self.check_travel(row['plan'])['verdict']=='PASS'
        return row['user_id']==self.scope and row['status']=='exchange requested' and bool(row.get('course_exchange',{}).get('confirmation'))
