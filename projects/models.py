from django.db import models
from django.conf import settings


def project_document_upload_path(instance, filename):
    return f'projects/{instance.project_id}/{filename}'


def project_hardcopy_upload_path(instance, filename):
    return f'projects/{instance.project_id}/hardcopies/{filename}'


class Project(models.Model):
    STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('assigned',    'Assigned'),
        ('in_progress', 'In Progress'),
        ('issue',       'Issue'),
        ('completed',   'Completed'),
    ]

    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_projects',
    )
    assigned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_projects',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']


class ProjectDocument(models.Model):
    STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('in_progress', 'In Progress'),
        ('issue',       'Issue'),
        ('completed',   'Completed'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=project_document_upload_path)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    analysis = models.JSONField(null=True, blank=True)

    # User's tap-confirmed field statuses (which fields they marked as signed in-app)
    user_fields = models.JSONField(null=True, blank=True)

    # The scanned/signed hardcopy PDF uploaded by the user
    hardcopy_file = models.FileField(
        upload_to=project_hardcopy_upload_path, null=True, blank=True
    )

    # AI cross-verification result comparing user claims vs hardcopy
    verification = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.project.name} – {self.title}'

    class Meta:
        ordering = ['-created_at']
