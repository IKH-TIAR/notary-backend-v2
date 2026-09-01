from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project, ProjectDocument
from .permissions import IsAdminRole
from .serializers import (
    AssignProjectSerializer,
    ProjectCreateSerializer,
    ProjectDocumentSerializer,
    ProjectSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _get_project_or_404(project_id):
    try:
        return Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
class ProjectListCreateView(APIView):
    """
    GET  /api/projects/  → list all projects
    POST /api/projects/  → create a project
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        projects = Project.objects.prefetch_related('assigned_users', 'documents').all()
        serializer = ProjectSerializer(projects, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            project = serializer.save()
            return Response(
                ProjectSerializer(project, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectDetailView(APIView):
    """
    DELETE /api/projects/<id>/  → delete a project
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def delete(self, request, project_id):
        project = _get_project_or_404(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectAssignView(APIView):
    """
    POST /api/projects/<id>/assign/  → assign users to a project
    Body: { "user_ids": [2, 5] }
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, project_id):
        project = _get_project_or_404(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssignProjectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_ids = serializer.validated_data['user_ids']
        users = User.objects.filter(id__in=user_ids)
        project.assigned_users.set(users)
        project.status = 'assigned'
        project.save()

        return Response(ProjectSerializer(project, context={'request': request}).data)


# ---------------------------------------------------------------------------
# Project Documents
# ---------------------------------------------------------------------------
class ProjectDocumentListCreateView(APIView):
    """
    GET  /api/projects/<id>/documents/  → list documents for a project
    POST /api/projects/<id>/documents/  → upload PDF + run AI analysis
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request, project_id):
        project = _get_project_or_404(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        docs = project.documents.all()
        return Response(
            ProjectDocumentSerializer(docs, many=True, context={'request': request}).data
        )

    def post(self, request, project_id):
        project = _get_project_or_404(project_id)
        if not project:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if not uploaded_file.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are allowed'}, status=status.HTTP_400_BAD_REQUEST)

        title = request.data.get('title', uploaded_file.name)

        # 1. Save or replace the document record.
        # If admin uploads again with the same title, reopen that document flow.
        doc = (
            ProjectDocument.objects
            .filter(project=project, title=title)
            .order_by('-created_at')
            .first()
        )

        if doc:
            # Best-effort cleanup of old files; do not block the upload if cleanup fails.
            try:
                import os
                if doc.file and os.path.isfile(doc.file.path):
                    os.remove(doc.file.path)
                if doc.hardcopy_file and os.path.isfile(doc.hardcopy_file.path):
                    os.remove(doc.hardcopy_file.path)
            except Exception:
                pass

            doc.file = uploaded_file
            doc.analysis = None
            doc.user_fields = None
            doc.hardcopy_file = None
            doc.verification = None
            doc.status = 'pending'
            doc.save()
        else:
            doc = ProjectDocument.objects.create(
                project=project,
                title=title,
                file=uploaded_file,
                status='pending',
            )

        # 2. Run AI analysis on the saved file
        try:
            from backend_ai_analysis import analyze_pdf
            analysis = analyze_pdf(doc.file.path, file_name=title)
            doc.analysis = analysis
            doc.status = 'in_progress'
            doc.save()

            # If project was finalized and admin uploaded a new version,
            # project should move back to in-progress.
            if project.status in ('completed', 'issue'):
                project.status = 'in_progress'
                project.save(update_fields=['status'])
        except Exception as exc:
            # Don't block the upload — leave analysis as null and log the error
            import traceback
            traceback.print_exc()
            print(f'[AI analysis] Failed for document {doc.id}: {exc}')

        serializer = ProjectDocumentSerializer(doc, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# User-facing views  (assigned users only – no admin role required)
# ---------------------------------------------------------------------------
class UserProjectListView(APIView):
    """
    GET /api/projects/my/
    Returns only the projects where the logged-in user is in assigned_users.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = (
            Project.objects
            .prefetch_related('assigned_users', 'documents')
            .filter(assigned_users=request.user)
        )
        serializer = ProjectSerializer(projects, many=True, context={'request': request})
        return Response(serializer.data)


class UserCompletedProjectListView(APIView):
    """
    GET /api/projects/my/completed/
    Returns only completed projects assigned to the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = (
            Project.objects
            .prefetch_related('assigned_users', 'documents')
            .filter(assigned_users=request.user, status='completed')
        )
        serializer = ProjectSerializer(projects, many=True, context={'request': request})
        return Response(serializer.data)


class UserProjectInfoView(APIView):
    """
    GET /api/projects/my/info/

    Returns user summary and project counts with frontend status mapping:
      - assigned/in_progress/pending -> pending
      - issue -> issue
      - completed -> done
    """
    permission_classes = [IsAuthenticated]

    STATUS_MAP = {
        'pending': 'pending',
        'assigned': 'pending',
        'in_progress': 'pending',
        'issue': 'issue',
        'completed': 'done',
    }

    def get(self, request):
        user = request.user
        projects = (
            Project.objects
            .filter(assigned_users=user)
            .order_by('-created_at')
        )

        full_name = f'{user.first_name} {user.last_name}'.strip() or user.email
        profile_picture = ''
        if getattr(user, 'profile_picture', None):
            uri = request.build_absolute_uri(user.profile_picture.url)
            profile_picture = uri.replace('http://', 'https://', 1) if not settings.DEBUG else uri

        pending_count = 0
        issue_count = 0
        done_count = 0

        for project in projects:
            mapped_status = self.STATUS_MAP.get(project.status, 'pending')

            if mapped_status == 'pending':
                pending_count += 1
            elif mapped_status == 'issue':
                issue_count += 1
            elif mapped_status == 'done':
                done_count += 1

        return Response({
            'name': full_name,
            'profile_picture': profile_picture,
            'pending': pending_count,
            'issue': issue_count,
            'done': done_count,
        })


class UserProjectDocumentListView(APIView):
    """
    GET /api/projects/my/<project_id>/documents/
    Returns the documents for a project only if the user is assigned to that project.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        try:
            project = (
                Project.objects
                .prefetch_related('documents')
                .get(pk=project_id, assigned_users=request.user)
            )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        docs = project.documents.all()
        serializer = ProjectDocumentSerializer(docs, many=True, context={'request': request})
        return Response(serializer.data)


class UserProjectDocumentDetailView(APIView):
    """
    GET /api/projects/my/<project_id>/documents/<doc_id>/
    Returns a single document with its full AI analysis,
    only if the user is assigned to the parent project.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, doc_id):
        # Verify the user is assigned to the project
        try:
            project = Project.objects.get(pk=project_id, assigned_users=request.user)
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fetch the document that belongs to that project
        try:
            doc = ProjectDocument.objects.get(pk=doc_id, project=project)
        except ProjectDocument.DoesNotExist:
            return Response(
                {'error': 'Document not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # First time a user opens a pending document, mark it in progress.
        if doc.status == 'pending':
            doc.status = 'in_progress'
            doc.save(update_fields=['status'])

        # User has started work; promote project from assigned to in_progress.
        if project.status == 'assigned':
            project.status = 'in_progress'
            project.save(update_fields=['status'])

        serializer = ProjectDocumentSerializer(doc, context={'request': request})
        return Response(serializer.data)


class UserDocumentSignView(APIView):
    """
    PATCH /api/projects/my/<project_id>/documents/<doc_id>/sign/

    User taps fields in-app to mark them as signed/unsigned.
    Body: { "fields": [ { "id": "field_1", "isSigned": true }, ... ] }

    Saves to user_fields without touching the original AI analysis.
    """
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, project_id, doc_id):
        try:
            project = Project.objects.get(pk=project_id, assigned_users=request.user)
        except Project.DoesNotExist:
            return None, Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            doc = ProjectDocument.objects.get(pk=doc_id, project=project)
        except ProjectDocument.DoesNotExist:
            return None, Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return doc, None

    def patch(self, request, project_id, doc_id):
        doc, err = self._get_doc(request, project_id, doc_id)
        if err:
            return err

        fields = request.data.get('fields')
        if not isinstance(fields, list):
            return Response(
                {'error': '"fields" must be a list of { id, isSigned } objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Merge into existing user_fields (keep any fields not in this update)
        existing = {f['id']: f for f in (doc.user_fields or []) if f.get('id')}
        for f in fields:
            fid = f.get('id')
            if fid:
                prev = existing.get(fid, {})
                existing[fid] = {
                    **prev,
                    **f,
                    # This is filled later by AI verification in /verify-all/.
                    'actually_signed': prev.get('actually_signed', None),
                }

        doc.user_fields = list(existing.values())
        doc.save()

        return Response(ProjectDocumentSerializer(doc, context={'request': request}).data)


class UserDocumentSubmitView(APIView):
    """
    POST /api/projects/my/<project_id>/documents/<doc_id>/submit/

    User uploads the scanned signed hardcopy PDF for a single document.
    Saves the file only — no AI runs here.
    AI verification runs later when the user calls /verify-all/.
    Can be re-called to replace a previously uploaded hardcopy.
    Returns the full document object with hardcopy_file populated, verification still null.
    """
    permission_classes = [IsAuthenticated]

    def _get_doc(self, request, project_id, doc_id):
        try:
            project = Project.objects.get(pk=project_id, assigned_users=request.user)
        except Project.DoesNotExist:
            return None, Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            doc = ProjectDocument.objects.get(pk=doc_id, project=project)
        except ProjectDocument.DoesNotExist:
            return None, Response({'error': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return doc, None

    def post(self, request, project_id, doc_id):
        doc, err = self._get_doc(request, project_id, doc_id)
        if err:
            return err

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if not uploaded_file.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Block re-upload if this document is already completed
        if doc.status == 'completed':
            return Response(
                {'error': 'This document is already completed and cannot be re-uploaded.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete the old hardcopy from disk if one already exists
        if doc.hardcopy_file:
            try:
                old_path = doc.hardcopy_file.path
                import os
                if os.path.isfile(old_path):
                    os.remove(old_path)
            except Exception:
                pass  # Don't block the upload if cleanup fails

        # Save the new hardcopy file and clear any stale verification
        # (verification is now outdated since the hardcopy changed)
        doc.hardcopy_file = uploaded_file
        doc.verification = None
        # Hardcopy changed; clear previous AI decisions and wait for next /verify-all/.
        if doc.user_fields:
            doc.user_fields = [
                {**f, 'actually_signed': None}
                for f in doc.user_fields if isinstance(f, dict)
            ]
        doc.status = 'in_progress'
        doc.save()

        return Response(ProjectDocumentSerializer(doc, context={'request': request}).data)


class UserProjectVerifyAllView(APIView):
    """
    POST /api/projects/my/<project_id>/verify-all/

    Triggered when the user presses "Upload all hard copies to submit".
    BLOCKED if any document in the project is missing a hardcopy_file.
    Once all hardcopies are present, runs AI verification for every document
    one by one, stores the result in each doc's verification field, and
    updates doc.status accordingly.
    Marks the project 'completed' only if every document passes.
    Otherwise marks the project 'issue'.
    Returns a full summary of all documents.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        try:
            project = Project.objects.prefetch_related('documents').get(
                pk=project_id, assigned_users=request.user
            )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        docs = list(project.documents.order_by('created_at'))

        # Block if any doc is missing a hardcopy
        missing_hardcopy = [d.title for d in docs if not d.hardcopy_file]
        if missing_hardcopy:
            return Response(
                {
                    'error': 'All documents must have a hardcopy uploaded before submitting.',
                    'missing': missing_hardcopy,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from backend_ai_analysis import verify_signed_pdf

        results = []
        for doc in docs:
            original_fields = (doc.analysis or {}).get('fields', [])
            user_fields = doc.user_fields or []
            try:
                verification = verify_signed_pdf(
                    hardcopy_source=doc.hardcopy_file.path,
                    original_fields=original_fields,
                    user_fields=user_fields,
                )
                doc.verification = verification

                # Push AI per-field actual signature result into user_fields.
                existing_user_fields = {
                    f.get('id'): f for f in (doc.user_fields or [])
                    if isinstance(f, dict) and f.get('id')
                }
                for fr in verification.get('field_results', []):
                    fid = fr.get('id')
                    if not fid:
                        continue
                    entry = existing_user_fields.get(fid, {'id': fid})
                    ai_signed = fr.get('actually_signed')
                    # Keep user tap and AI output in sync after verification.
                    entry['isSigned'] = ai_signed
                    entry['actually_signed'] = ai_signed
                    existing_user_fields[fid] = entry
                doc.user_fields = list(existing_user_fields.values())

                doc.status = 'completed' if verification.get('status') == 'completed' else 'issue'
                doc.save()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print(f'[AI verification] Failed for document {doc.id}: {exc}')
                doc.verification = {
                    'status': 'error',
                    'label': f'Verification failed: {exc}',
                    'signed_count': 0,
                    'total_count': len(original_fields),
                    'field_results': [],
                }
                doc.status = 'issue'
                doc.save()

            results.append({
                'id':           doc.id,
                'title':        doc.title,
                'status':       doc.status,
                'verification': doc.verification,
            })

        # Set project status from verification outcome
        all_done = all(
            r['verification'] and r['verification'].get('status') == 'completed'
            for r in results
        )
        project.status = 'completed' if all_done else 'issue'
        project.save(update_fields=['status'])

        return Response({
            'project_status': project.status,
            'documents':      results,
        })


class UserProjectAnalysisView(APIView):
    """
    GET /api/projects/my/<project_id>/analysis/

    Returns the AI analysis + verification data for every document in the project,
    ordered by creation date (first uploaded → first in list).

    Each entry contains:
      - id, title, file_url, hardcopy_file_url
      - status
      - analysis       → original AI field-detection result
      - user_fields    → fields the user tapped as signed in-app
      - verification   → AI cross-check result against the hardcopy:
            {
              "status":        "completed" | "needs_fix" | "error",
              "signed_count":  int,
              "total_count":   int,
              "label":         "4 of 5 signed correctly",
              "field_results": [
                  {
                    "id": "...",
                    "label": "...",
                    "user_claimed_signed": bool,
                    "actually_signed": bool,
                    "match": bool,
                    "note": "..."
                  }, ...
              ]
            }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        try:
            project = Project.objects.prefetch_related('documents').get(
                pk=project_id, assigned_users=request.user
            )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found or you are not assigned to it.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        docs = project.documents.order_by('created_at')
        documents_data = []

        for doc in docs:
            file_url = None
            if doc.file:
                file_uri = request.build_absolute_uri(doc.file.url)
                file_url = file_uri.replace('http://', 'https://', 1) if not settings.DEBUG else file_uri

            hardcopy_url = None
            if doc.hardcopy_file:
                hardcopy_uri = request.build_absolute_uri(doc.hardcopy_file.url)
                hardcopy_url = hardcopy_uri.replace('http://', 'https://', 1) if not settings.DEBUG else hardcopy_uri

            # Build mismatch list: fields user claimed as signed in-app,
            # but AI found as not signed on the uploaded hardcopy.
            issues = []
            verification = doc.verification or {}
            for fr in verification.get('field_results', []):
                user_claimed_signed = fr.get('user_claimed_signed', False)
                actually_signed = fr.get('actually_signed', True)
                if user_claimed_signed and not actually_signed:
                    issues.append({
                        'field_id':    fr.get('id'),
                        'label':       fr.get('label'),
                        'user_claimed_signed': user_claimed_signed,
                        'actually_signed': actually_signed,
                        'note':        fr.get('note', 'Not signed'),
                        'page':        next(
                            (f.get('page') for f in (doc.analysis or {}).get('fields', [])
                             if f.get('id') == fr.get('id')),
                            None,
                        ),
                    })

            documents_data.append({
                'id':               doc.id,
                'title':            doc.title,
                'file_url':         file_url,
                'hardcopy_file_url': hardcopy_url,
                'status':           doc.status,
                'analysis':         doc.analysis,
                'user_fields':      doc.user_fields,
                'verification':     verification if verification else None,
                'issues':           issues,
            })

        return Response({
            'project_id':     project.id,
            'project_name':   project.name,
            'project_status': project.status,
            'total_documents': len(documents_data),
            'documents':      documents_data,
        })


class ProjectDocumentDetailView(APIView):
    """
    PATCH /api/projects/<projectId>/documents/<docId>/
      → save edited analysis after admin reviews fields in the viewer
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def _get_doc(self, project_id, doc_id):
        try:
            return ProjectDocument.objects.get(pk=doc_id, project_id=project_id)
        except ProjectDocument.DoesNotExist:
            return None

    def patch(self, request, project_id, doc_id):
        doc = self._get_doc(project_id, doc_id)
        if not doc:
            return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)

        if 'analysis' in request.data:
            doc.analysis = request.data['analysis']
            doc.save()

        serializer = ProjectDocumentSerializer(doc, context={'request': request})
        return Response(serializer.data)
