from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()
    comment = serializers.CharField(max_length=1000, allow_blank=True, required=False)

    class Meta:
        model = Review
        fields = ["id", "rating", "comment", "author", "mine", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def get_author(self, review) -> str:
        return review.user.first_name or "Cliente"  # nunca o e-mail

    def get_mine(self, review) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and request.user.pk == review.user_id)
