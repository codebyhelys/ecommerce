from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def fake_gateway_in_production(app_configs, **kwargs):
    """`manage.py check --deploy` falha se o provedor de mentira estiver ativo fora de desenvolvimento."""
    if not settings.DEBUG and settings.PAYMENT_GATEWAY == "fake":
        return [
            Error(
                "PAYMENT_GATEWAY='fake' não pode ser usado com DEBUG=False.",
                hint="Defina PAYMENT_GATEWAY com o provedor real (ex.: mercadopago) no ambiente.",
                id="payments.E001",
            )
        ]
    return []
