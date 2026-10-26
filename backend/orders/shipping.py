from decimal import Decimal

from django.conf import settings


def calculate_shipping(merchandise_value):
    """Frete fixo; grátis a partir de SHIPPING_FREE_ABOVE (sobre o valor dos itens já com desconto)."""
    value = Decimal(merchandise_value)
    if value <= 0:
        return Decimal("0.00")
    free_above = settings.SHIPPING_FREE_ABOVE
    if free_above is not None and value >= free_above:
        return Decimal("0.00")
    return Decimal(settings.SHIPPING_FLAT_RATE)
