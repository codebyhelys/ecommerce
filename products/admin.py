from django.contrib import admin

from .models import Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline]
    list_display = ["name", "price", "stock", "category", "is_active"]
    search_fields = ["name"]
    list_filter = ["is_active", "category"]
    autocomplete_fields = ["category"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"
    actions = ["activate", "deactivate"]

    @admin.action(description="Ativar produtos selecionados")
    def activate(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} produto(s) ativado(s).")

    @admin.action(description="Desativar produtos selecionados")
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} produto(s) desativado(s).")
