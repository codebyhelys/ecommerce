import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="orders.send_order_email",
    autoretry_for=(Exception,),
    retry_backoff=10,  # 10 s, 20 s, 40 s... (com variação) até 10 min: SMTP fora do ar costuma voltar
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_order_email_task(order_id, event):
    from .emails import deliver_order_email

    deliver_order_email(order_id, event)


@shared_task(name="orders.expire_pending_orders")
def expire_pending_orders_task():
    from .services import expire_pending_orders

    expired, released = expire_pending_orders()
    logger.info("expire_pending_orders: %s pedido(s) expirado(s), %s pagamento(s) liberado(s)", expired, released)
