from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "created_at"]
    list_filter = ["rating"]
    search_fields = ["product__name", "user__email", "comment"]
    readonly_fields = ["product", "user", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False
