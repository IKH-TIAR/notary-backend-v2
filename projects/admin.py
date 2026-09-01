from django.contrib import admin
from .models import Project, ProjectDocument


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'status', 'created_by', 'assigned_users_display', 'created_at']
    list_filter = ['status']
    search_fields = ['name']

    @admin.display(description='Assigned Users')
    def assigned_users_display(self, obj):
        users = obj.assigned_users.all()
        if not users:
            return '—'
        names = []
        for u in users:
            full = f'{u.first_name} {u.last_name}'.strip()
            names.append(full or u.email)
        return ', '.join(names)


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'title', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'project__name']
