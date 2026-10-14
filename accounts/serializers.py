from django.contrib.auth import authenticate, get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "password"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("já existe uma conta com esse email")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs.get("email"), first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", ""),)
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
        
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(request=self.context.get("request"), email=attrs["email"].strip().lower(), password=attrs["password"],)
        if user is None:
            raise serializers.ValidationError("E-mail ou senha inválidos.", code="authorization")
        attrs["user"] = user
        return attrs
    
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields =  ["id", "email", "first_name", "last_name", "date_joined"]
        read_only_fields = ["id", "email", "date_joined"]
