# ./django/your_app/serializers.py
from rest_framework_mongoengine import serializers
from .models import LoginUser

class LoginUserSerializer(serializers.DocumentSerializer):
    class Meta:
        model = LoginUser
        fields = '__all__'
        read_only_fields = ('id',)
