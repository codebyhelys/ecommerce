from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ["product", "product_name", "unit_price", "quantity"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["id", "user__email"]
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    actions = ["mark_shipped", "mark_delivered", "cancel_orders"]
    # nada é editável à mão: o status só muda pelas ações abaixo (que respeitam as regras do sistema)
    readonly_fields = [
        "user",
        "status",
        "total",
        "created_at",
        "updated_at",
        "shipping_name",
        "shipping_zip_code",
        "shipping_street",
        "shipping_number",
        "shipping_complement",
        "shipping_district",
        "shipping_city",
        "shipping_state",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _run(self, request, queryset, action, done):
        ok = 0
        for order in queryset:
            try:
                action(order)
                ok += 1
            except APIException as exc:
                self.message_user(request, str(exc.detail), level=messages.WARNING)
        if ok:
            self.message_user(request, f"{ok} pedido(s) {done}.")

    @admin.action(description="Marcar como enviado (pedidos pagos)")
    def mark_shipped(self, request, queryset):
        self._run(request, queryset, services.ship_order, "marcado(s) como enviado(s)")

    @admin.action(description="Marcar como entregue (pedidos enviados)")
    def mark_delivered(self, request, queryset):
        self._run(request, queryset, services.deliver_order, "marcado(s) como entregue(s)")

    @admin.action(description="Cancelar (pedidos pendentes; devolve o estoque)")
    def cancel_orders(self, request, queryset):
        self._run(request, queryset, services.cancel_order, "cancelado(s)")
