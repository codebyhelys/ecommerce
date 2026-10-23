from django.contrib import admin, messages
from rest_framework.exceptions import APIException

from . import services
from .models import Payment, WebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "provider", "method", "status", "amount", "needs_refund", "created_at"]
    list_filter = ["status", "provider", "method", "needs_refund"]
    search_fields = ["id", "order__id", "provider_reference"]
    # pagamento é registro financeiro: o admin só consulta
    readonly_fields = [f.name for f in Payment._meta.fields]
    actions = ["mark_refunded"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Registrar estorno JÁ realizado no provedor")
    def mark_refunded(self, request, queryset):
        done = 0
        for payment in queryset:
            try:
                services.mark_refunded(payment)
                done += 1
            except APIException as exc:
                self.message_user(request, f"Pagamento #{payment.pk}: {exc.detail}", level=messages.WARNING)
        if done:
            self.message_user(request, f"{done} estorno(s) registrado(s).")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["id", "provider", "event_id", "created_at"]
    search_fields = ["event_id"]
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
