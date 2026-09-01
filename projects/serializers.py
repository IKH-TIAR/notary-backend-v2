from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, ProjectDocument

User = get_user_model()


class ProjectUserSerializer(serializers.ModelSerializer):
    """Slim user representation expected by the frontend: { id, name }"""
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name']

    def get_name(self, obj):
        full = f'{obj.first_name} {obj.last_name}'.strip()
        return full or obj.email


class ProjectDocumentSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()
    hardcopy_file = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = [
            'id', 'title', 'file', 'status',
            'analysis',
            'user_fields',
            'hardcopy_file',
            'verification',
            'created_at',
        ]

    def get_file(self, obj):
        """Return an absolute URL so the frontend can load the PDF directly."""
        if not obj.file:
            return None
        url = obj.file.url
        request = self.context.get('request')
        if request:
            uri = request.build_absolute_uri(url)
            return uri.replace('http://', 'https://', 1) if not settings.DEBUG else uri
        return url

    def get_hardcopy_file(self, obj):
        """Return an absolute URL for the uploaded signed hardcopy PDF."""
        if not obj.hardcopy_file:
            return None
        url = obj.hardcopy_file.url
        request = self.context.get('request')
        if request:
            uri = request.build_absolute_uri(url)
            return uri.replace('http://', 'https://', 1) if not settings.DEBUG else uri
        return url


class ProjectSerializer(serializers.ModelSerializer):
    assigned_users = ProjectUserSerializer(many=True, read_only=True)
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'status', 'document_count', 'assigned_users', 'created_at']

    def get_document_count(self, obj):
        return obj.documents.count()


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['name']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        return super().create(validated_data)


class AssignProjectSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
