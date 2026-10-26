from drf_spectacular.utils import extend_schema, inline_serializer
from knox.views import LoginView as KnoxLoginView
from knox.views import LogoutAllView as KnoxLogoutAllView
from knox.views import LogoutView as KnoxLogoutView
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.serializers import DetailSerializer

from . import services
from .models import Address
from .serializers import (
    AddressSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"


class LoginView(KnoxLoginView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses=inline_serializer(
            "LoginResponse",
            {"token": serializers.CharField(), "expiry": serializers.DateTimeField()},
        ),
    )
    def post(self, request, format=None):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user = serializer.validated_data["user"]
        return super().post(request, format=None)


class LogoutView(KnoxLogoutView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, format=None):
        return super().post(request, format=format)


class LogoutAllView(KnoxLogoutAllView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, format=None):
        return super().post(request, format=format)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # no máximo 10 por conta

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do esquema OpenAPI, sem usuário
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_address(self.request.user, serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.update_address(serializer.instance, serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_address(instance)


class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(request.user, serializer.validated_data["new_password"], keep_token=request.auth)
        return Response({"detail": "Senha alterada."})


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        # mesma resposta exista a conta ou não: não revela quais e-mails estão cadastrados
        return Response({"detail": "Se o e-mail estiver cadastrado, enviaremos as instruções."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses=DetailSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(**serializer.validated_data)
        return Response({"detail": "Senha redefinida. Entre com a nova senha."}, status=status.HTTP_200_OK)
