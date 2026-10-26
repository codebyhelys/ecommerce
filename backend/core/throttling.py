from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AnonThrottle(AnonRateThrottle):
    """Limite por IP para quem não está logado. A taxa é lida das settings a cada requisição."""

    def get_rate(self):
        return settings.THROTTLE_ANON_RATE


class UserThrottle(UserRateThrottle):
    """Limite por usuário logado."""

    def get_rate(self):
        return settings.THROTTLE_USER_RATE
