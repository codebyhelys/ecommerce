from django.contrib import admin

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
    # só o status é editável; itens, valores e endereço são histórico
    readonly_fields = [
        "user", "total", "created_at", "updated_at",
        "shipping_name", "shipping_zip_code", "shipping_street", "shipping_number",
        "shipping_complement", "shipping_district", "shipping_city", "shipping_state",
    ]