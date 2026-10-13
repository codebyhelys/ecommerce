from rest_framework import viewsets, permissions
from .models import Product
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    lookup_field = "slug"

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        qs = Product.objects.select_related("category")
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        # soft delete: desativa em vez de apagar, para preservar o histórico de pedidos
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])