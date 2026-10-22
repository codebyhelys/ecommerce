from django.urls import path
from knox.views import LogoutAllView, LogoutView

from .views import LoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("logoutall/", LogoutAllView.as_view(), name="auth-logoutall"),
    path("me/", MeView.as_view(), name="auth-me"),
]
