from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Coupon


def get_valid_coupon(code, *, user, subtotal, lock=False):
    """Devolve (cupom, desconto) ou levanta ValidationError({'coupon': ...}).

    Com lock=True a linha do cupom fica travada até o fim da transação: dois checkouts simultâneos
    do último uso não passam os dois.
    """
    queryset = Coupon.objects.select_for_update() if lock else Coupon.objects
    try:
        coupon = queryset.get(code=str(code).strip().upper(), is_active=True)
    except Coupon.DoesNotExist:
        raise ValidationError({"coupon": "Cupom inválido."}) from None  # mesma mensagem para inexistente e inativo

    now = timezone.now()
    if coupon.starts_at and now < coupon.starts_at:
        raise ValidationError({"coupon": "Este cupom ainda não está válido."})
    if coupon.expires_at and now >= coupon.expires_at:
        raise ValidationError({"coupon": "Este cupom expirou."})
    if subtotal < coupon.min_order_value:
        raise ValidationError({"coupon": f"Pedido mínimo de R$ {coupon.min_order_value:.2f} para este cupom."})
    if coupon.usage_limit is not None and coupon.redemptions.count() >= coupon.usage_limit:
        raise ValidationError({"coupon": "Este cupom esgotou."})
    if coupon.redemptions.filter(user=user).count() >= coupon.per_user_limit:
        raise ValidationError({"coupon": "Você já usou este cupom."})
    return coupon, coupon.discount_for(subtotal)
