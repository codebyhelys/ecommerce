from django.contrib import admin

from .models import Coupon, CouponRedemption


class CouponRedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    can_delete = False
    readonly_fields = ["user", "order", "discount", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "kind", "value", "is_active", "expires_at", "usage_limit", "uses"]
    list_filter = ["kind", "is_active"]
    search_fields = ["code", "description"]
    readonly_fields = ["created_at"]
    inlines = [CouponRedemptionInline]

    @admin.display(description="Usos")
    def uses(self, obj):
        return obj.redemptions.count()
