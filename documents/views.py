from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .models import Document
from .permissions import IsAdminRole
from .serializers import (
    DocumentSerializer,
    DocumentCreateSerializer,
    AssignUsersSerializer,
    DashboardStatsSerializer,
    AssignedUserSerializer,
    UserManagementSerializer,
)
from projects.models import Project

User = get_user_model()


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        stats = {
            'total_projects': Project.objects.count(),
            'pending_projects': Project.objects.filter(status='pending').count(),
            'assigned_projects': Project.objects.filter(status='assigned').count(),
            'in_progress_projects': Project.objects.filter(status='in_progress').count(),
            'completed_projects': Project.objects.filter(status='completed').count(),
            'total_users': User.objects.filter(role='USER').count(),
        }
        serializer = DashboardStatsSerializer(stats)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        search = request.query_params.get('search', None)
        documents = Document.objects.all()
        if search:
            documents = documents.filter(title__icontains=search)
        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DocumentCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_object(self, pk):
        try:
            return Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return None

    def get(self, request, pk):
        document = self.get_object(pk)
        if not document:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        document = self.get_object(pk)
        if not document:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        document.delete()
        return Response(
            {'message': 'Document deleted successfully'},
            status=status.HTTP_204_NO_CONTENT
        )


class AssignUsersView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response(
                {'error': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AssignUsersSerializer(data=request.data)
        if serializer.is_valid():
            user_ids = serializer.validated_data['user_ids']
            users = User.objects.filter(id__in=user_ids, role='USER')
            document.assigned_users.set(users)
            return Response(
                {'message': 'Users assigned successfully'},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserListView(APIView):
    """Admin can view list of all users to assign to documents"""
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        users = User.objects.filter(role='USER')
        serializer = UserManagementSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ToggleUserStatusView(APIView):
    """Admin can activate or deactivate a user"""
    permission_classes = [IsAuthenticated, IsAdminRole]

    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role='USER')
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        user.is_active = not user.is_active
        user.save()

        return Response(
            {
                'message': f'User {"activated" if user.is_active else "deactivated"} successfully',
                'is_active': user.is_active
            },
            status=status.HTTP_200_OK
        )
