"""Deterministic, offline-first course extraction. Never execute upstream code."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
TRAVEL_COMMIT = 'e52c87f4ac348a3410c46dc3553c519db5ec5e23'
RETAIL_COMMIT = '7aad81c37a3a78b4ed3e4866769f851400c64415'
SOURCES = {
    'travel_train.jsonl': (f'https://raw.githubusercontent.com/OSU-NLP-Group/TravelPlanner/{TRAVEL_COMMIT}/database/train_ref_info.jsonl', 'f9eff8c9e3056c726c4bc46b8183a51efdf63760755b0183fa36f1c9f14b6e83'),
    'retail_db.json': (f'https://raw.githubusercontent.com/sierra-research/tau2-bench/{RETAIL_COMMIT}/data/tau2/domains/retail/db.json', '413a65160adbdb5fde0ffc0015c49b6d70250b10c18128de169b597af7766765'),
    'retail_policy.md': (f'https://raw.githubusercontent.com/sierra-research/tau2-bench/{RETAIL_COMMIT}/data/tau2/domains/retail/policy.md', '2c9652afbce57d6e087768d37cda64d31c53d50b3e3225cfdb791bac66466467'),
}

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')

def prepare(download=False):
    manifest = {'version': 'lab1-data-v1', 'conversion': 'prepare_data.py v1', 'sampling': 'first 3 travel lines; deterministic sorted retail selection', 'random_seed': None, 'files': []}
    for name, (url, expected) in SOURCES.items():
        p = ROOT/'data/raw'/name
        if download:
            with urlopen(url, timeout=60) as r: content = r.read()
            if hashlib.sha256(content).hexdigest() != expected: raise ValueError('下载校验失败 '+name)
            p.write_bytes(content)
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != expected: raise ValueError('原始数据被改动 '+name)
        manifest['files'].append({'file': name, 'url': url, 'sha256': actual, 'bytes': p.stat().st_size})
    manifest['licenses'] = {'travel_data': 'CC-BY-4.0; https://huggingface.co/datasets/osunlp/TravelPlanner', 'travel_code': 'MIT; data/licenses/TravelPlanner_CODE_LICENSE', 'retail': 'MIT; data/licenses/tau2_LICENSE'}
    records = {}
    lines = (ROOT/'data/raw/travel_train.jsonl').read_text(encoding='utf-8').splitlines()
    for li, line in enumerate(lines[:3],1):
        for gi, (group, rows) in enumerate(json.loads(line).items(),1):
            if not isinstance(rows,list): continue
            for ri,r in enumerate(rows):
                ident=f'T{li:02d}-{gi:02d}-{ri:03d}'
                v={'id':ident,'source':f'travel_train.jsonl:line={li};group={group};index={ri}', 'source_version':TRAVEL_COMMIT,'record_version':1}
                if group.startswith('Flight'):
                    v.update(kind='flight', name=r['Flight Number'], price_usd=r['Price'], origin=r['OriginCityName'],city=r['DestCityName'], date=r['FlightDate'],departure=r['DepTime'],arrival=r['ArrTime'])
                elif group.startswith('Accommodations'):
                    v.update(kind='lodging',name=r['NAME'],price_usd=r['price'],city=r['city'],capacity=r['maximum occupancy'],min_nights=int(r['minimum nights']),room_type=r['room type'],house_rules=r['house_rules'])
                elif group.startswith('Restaurants'):
                    v.update(kind='restaurant',name=r['Name'],price_usd=r['Average Cost'],city=r['City'])
                else:
                    v.update(kind='attraction',name=r['Name'],city=r['City'],price_usd=None)
                records[ident]=v
    task={'origin':'St. Petersburg','destination':'Rockford','start':'2022-03-16','end':'2022-03-18','people':1,'budget_usd':1800,'no_driving':True,'scope':'round-trip flights + rooms for 2 nights + one meal per day; other costs unknown'}
    travel={'version':'travel-course-v1','records':records,'task':task,'units_overlay':{'derived_from':'TravelPlanner database/README.md','flight':'USD per person one way','lodging':'USD per room per night; occupancy per room','restaurant':'USD per person per meal; course task budgets one meal each day','unpriced':['attraction tickets','local transport','other meals'],'schedule':'Date-level candidate activities only; no opening-hour or time-zone feasibility guarantee.'}}
    full=json.loads((ROOT/'data/raw/retail_db.json').read_text(encoding='utf-8'))
    matches=[]
    for oid,o in sorted(full['orders'].items()):
        if o['status']!='delivered': continue
        u=full['users'][o['user_id']]
        for item in o['items']:
            if item['name']!='T-Shirt': continue
            variants=full['products'][item['product_id']]['variants']
            targets=[v for _,v in sorted(variants.items()) if v['available'] and v['item_id']!=item['item_id'] and all(v['options'].get(k)==val for k,val in item['options'].items() if k!='color') and v['options']['color']!=item['options']['color']]
            pays=[k for k,v in sorted(u['payment_methods'].items()) if v['source'] in ('credit_card','paypal')]
            if targets and pays: matches.append((o,u,item,targets[0],pays[0]))
    if not matches: raise ValueError('冻结数据中找不到可用任务，不能编造订单')
    o,u,item,target,payment=matches[0]
    selected=[u['user_id']]+[uid for uid in sorted(full['users']) if uid!=u['user_id']][:9]
    users={uid:full['users'][uid] for uid in selected}
    orders={oid:row for oid,row in full['orders'].items() if row['user_id'] in users}
    pids={i['product_id'] for row in orders.values() for i in row['items']}
    products={pid:full['products'][pid] for pid in sorted(pids)}
    for oid,row in orders.items():
        row['record_version']=1; row['source']=f'retail_db.json:/orders/{oid}'; row['source_version']=RETAIL_COMMIT
        for it in row['items']: assert it['item_id'] in products[it['product_id']]['variants']
        for trans in row['payment_history']: assert trans['payment_method_id'] in users[row['user_id']]['payment_methods']
    for uid,row in users.items():
        assert all(oid in orders and orders[oid]['user_id']==uid for oid in row['orders'])
        row.update(record_version=1,source=f'retail_db.json:/users/{uid}',source_version=RETAIL_COMMIT)
    for pid,row in products.items():
        row.update(record_version=1,source=f'retail_db.json:/products/{pid}',source_version=RETAIL_COMMIT)
    task_b={'user_scope':u['user_id'],'email':u['email'],'order_id':o['order_id'],'old_item_id':item['item_id'],'target_color':target['options']['color'],'keep_options':{k:v for k,v in item['options'].items() if k!='color'},'payment_method_id':payment,'intent':'compare_only_then_wait_for_confirmation'}
    retail={'version':'retail-course-v1','users':users,'orders':orders,'products':products,'task':task_b,'course_scope':'Only one delivered-order item exchange; no email, payment, shipping or production authentication. Full policy retained in data/raw/retail_policy.md.'}
    dump(ROOT/'data/derived/travel.json',travel)
    dump(ROOT/'data/derived/retail.json',retail)
    for name in ('travel','retail'):
        path=ROOT/f'data/derived/{name}.json'
        manifest.setdefault('derived',[]).append({'file':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    dump(ROOT/'data/source_manifest.json',manifest)
    print(json.dumps({'travel_records':len(records),'retail_users':len(users),'retail_orders':len(orders),'retail_products':len(products),'retail_task':task_b},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--download',action='store_true'); args=p.parse_args(); prepare(args.download)
