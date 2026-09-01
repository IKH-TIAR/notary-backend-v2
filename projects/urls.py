from django.urls import path
from .views import (
    ProjectAssignView,
    ProjectDetailView,
    ProjectDocumentDetailView,
    ProjectDocumentListCreateView,
    ProjectListCreateView,
    UserProjectListView,
    UserCompletedProjectListView,
    UserProjectInfoView,
    UserProjectDocumentListView,
    UserProjectDocumentDetailView,
    UserDocumentSignView,
    UserDocumentSubmitView,
    UserProjectVerifyAllView,
    UserProjectAnalysisView,
)

urlpatterns = [
    # ── Admin endpoints ──────────────────────────────────────────────────
    path('', ProjectListCreateView.as_view(), name='project-list-create'),
    path('<int:project_id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/assign/', ProjectAssignView.as_view(), name='project-assign'),
    path('<int:project_id>/documents/', ProjectDocumentListCreateView.as_view(), name='project-document-list-create'),
    path('<int:project_id>/documents/<int:doc_id>/', ProjectDocumentDetailView.as_view(), name='project-document-detail'),

    # ── User-facing endpoints (filtered by assigned_users) ───────────────
    path('my/', UserProjectListView.as_view(), name='user-project-list'),
    path('my/info/', UserProjectInfoView.as_view(), name='user-project-info'),
    path('my/completed/', UserCompletedProjectListView.as_view(), name='user-completed-project-list'),
    path('my/<int:project_id>/documents/', UserProjectDocumentListView.as_view(), name='user-project-document-list'),
    path('my/<int:project_id>/documents/<int:doc_id>/', UserProjectDocumentDetailView.as_view(), name='user-project-document-detail'),
    path('my/<int:project_id>/documents/<int:doc_id>/sign/', UserDocumentSignView.as_view(), name='user-document-sign'),
    path('my/<int:project_id>/documents/<int:doc_id>/submit/', UserDocumentSubmitView.as_view(), name='user-document-submit'),
    path('my/<int:project_id>/verify-all/', UserProjectVerifyAllView.as_view(), name='user-project-verify-all'),
    path('my/<int:project_id>/analysis/', UserProjectAnalysisView.as_view(), name='user-project-analysis'),
]
