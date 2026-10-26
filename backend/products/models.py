import uuid
from decimal import Decimal
from pathlib import Path

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .validators import validate_image_format, validate_image_size


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["is_active", "-created_at"], name="product_active_created_idx")]

    def __str__(self):
        return self.name


def product_image_path(instance, filename):
    # nome aleatório: ignora o que o cliente mandou (colisões, caracteres estranhos, tentativa de path traversal)
    return f"products/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class ProductImage(models.Model):
    MAX_PER_PRODUCT = 8

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=product_image_path, validators=[validate_image_size, validate_image_format])
    alt_text = models.CharField(max_length=150, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product} #{self.position}"


@receiver(post_delete, sender=ProductImage)
def delete_image_file(sender, instance, **kwargs):
    # o arquivo só some depois do commit: se a transação desfizer, a imagem continua existindo no banco
    if instance.image:
        storage, name = instance.image.storage, instance.image.name
        transaction.on_commit(lambda: storage.delete(name))
