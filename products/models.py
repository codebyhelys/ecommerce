from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name_plural = "categoriies"

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=10, unique=True)
    description = models.TextField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    categorie = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="produts")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

