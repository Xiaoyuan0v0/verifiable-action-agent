"""学生必做：三个函数。确认由宿主保存，不接收模型自报 confirmed=True。"""
from core import StudentTask, rule

def check_owner_status(action,task,db):
    """BR1: order_id 属于 task.user_scope；订单存在且 delivered。
    action={order_id,old_item_id,new_item_id,payment_method_id}。
    订单状态缺失 UNKNOWN；属于别人或状态禁止 FAIL。
    """
    raise StudentTask('TODO BR1')

def check_variant_stock(action,task,db):
    """BR2: 旧 item 在订单里；新 item 在同一 product 下且不同于旧 item；
    available is True；符合目标颜色且其他 options 不变。
    缺货 False 与库存未知 None 要区分。不能按商品名称猜同一产品。
    """
    raise StudentTask('TODO BR2')

def check_payment(action,task,db):
    """BR3: 支付方式属于当前用户，且是本任务指定方式；
    Decimal(新变体当前价)-Decimal(原订单成交价)。
    gift_card 正价差必须有足够 balance；未知价格/余额 UNKNOWN。
    PASS details 含 difference_usd 字符串。不调用真实支付服务。
    """
    raise StudentTask('TODO BR3')

RULES=[check_owner_status,check_variant_stock,check_payment]
