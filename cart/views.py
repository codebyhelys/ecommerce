from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import AddItemSerializer, CartSerializer, QuantitySerializer


def cart_response(user, status_code=status.HTTP_200_OK):
    return Response(CartSerializer(services.get_cart(user)).data, status=status_code)


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return cart_response(request.user)

    def delete(self, request):
        services.clear_cart(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_item(request.user, **serializer.validated_data)
        return cart_response(request.user, status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, slug):
        serializer = QuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_quantity(request.user, slug, serializer.validated_data["quantity"])
        return cart_response(request.user)

    def delete(self, request, slug):
        services.remove_item(request.user, slug)
        return cart_response(request.user)