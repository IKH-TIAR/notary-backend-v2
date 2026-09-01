from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Document

User = get_user_model()


class AssignedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']


class UserManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'is_active']


class DocumentSerializer(serializers.ModelSerializer):
    assigned_users = AssignedUserSerializer(many=True, read_only=True)
    created_by = AssignedUserSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            'id',
            'title',
            'file',
            'status',
            'assigned_users',
            'issues',
            'created_by',
            'created_at',
            'updated_at',
        ]


class DocumentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'title', 'file', 'status', 'issues']

    def validate_file(self, value):
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError("Only PDF files are allowed.")
        if value.size > 10 * 1024 * 1024:  # 10MB limit
            raise serializers.ValidationError("File size must not exceed 10MB.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        return super().create(validated_data)


class AssignUsersSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )

    def validate_user_ids(self, value):
        users = User.objects.filter(id__in=value, role='USER')
        if users.count() != len(value):
            raise serializers.ValidationError("One or more user IDs are invalid.")
        return value


class DashboardStatsSerializer(serializers.Serializer):
    total_projects = serializers.IntegerField()
    pending_projects = serializers.IntegerField()
    assigned_projects = serializers.IntegerField()
    in_progress_projects = serializers.IntegerField()
    completed_projects = serializers.IntegerField()
    total_users = serializers.IntegerField()
