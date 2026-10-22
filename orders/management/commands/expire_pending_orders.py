from django.core.management.base import BaseCommand

from orders import services


class Command(BaseCommand):
    help = "Cancela pedidos pendentes expirados (devolvendo o estoque) e libera pagamentos presos."

    def handle(self, *args, **options):
        expired, stuck = services.expire_pending_orders()
        self.stdout.write(
            self.style.SUCCESS(f"{expired} pedido(s) expirado(s); {stuck} pagamento(s) preso(s) liberado(s).")
        )
