from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets

from products.models import Product

from . import services
from .models import Review
from .serializers import ReviewSerializer


class AuthorOrStaffCanDelete(permissions.BasePermission):
    """Ler é público; editar só o autor; apagar o autor ou a equipe (moderação)."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.pk == obj.user_id:
            return True
        return request.method == "DELETE" and request.user.is_staff


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, AuthorOrStaffCanDelete]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]  # sem PUT: PATCH basta

    def get_product(self):
        if not hasattr(self, "_product"):
            products = Product.objects.all() if self.request.user.is_staff else Product.objects.filter(is_active=True)
            self._product = get_object_or_404(products, slug=self.kwargs["product_slug"])
        return self._product

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do esquema OpenAPI, sem produto na URL
            return Review.objects.none()
        return Review.objects.filter(product=self.get_product()).select_related("user")

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.create_review(
            user=self.request.user,
            product=self.get_product(),
            rating=data["rating"],
            comment=data.get("comment", ""),
        )
