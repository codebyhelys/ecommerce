from rest_framework import viewsets, permissions
from .models import Product
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action in ("list", "retrive"):
            return [permissions.AllowAny()]
        return[permissions.IsAdminUser]

    def get_queryset(self):
        qs = Product.objects.select_related("category")
        if not self.request.user.is_staff:
            qs = qs.filter(is_active=True)
        return qs