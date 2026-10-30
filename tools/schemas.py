"""Small JSON-schema subset used by this course, not a general JSON-schema engine."""
import math

def obj(props,required=None):
    return {'type':'object','properties':props,'required':list(props) if required is None else required,'additionalProperties':False}
S={'type':'string','minLength':1}
I={'type':'integer','minimum':1}
PLAN=obj({'outbound_id':S,'return_id':S,'lodging_id':S,'rooms':I,'daily':{'type':'array','minItems':1,'maxItems':7,'items':obj({'date':S,'attraction_id':S,'restaurant_id':S})}})
ACTION=obj({'order_id':S,'old_item_id':S,'new_item_id':S,'payment_method_id':S})

def spec(name,description,params): return {'type':'function','function':{'name':name,'description':description,'parameters':params}}
def specs(route):
    if route=='travel':
        return [
            spec('search_options','搜索冻结快照；city 是目的城市，flight 可另传 origin/date。返回有来源的有限分页；不是实时订票。',obj({'kind':{'type':'string','enum':['flight','lodging','restaurant','attraction']},'city':S,'origin':S,'date':S,'limit':{'type':'integer','minimum':1,'maximum':10},'offset':{'type':'integer','minimum':0}},['kind','city'])),
            spec('get_option','凭搜索返回的 ID 读取一项事实及来源。',obj({'option_id':S})),
            spec('check_plan','用 Python 规则核验行程；PASS/FAIL/UNKNOWN，返回费用计算范围。',obj({'plan':PLAN})),
            spec('save_itinerary','重新检查后保存教学行程；拒绝未通过检查的写入。必须再 get_itinerary 读回。',obj({'plan':PLAN})),
            spec('get_itinerary','读回当前任务的已保存行程，核对最终状态。',obj({'itinerary_id':S})),
        ]
    if route=='retail':
        return [
            spec('identify_customer','以任务中的合成 email 定位用户，绑定宿主预设主体；不能切换其他用户。',obj({'email':S})),
            spec('get_order','只允许读取已绑定用户的订单；写入后再次调用核验状态。',obj({'order_id':S})),
            spec('get_product','读取该用户订单中关联的商品及变体，最多 100 个变体。',obj({'product_id':S})),
            spec('check_action','检查一件已送达商品换色，计算价差。通过后形成精确提案；等待用户在终端确认。',obj({'action':ACTION})),
            spec('apply_action','提交已经由用户在宿主终端确认的 proposal_id。模型传 confirmed/yes 不构成确认。',obj({'proposal_id':S})),
        ]
    raise ValueError('unknown route')

def validate(schema,value,path='$'):
    typ=schema['type']
    match={'object':type(value) is dict,'array':type(value) is list,'string':type(value) is str,'integer':type(value) is int,'number':type(value) in (int,float),'boolean':type(value) is bool}.get(typ,False)
    if not match: raise ValueError(f'{path}: expected {typ}')
    if typ=='object':
        if any(k not in value for k in schema.get('required',[])): raise ValueError(f'{path}: required field missing')
        if schema.get('additionalProperties') is False and set(value)-set(schema['properties']): raise ValueError(f'{path}: extra fields')
        for k,v in value.items(): validate(schema['properties'][k],v,f'{path}.{k}')
    elif typ=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',100): raise ValueError(f'{path}: array size')
        for i,v in enumerate(value): validate(schema['items'],v,f'{path}[{i}]')
    elif typ in ('integer','number'):
        if not math.isfinite(value) or value<schema.get('minimum',float('-inf')) or value>schema.get('maximum',float('inf')): raise ValueError(f'{path}: numeric bounds')
    elif typ=='string' and len(value)<schema.get('minLength',0): raise ValueError(f'{path}: empty string')
    if 'enum' in schema and value not in schema['enum']: raise ValueError(f'{path}: invalid enum')
