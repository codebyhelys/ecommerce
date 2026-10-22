from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException

from .filters import ProductFilter
from .models import Category, Product
from .permissions import IsAdminOrReadOnly
from .serializers import CategorySerializer, ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category")
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        # soft delete: desativa em vez de apagar, para preservar o histórico de pedidos
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class CategoryInUse(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Categoria possui produtos e não pode ser removida."
    default_code = "category_in_use"


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        return Category.objects.annotate(products_count=Count("products", filter=Q(products__is_active=True))).order_by(
            "name"
        )

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise CategoryInUse() from None
