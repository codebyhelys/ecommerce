from rest_framework import serializers

from .models import Category, Product, ProductImage


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "products_count"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "position"]


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews_count = serializers.SerializerMethodField()
    rating_average = serializers.SerializerMethodField()
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "stock",
            "category",
            "category_id",
            "images",
            "reviews_count",
            "rating_average",
            "is_active",
            "created_at",
            "updated_at",
        ]

    # anotados pela view (uma consulta só na listagem); fora dela (ex.: resposta de criação) não há avaliações
    def get_reviews_count(self, product) -> int:
        return getattr(product, "reviews_count", 0)

    def get_rating_average(self, product) -> float | None:
        average = getattr(product, "rating_average", None)
        return None if average is None else round(float(average), 1)

    def update(self, instance, validated_data):
        # grava só o que foi enviado: um save() completo sobrescreveria o estoque que um checkout
        # concorrente acabou de baixar
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save(update_fields=[*validated_data, "updated_at"])
        return instance
