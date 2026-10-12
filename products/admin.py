from django.contrib import admin
from .models import Produto, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "stock", "category", "is_active"]
    search_fields = ["name"]
    list_filter = ["is_active", "category"]
    prepopulated_fields = {"slug": ("name",)}