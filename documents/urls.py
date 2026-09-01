from django.urls import path
from .views import (
    DashboardStatsView,
    DocumentListCreateView,
    DocumentDetailView,
    AssignUsersView,
    UserListView,
    ToggleUserStatusView,
)

urlpatterns = [
    path('stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/toggle-status/', ToggleUserStatusView.as_view(), name='toggle-user-status'),
    path('', DocumentListCreateView.as_view(), name='document-list-create'),
    path('<int:pk>/', DocumentDetailView.as_view(), name='document-detail'),
    path('<int:pk>/assign/', AssignUsersView.as_view(), name='document-assign-users'),
]
