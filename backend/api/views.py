import random
import math
import re
import secrets
import logging
import urllib.error
import urllib.parse
import urllib.request
import json
from dataclasses import asdict
from datetime import datetime
from django.conf import settings
from django.core import signing
from django.shortcuts import redirect
from django.utils import timezone
from django.contrib.auth import get_user_model, authenticate
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Project, 
    ContactInquiry, 
    EstimationRecord, 
    DeploymentRecord, 
    WaitlistSubscriber,
        GitHubConnection,
    AWSConnection,
    EC2Instance,
    default_estimation,
    default_recommendation,
    default_deployment,
    default_optimizations
)
from .serializers import (
    UserProfileSerializer,
    UserSignupSerializer,
    UserLoginSerializer,
    ProjectSerializer,
    ContactInquirySerializer,
    EstimationRecordSerializer,
    DeploymentRecordSerializer,
    WaitlistSubscriberSerializer
)
from .permissions import IsProjectRolePermission
from .services.deployment_file_generator import generate_deployment_files
from .services.github_service import GitHubApiError, push_files_to_repository
from .services.github_repository_service import inspect_repository, RepositoryLimitError
from .services.tech_stack_detector import (
    UnsupportedTechStackError,
    analyze_repository,
    detect_tech_stack,
)
from .services.aws_pricing_service import AwsPricingError, get_aws_price_snapshot
from .services.free_tier_policy import FreeTierLimitError, validate_free_tier_deployment, evaluate_free_tier_eligibility
from .services.deployment.pipeline import (
    append_log,
    fail_deployment,
    start_pipeline,
)
from .services.deployment.status import DeploymentStage, DeploymentStatus
from .services.deployment.aws_connection_service import (
    AwsConnectionError,
    build_policies,
    connect as aws_connect,
    connection_public_dict,
    disconnect as aws_disconnect,
    ensure_pending_connection,
    platform_credentials_configured,
)
from .services.deployment.aws_ec2_provider import AwsEc2Error, AwsEc2Provider

User = get_user_model()

logger = logging.getLogger(__name__)

# Salt for the signed OAuth `state` parameter (CSRF protection). It keeps the
# GitHub state value in a namespace of its own so a signed value issued for a
# different purpose can never be replayed as an OAuth state.
GITHUB_OAUTH_STATE_SALT = 'cloudwise.github.oauth.start'


def get_user_github_connection(user):
    """Return the GitHubConnection attached to a CloudWise user, or None."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    try:
        return user.github_connection
    except GitHubConnection.DoesNotExist:
        return None
    except Exception:  # pragma: no cover - defensive (schema not migrated yet)
        logger.exception(
            "Unable to read GitHub connection for CloudWise user %s",
            getattr(user, 'pk', None),
        )
        return None


def get_user_github_token(user):
    """Return (connection, decrypted_github_token) for a CloudWise user."""
    connection = get_user_github_connection(user)
    if connection is None:
        return None, None
    return connection, connection.get_token()


# Helper to extract user identity and role from headers / auth
def get_request_user_info(request):
    user_id = request.headers.get('x-user-id', 'default_user')
    user_role = request.headers.get('x-user-role', 'owner')
    user_obj = None

    if request.user and request.user.is_authenticated:
        user_obj = request.user
        user_id = str(user_obj.id)
        user_role = getattr(user_obj, 'role', user_role)

    return user_id, user_role, user_obj


# -------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def signup_view(request):
    serializer = UserSignupSerializer(data=request.data)
    if not serializer.is_valid():
        errors = serializer.errors
        error_msg = 'Validation error.'
        if 'email' in errors:
            error_msg = errors['email'][0]
        elif 'password' in errors:
            error_msg = errors['password'][0]
        elif 'name' in errors:
            error_msg = errors['name'][0]
        
        return Response({
            'success': False,
            'error': error_msg,
            'details': errors
        }, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'success': True,
        'message': 'Account created successfully!',
        'token': str(refresh.access_token),
        'user': UserProfileSerializer(user).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'error': 'Email address and password are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email'].strip().lower()
    password = serializer.validated_data['password']

    try:
        user_obj = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Invalid email or password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    if not user_obj.check_password(password):
        return Response({
            'success': False,
            'error': 'Invalid email or password.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user_obj)

    return Response({
        'success': True,
        'message': 'Signed in successfully.',
        'token': str(refresh.access_token),
        'user': UserProfileSerializer(user_obj).data
    }, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# Projects API Endpoints (Module 2 & RBAC Module 10)
# -------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def projects_list_create_view(request):
    user = request.user
    user_role = getattr(user, 'role', 'owner') or 'owner'

    if request.method == 'GET':
        projects = Project.objects.filter(user=user).order_by('-created_at')
        serializer = ProjectSerializer(projects, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        role = request.data.get('role', user_role)
        if role == 'viewer' or user_role == 'viewer':
            return Response({
                'success': False,
                'error': 'Access Denied (RBAC): Users with "Viewer" role cannot create new projects.'
            }, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({
                'success': False,
                'error': 'Project name is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        description = request.data.get('description', '').strip() or 'Cloud infrastructure workload project'
        environment = request.data.get('environment', 'Production')

        project = Project.objects.create(
            user=user,
            user_id_str=str(user.id),
            name=name,
            description=description,
            environment=environment,
            user_role=role,
            current_step='estimation',
            estimation={},
            selected_recommendation=None,
            deployment=None,
            optimizations=None
        )

        return Response({
            'success': True,
            'message': 'Project created successfully',
            'data': ProjectSerializer(project).data
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def project_detail_view(request, pk):
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Project not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    # Strict user ownership check
    if project.user_id != request.user.id:
        return Response({
            'success': False,
            'error': 'Access Denied: You do not have permission to access this project.'
        }, status=status.HTTP_403_FORBIDDEN)

    user_role = getattr(request.user, 'role', project.user_role) or project.user_role

    if request.method == 'GET':
        return Response({
            'success': True,
            'data': ProjectSerializer(project).data
        }, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        if user_role == 'viewer' or project.user_role == 'viewer':
            return Response({
                'success': False,
                'error': 'Access Denied (RBAC): Read-only "Viewer" role cannot modify project settings.'
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        if 'name' in data and data['name'].strip():
            project.name = data['name'].strip()
        if 'description' in data:
            project.description = data['description']
        if 'environment' in data:
            project.environment = data['environment']
        if 'userRole' in data:
            project.user_role = data['userRole']
        if 'currentStep' in data:
            project.current_step = data['currentStep']
        if 'estimation' in data:
            project.estimation = data['estimation']
        if 'selectedRecommendation' in data:
            project.selected_recommendation = data['selectedRecommendation']
        if 'githubRepo' in data:
            project.github_repo = data['githubRepo']
        if 'deployment' in data:
            project.deployment = data['deployment']
        if 'optimizations' in data:
            project.optimizations = data['optimizations']

        project.save()

        return Response({
            'success': True,
            'message': 'Project updated successfully',
            'data': ProjectSerializer(project).data
        }, status=status.HTTP_200_OK)

    elif request.method == 'DELETE':
        if user_role not in ['owner', 'admin']:
            return Response({
                'success': False,
                'error': 'Access Denied (RBAC): Only project Owner or Admin can delete a project.'
            }, status=status.HTTP_403_FORBIDDEN)

        project.delete()
        return Response({
            'success': True,
            'message': 'Project deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def estimate_view_free_tier_stub(request):
    """Stub endpoint for free-tier evaluation — kept for backwards compat."""
    data = request.data or {}
    try:
        vcpu = int(data.get('vcpu', 8))
        ram = int(data.get('ram', 32))
        storage = int(data.get('storage', 500))
    except (ValueError, TypeError):
        vcpu, ram, storage = 8, 32, 500

    evaluation = evaluate_free_tier_eligibility(
        vcpu=vcpu,
        ram_gb=ram,
        storage_gb=storage,
        instances=1
    )
    return Response({'success': True, 'freeTierStatus': evaluation}, status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def project_github_connect_view(request, pk):
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Project not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    if project.user_id != request.user.id:
        return Response({
            'success': False,
            'error': 'Access Denied: You do not have permission to access this project.'
        }, status=status.HTTP_403_FORBIDDEN)

    user_role = getattr(request.user, 'role', project.user_role) or project.user_role
    if user_role == 'viewer' or project.user_role == 'viewer':
        return Response({
            'success': False,
            'error': 'Access Denied (RBAC): Viewer role cannot link GitHub repository.'
        }, status=status.HTTP_403_FORBIDDEN)

    repo_name = request.data.get('repoName', 'org/app-cloudwise')
    now_str = datetime.now().strftime("%I:%M:%S %p %m/%d/%Y")

    github_repo = {
        'name': repo_name,
        'connectedAt': now_str,
        'synced': True,
        'files': ['Dockerfile', '.github/workflows/deploy.yml', 'docker-compose.yml']
    }

    project.github_repo = github_repo
    project.current_step = 'generate'
    project.save()

    return Response({
        'success': True,
        'message': f'Successfully connected GitHub repository {repo_name} and synced generated deployment artifacts!',
        'data': ProjectSerializer(project).data
    }, status=status.HTTP_200_OK)


def require_cloudwise_user(request):
    """Return a {success, error} 401 envelope when the caller is not signed in.

    GitHub endpoints answer with the project envelope instead of DRF's bare
    {"detail": ...} so the React client can show a real message.
    """
    if request.user.is_authenticated:
        return None
    return Response({
        'success': False,
        'code': 'AUTH_REQUIRED',
        'error': 'Please sign in to CloudWise before using GitHub features.',
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def project_github_push_view(request, pk):
    unauthorized = require_cloudwise_user(request)
    if unauthorized is not None:
        return unauthorized
    try:
        project = Project.objects.get(pk=pk, user=request.user)
    except Project.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Project not found or access denied.'
        }, status=status.HTTP_404_NOT_FOUND)

    if project.user_role == 'viewer' or request.user.role == 'viewer':
        return Response({
            'success': False,
            'error': 'Access Denied (RBAC): Viewer role cannot push files.'
        }, status=status.HTTP_403_FORBIDDEN)

    files = request.data.get('files')
    commit_message = request.data.get('commit_message', 'Add CloudWise deployment configuration')
    repository = project.github_repo or {}
    if not isinstance(files, dict) or not files:
        return Response({
            'success': False,
            'error': 'Generated files must be provided as a non-empty object.'
        }, status=status.HTTP_400_BAD_REQUEST)
    if not repository.get('name'):
        return Response({
            'success': False,
            'error': 'Select a GitHub repository before pushing files.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        connection = request.user.github_connection
        result = push_files_to_repository(
            connection.get_token(),
            repository,
            files,
            commit_message,
        )
    except GitHubConnection.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Connect a GitHub account before pushing files.'
        }, status=status.HTTP_400_BAD_REQUEST)
    except (GitHubApiError, ValueError) as exc:
        return Response({
            'success': False,
            'error': str(exc)
        }, status=status.HTTP_502_BAD_GATEWAY)

    return Response({
        'success': True,
        'message': 'CloudWise deployment files committed successfully.',
        'data': result,
    }, status=status.HTTP_200_OK)


def _run_repository_inspection(user, repository, persist_project=None):
    """Scan a repository using *this* CloudWise user's GitHub authorization.

    Returns a DRF Response. When ``persist_project`` is given, the scanned
    tree is persisted on that project (project-scoped endpoint).
    """
    access_token = None
    try:
        connection = user.github_connection
        access_token = connection.get_token()
    except GitHubConnection.DoesNotExist:
        pass

    # Progress callback for the frontend scan UI
    _progress_items = []
    def _progress(stage: str, message: str, pct: int):
        _progress_items.append({'stage': stage, 'message': message, 'progress': pct})

    try:
        inspection = inspect_repository(
            access_token, repository, progress_callback=_progress,
        )
        try:
            stack = detect_tech_stack(inspection['files'])
            stack_data = asdict(stack)
        except UnsupportedTechStackError:
            stack_data = None

        analysis = analyze_repository(
            inspection.get('files') or {},
            tree=inspection.get('tree') or [],
            repository_size=inspection.get('repositorySize') or {},
        )

        repo_info = inspection.get('repository', {})
        repo_dict = repo_info if isinstance(repo_info, dict) else {}
        repo_full_name = repo_dict.get('full_name') if repo_dict else str(repo_info)
        updated_github_repo = {
            'name': repo_full_name,
            'owner': repo_dict.get('owner', '') if repo_dict else '',
            'defaultBranch': inspection.get('branch', 'main'),
            'commitSha': inspection.get('commitSha', ''),
            'synced': True,
            'scannedAt': inspection.get('scannedAt'),
            'totalFiles': inspection.get('totalFiles', 0),
            'totalDirectories': inspection.get('totalDirectories', 0),
            'tree': inspection.get('tree', []),
            'files': list(inspection.get('files', {}).keys()),
        }
        if persist_project is not None:
            persist_project.github_repo = updated_github_repo
            persist_project.save(update_fields=['github_repo', 'updated_at'])

        return Response({
            'status': 'SUCCESS',
            'success': True,
            'data': {
                'repository': inspection.get('repository'),
                'branch': inspection.get('branch'),
                'commitSha': inspection.get('commitSha'),
                'commitMessage': inspection.get('commitMessage', ''),
                'commitDate': inspection.get('commitDate', ''),
                'tree': inspection.get('tree', []),
                'files': inspection.get('files', {}),
                'totalFiles': inspection.get('totalFiles', 0),
                'totalDirectories': inspection.get('totalDirectories', 0),
                'truncated': inspection.get('truncated', False),
                'scannedAt': inspection.get('scannedAt'),
                'technology': stack_data,
                'has_dockerfile': inspection.get('has_dockerfile', False),
                'has_compose': inspection.get('has_compose', False),
                'has_cicd': inspection.get('has_cicd', False),
                'visibility': repo_dict.get('visibility', ''),
                **analysis,
            },
            'progress': _progress_items,
        }, status=status.HTTP_200_OK)
    except RepositoryLimitError as exc:
        return Response({
            'status': 'ERROR',
            'code': 'REPOSITORY_LIMIT_EXCEEDED',
            'success': False,
            'error': str(exc),
            'message': str(exc),
        }, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    except ValueError as exc:
        return Response({
            'status': 'ERROR',
            'code': 'INVALID_REPOSITORY_DATA',
            'success': False,
            'error': str(exc),
            'message': str(exc)
        }, status=status.HTTP_400_BAD_REQUEST)
    except GitHubApiError as exc:
        st_code = getattr(exc, 'status_code', 502)
        code_map = {
            400: 'BAD_REQUEST',
            401: 'GITHUB_AUTH_FAILED',
            403: 'GITHUB_PERMISSION_DENIED',
            404: 'GITHUB_REPO_NOT_FOUND',
            409: 'GITHUB_REPOSITORY_NOT_CONFIGURED',
            422: 'INVALID_REPOSITORY_DATA',
            429: 'GITHUB_RATE_LIMITED',
            502: 'GITHUB_UPSTREAM_ERROR',
        }
        err_code = code_map.get(st_code, 'GITHUB_API_ERROR')

        if st_code in (401, 403) and isinstance(repository, dict) and repository.get('tree'):
            cached_tree = repository.get('tree', [])
            cached_files_list = repository.get('files', [])
            token_expired = st_code == 401
            rate_limited = st_code == 403
            cached_files_map = {f: '' for f in cached_files_list}
            cached_analysis = analyze_repository(
                cached_files_map,
                tree=cached_tree,
            )
            if not cached_analysis.get('repositorySize'):
                cached_analysis['repositorySize'] = {
                    'totalBytes': sum(int(n.get('size') or 0) for n in cached_tree if isinstance(n, dict) and n.get('type') == 'file'),
                    'fileCount': len([n for n in cached_tree if isinstance(n, dict) and n.get('type') == 'file']),
                }
            return Response({
                'status': 'SUCCESS',
                'success': True,
                'cached': True,
                'token_expired': token_expired,
                'rate_limited': rate_limited,
                'data': {
                    'repository': {
                        'owner': repository.get('owner', ''),
                        'name': repository.get('name', ''),
                        'full_name': repository.get('name', ''),
                        'defaultBranch': repository.get('defaultBranch', 'main'),
                    },
                    'branch': repository.get('defaultBranch', 'main'),
                    'commitSha': repository.get('commitSha', ''),
                    'tree': cached_tree,
                    'files': cached_files_map,
                    'totalFiles': repository.get('totalFiles', len([n for n in cached_tree if n.get('type') == 'file'])),
                    'totalDirectories': repository.get('totalDirectories', 0),
                    'truncated': False,
                    'scannedAt': repository.get('scannedAt'),
                    'technology': None,
                    'has_dockerfile': False,
                    'has_compose': False,
                    'has_cicd': False,
                    **cached_analysis,
                },
                'progress': _progress_items,
            }, status=status.HTTP_200_OK)

        res_status = st_code if st_code in (400, 401, 403, 404, 409, 422, 429, 500, 502) else status.HTTP_500_INTERNAL_SERVER_ERROR
        error_message = str(exc)
        if access_token is None and st_code in (401, 404):
            error_message = (
                f"{error_message} Connect your GitHub account "
                "(Authorize GitHub Account) to access private repositories."
            )
        return Response({
            'status': 'ERROR',
            'code': err_code,
            'success': False,
            'error': error_message,
            'message': error_message,
            'details': getattr(exc, 'details', str(exc)),
            'token_expired': st_code == 401,
            'rate_limited': st_code == 429,
            'progress': _progress_items,
        }, status=res_status)
    except Exception as exc:
        return Response({
            'status': 'ERROR',
            'code': 'INTERNAL_SERVER_ERROR',
            'success': False,
            'error': 'An unexpected error occurred while scanning the repository.',
            'details': str(exc)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def project_github_inspect_view(request, pk):
    unauthorized = require_cloudwise_user(request)
    if unauthorized is not None:
        return unauthorized
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({
            'status': 'ERROR',
            'code': 'PROJECT_NOT_FOUND',
            'success': False,
            'error': 'Project not found or access denied.'
        }, status=status.HTTP_404_NOT_FOUND)

    if project.user_id != request.user.id:
        return Response({
            'status': 'ERROR',
            'code': 'PROJECT_ACCESS_DENIED',
            'success': False,
            'error': 'Project not found or access denied.'
        }, status=status.HTTP_404_NOT_FOUND)

    # Always prefer the repoName supplied by the caller.  A stale
    # project.github_repo must never shadow a fresh selection.
    body_repo_name = (request.data.get('repoName') or '').strip()
    if body_repo_name:
        repository = {'name': body_repo_name}
    else:
        repository = project.github_repo or {}

    if not repository or (isinstance(repository, dict) and not repository.get('name')):
        return Response({
            'status': 'ERROR',
            'code': 'GITHUB_REPOSITORY_NOT_CONFIGURED',
            'success': False,
            'error': 'Select and connect a GitHub repository before inspecting it.'
        }, status=status.HTTP_409_CONFLICT)

    return _run_repository_inspection(request.user, repository, persist_project=project)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def github_repository_inspect_view(request, repo_path):
    """Inspect an arbitrary ``owner/repo`` using the caller's GitHub token.

    Used by the deployment pipeline, which analyses a repository directly
    instead of through a CloudWise project.
    """
    unauthorized = require_cloudwise_user(request)
    if unauthorized is not None:
        return unauthorized
    repository_name = (request.data.get('repoName') or '').strip() or repo_path.strip()
    if not repository_name:
        return Response({
            'status': 'ERROR',
            'code': 'GITHUB_REPOSITORY_NOT_CONFIGURED',
            'success': False,
            'error': 'Provide a repository in owner/repo form.'
        }, status=status.HTTP_400_BAD_REQUEST)

    return _run_repository_inspection(request.user, {'name': repository_name})


# -------------------------------------------------------------
# Core Application Endpoints
# -------------------------------------------------------------

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def contact_view(request):
    serializer = ContactInquirySerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'error': 'Missing required fields: name, email, and message are required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    record = serializer.save()
    return Response({
        'success': True,
        'message': 'Your inquiry has been successfully transmitted to our cloud engineering team.',
        'data': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def estimate_view(request):
    data = request.data or {}
    app_type = data.get('appType', 'Microservices & Web APIs')
    vcpu_num = int(data.get('vcpu', 8))
    ram_num = int(data.get('ram', 32))
    storage_num = int(data.get('storage', 500))
    traffic = data.get('traffic', '1,000,000 req/day')
    region = data.get('region', 'Gujarat (GIFT City / Gandhinagar)')
    performance_tier = data.get('performanceTier', 'High Performance')
    budget_tier = data.get('budgetTier', 'Balanced')

    target_region = region.lower()
    region_multiplier = 1.0
    if 'gujarat' in target_region:
        region_multiplier = 0.92
    elif 'bengaluru' in target_region:
        region_multiplier = 1.05
    elif 'kolkata' in target_region:
        region_multiplier = 0.96

    # Cost calculation in INR (₹)
    base_cost = round((vcpu_num * 1000 + ram_num * 200 + storage_num * 6) * region_multiplier)
    min_cost = round(base_cost * 0.85)
    max_cost = round(base_cost * 1.25)
    suggested_instances = max(1, math.ceil(vcpu_num / 4))
    bandwidth_gb = round(ram_num * 15 + vcpu_num * 30)

    calculated_result = {
        'minCost': min_cost,
        'maxCost': max_cost,
        'suggestedInstances': suggested_instances,
        'bandwidthGB': bandwidth_gb
    }

    record = EstimationRecord.objects.create(
        app_type=app_type,
        vcpu=vcpu_num,
        ram=ram_num,
        storage=storage_num,
        traffic=traffic,
        region=region,
        performance_tier=performance_tier,
        budget_tier=budget_tier,
        calculated_result=calculated_result
    )

    return Response({
        'success': True,
        'data': EstimationRecordSerializer(record).data
    }, status=status.HTTP_200_OK)


def _project_type_label(detection: dict) -> str:
    """Compact human label for the detected stack (shown on the details page)."""
    detection = detection or {}
    parts = [
        str(detection.get('frontend') or '').strip(),
        str(detection.get('backend') or '').strip(),
    ]
    label = ' + '.join(p for p in parts if p)
    if not label:
        label = str(detection.get('applicationType') or '').strip() or 'UNKNOWN'
    database = str(detection.get('database') or '').strip()
    if database:
        label = f'{label} / {database}'
    return label[:150]


def _prepare_repository_payload(user, project_id, data, env_vars):
    """
    Shared pre-flight for creating a deployment and for retrying one.

    Resolves the user's project, reads the linked GitHub repository,
    generates the deployment files, validates the environment variables
    and checks the user's AWS connection.

    Returns ``(payload, project, None)`` on success, or
    ``(None, None, Response)`` carrying a stage-tagged, actionable error:

        PROJECT     — project missing or not owned by this user
        GITHUB      — repository not linked / unreadable
        ENVIRONMENT — missing or invalid environment variables
        AWS         — no AWS connection for this user
    """
    # ----------------------------------------------------------------
    # Stage: PROJECT
    # ----------------------------------------------------------------
    project = None
    if project_id:
        project = Project.objects.filter(pk=project_id, user=user).first()
        if project is None:
            return None, None, Response({
                'success': False,
                'stage': 'PROJECT',
                'error': f'Project "{project_id}" not found.',
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        project = Project.objects.filter(user=user).order_by('-updated_at').first()

    if project is None:
        return None, None, Response({
            'success': False,
            'stage': 'PROJECT',
            'error': 'No active project found. Create a project first.',
        }, status=status.HTTP_400_BAD_REQUEST)

    # ----------------------------------------------------------------
    # Stage: GITHUB
    # ----------------------------------------------------------------
    github_repo = project.github_repo or {}
    repo_name = str(github_repo.get('name', '')).strip()
    if not repo_name or '/' not in repo_name:
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'error': (
                'No GitHub repository linked to this project. '
                'Authorize GitHub and select a repository first.'
            ),
            'connectUrl': '/generate',
        }, status=status.HTTP_400_BAD_REQUEST)

    github_connection = get_user_github_connection(user)
    if github_connection is None:
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'error': 'GitHub account not connected. Authorize GitHub first.',
            'connectUrl': '/generate',
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        github_token = github_connection.get_token()
    except Exception:  # noqa: BLE001 — decryption/rotation failure
        logger.exception("Stored GitHub token unreadable for user %s", user.pk)
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'error': (
                'Stored GitHub authorization could not be read. '
                'Re-authorize your GitHub account and try again.'
            ),
            'connectUrl': '/generate',
        }, status=status.HTTP_400_BAD_REQUEST)

    # Imported here so the repository reader is resolved at call time.
    from .services.github_repository_service import inspect_repository

    try:
        inspection = inspect_repository(github_token, github_repo)
    except RepositoryLimitError as exc:
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'code': 'REPOSITORY_LIMIT_EXCEEDED',
            'error': str(exc),
        }, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    except Exception as exc:
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'error': f'Cannot access GitHub repository "{repo_name}": {exc}',
        }, status=status.HTTP_400_BAD_REQUEST)

    repo_files = inspection.get('files') or {}
    tree = inspection.get('tree') or []

    try:
        generated = generate_deployment_files(repo_files, provider='AWS', tree=tree)
    except (TypeError, ValueError) as exc:
        return None, None, Response({
            'success': False,
            'stage': 'GITHUB',
            'error': str(exc),
        }, status=status.HTTP_400_BAD_REQUEST)

    deploy_files = {**repo_files, **(generated.get('files') or {})}
    # Never upload GitHub Actions workflows to the instance.
    deploy_files = {
        k: v for k, v in deploy_files.items()
        if not str(k).replace('\\', '/').startswith('.github/')
    }
    deployment_plan = generated.get('deploymentPlan') or {}
    app_port = int(generated.get('port') or 80)
    detection = generated.get('detection') or {}

    # ----------------------------------------------------------------
    # Stage: ENVIRONMENT
    # ----------------------------------------------------------------
    env_vars = {str(k): str(v) for k, v in dict(env_vars or {}).items() if k}

    required_env = list(deployment_plan.get('requiredEnvVars') or [])
    missing_env = [
        key for key in required_env
        if not str(env_vars.get(key, '')).strip()
    ]
    if missing_env:
        return None, None, Response({
            'success': False,
            'stage': 'ENVIRONMENT',
            'code': 'MISSING_ENV_VARS',
            'error': (
                'Missing required environment variable(s): '
                + ', '.join(missing_env)
                + '. Provide them before deploying (see .env.example in '
                'your repository).'
            ),
            'missing': missing_env,
            'required': required_env,
        }, status=status.HTTP_400_BAD_REQUEST)

    allowed_schemes = getattr(
        settings, 'AWS_ALLOWED_DB_URL_SCHEMES',
        ('postgres://', 'postgresql://', 'mysql://', 'mongodb://'),
    )
    for url_key in ('DATABASE_URL', 'MONGO_URI', 'MONGODB_URI', 'REDIS_URL'):
        raw_url = env_vars.get(url_key, '')
        if not raw_url:
            continue
        lowered = raw_url.strip().lower()
        if not any(lowered.startswith(s) for s in allowed_schemes):
            return None, None, Response({
                'success': False,
                'stage': 'ENVIRONMENT',
                'code': 'INVALID_DATABASE_URL',
                'error': (
                    f'{url_key} has an invalid scheme. Expected one of: '
                    + ', '.join(allowed_schemes)
                    + f' (got "{raw_url.split(":", 1)[0]}:...").'
                ),
                'field': url_key,
            }, status=status.HTTP_400_BAD_REQUEST)

    # ----------------------------------------------------------------
    # Stage: AWS — the user must have connected their own account
    # ----------------------------------------------------------------
    aws_connection = AWSConnection.objects.filter(
        user=user, status='active'
    ).first()
    if aws_connection is None:
        return None, None, Response({
            'success': False,
            'stage': 'AWS',
            'status': 'BLOCKED',
            'error': (
                'BLOCKED — AWS account not connected. '
                'Connect your AWS account (IAM role) to deploy to AWS EC2.'
            ),
            'required': ['AWS_ROLE_ARN'],
            'connectUrl': '/connect-aws',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    payload = {
        'project_id': str(project.pk),
        'environment_name': str(
            data.get('environmentName')
            or f"{project.name.lower().replace(' ', '-')}-prod"
        ),
        'region': str(data.get('region') or aws_connection.region),
        'instance_type': str(data.get('instanceType') or ''),
        'force_new_instance': bool(data.get('forceNewInstance', False)),
        'files': deploy_files,
        'env_vars': env_vars,
        'port': app_port,
        'detection': detection,
        'deployment_plan': deployment_plan,
        'specs': dict(data.get('specs') or {}),
        'monthly_cost': data.get('monthlyCost', 0),
        'repository': repo_name,
        'commit_sha': str(inspection.get('commitSha') or ''),
        'project_type': _project_type_label(detection),
        'aws_connection': aws_connection,
        'github_connection': github_connection,
    }
    return payload, project, None


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deploy_view(request):
    """
    Create a deployment of the user's GitHub repository into the same
    user's AWS account.

    Fast, actionable checks run synchronously (see
    ``_prepare_repository_payload`` for the stage-tagged errors).
    Provisioning, container deployment and health checks run on the
    background pipeline (api.services.deployment.pipeline) and are
    observed through:

        GET  /api/deployments                      — list mine
        GET  /api/deployments/<id>                 — full details
        GET  /api/deployments/<id>/status          — live status
        GET  /api/deployments/<id>/logs            — structured logs
        POST /api/deployments/<id>/health          — real HTTP health check
        POST /api/deployments/<id>/retry           — rerun a failed deploy
        POST /api/deployments/<id>/terminate       — terminate my EC2 instance
    """
    data = request.data or {}
    provider_name = str(data.get('provider', 'AWS')).strip()
    project_id = str(data.get('projectId', '')).strip()

    # Retired providers — AWS EC2 is the only active target.
    if provider_name.upper() in ('VERCEL', 'RENDER'):
        return Response({
            'success': False,
            'stage': 'PROJECT',
            'status': 'RETIRED',
            'error': (
                f'{provider_name} deployments are retired. '
                'CloudWise deploys to AWS EC2 only. '
                'Connect your AWS account and redeploy there.'
            ),
            'required': ['AWS_ROLE_ARN'],
            'connectUrl': '/connect-aws',
            'supported': ['AWS'],
        }, status=status.HTTP_400_BAD_REQUEST)

    if provider_name.upper() != 'AWS':
        return Response({
            'success': False,
            'stage': 'AWS',
            'error': f'Unknown provider "{provider_name}". Supported: AWS.',
            'supported': ['AWS'],
        }, status=status.HTTP_400_BAD_REQUEST)

    payload, project, error = _prepare_repository_payload(
        request.user, project_id, data, data.get('envVars') or {},
    )
    if error is not None:
        return error

    aws_connection = payload.pop('aws_connection')
    github_connection = payload.pop('github_connection')
    commit_sha = payload['commit_sha']
    commit_suffix = f' @ {commit_sha[:7]}' if commit_sha else ''

    record = DeploymentRecord.objects.create(
        user=request.user,
        project=project,
        github_connection=github_connection,
        aws_connection=aws_connection,
        environment_name=payload['environment_name'],
        repository=payload['repository'],
        commit_sha=commit_sha,
        project_type=payload['project_type'],
        provider='AWS',
        aws_account_id=aws_connection.account_id or '',
        region=payload['region'],
        instance_id='',
        instance_type=payload['instance_type'],
        monthly_cost=payload['monthly_cost'],
        specs=payload['specs'],
        deployment_status=DeploymentStatus.QUEUED,
        ip_address=None,
        live_url=None,
        logs=[{
            'timestamp': timezone.now().isoformat(),
            'level': 'INFO',
            'stage': DeploymentStage.PREPARING,
            'message': (
                f'Queued deployment of {payload["repository"]}{commit_suffix} '
                f'({payload["project_type"]}) to AWS account '
                f'{aws_connection.account_id or "connected"} in '
                f'{payload["region"]}.'
            ),
        }],
    )

    start_pipeline(record.id, payload)
    record.refresh_from_db()
    return Response({
        'success': True,
        'stage': 'QUEUED',
        'message': (
            f'Deployment {record.id} started for {payload["repository"]} '
            f'in {payload["region"]}.'
        ),
        'deployment_id': record.id,
        'data': DeploymentRecordSerializer(record).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def waitlist_view(request):
    email = request.data.get('email', '').strip().lower()
    source = request.data.get('source', 'home_page')

    if not email:
        return Response({
            'success': False,
            'error': 'Email address is required.'
        }, status=status.HTTP_400_BAD_REQUEST)

    serializer = WaitlistSubscriberSerializer(data={'email': email, 'source': source})
    if not serializer.is_valid():
        return Response({
            'success': False,
            'error': 'Please enter a valid email address.'
        }, status=status.HTTP_400_BAD_REQUEST)

    record = serializer.save()
    return Response({
        'success': True,
        'message': 'Successfully subscribed to CloudWise updates and early access releases!',
        'data': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def monitoring_view(request):
    """
    Real telemetry for the *calling user's* most recent deployment.

    Every value is either measured or derived from this user's own
    DeploymentRecord. CloudWise does not install a metrics agent on the
    instance, so CPU / memory / storage are returned as ``null`` with
    ``metricsCollected: false`` rather than being invented.
    """
    latest = (
        DeploymentRecord.objects.filter(user=request.user)
        .order_by('-created_at')
        .first()
    )

    payload = {
        'metricsCollected': False,
        'cpuUsage': None,
        'memoryUsage': None,
        'storageUsage': None,
        'networkInMB': None,
        'networkOutMB': None,
        'deploymentId': None,
        'deploymentStatus': None,
        'healthStatus': 'Not deployed',
        'clusterUptime': '0d 00h 00m',
        'activeNodes': 0,
        'ipAddress': None,
        'instanceId': None,
        'instanceType': None,
        'region': None,
        'awsAccountId': None,
        'endpointUrl': None,
    }

    if latest is None:
        return Response({'success': True, 'data': payload}, status=status.HTTP_200_OK)

    status_value = latest.deployment_status
    payload.update({
        'deploymentId': latest.pk,
        'deploymentStatus': status_value,
        'ipAddress': latest.ip_address or None,
        'instanceId': latest.instance_id or None,
        'instanceType': latest.instance_type or None,
        'region': latest.region,
        'awsAccountId': latest.aws_account_id or None,
        'endpointUrl': latest.live_url or None,
        'activeNodes': 1 if latest.instance_id else 0,
    })

    active_statuses = (
        DeploymentStatus.QUEUED,
        DeploymentStatus.PREPARING,
        DeploymentStatus.BUILDING,
        DeploymentStatus.DEPLOYING,
        DeploymentStatus.HEALTH_CHECK,
    )
    if status_value in active_statuses:
        payload['healthStatus'] = 'Deploying'
    elif status_value == DeploymentStatus.FAILED:
        payload['healthStatus'] = 'Failed'
    elif status_value in (DeploymentStatus.RUNNING, 'deployed', 'RUNNING'):
        payload['healthStatus'] = (
            'Healthy' if latest.live_url else 'Running — awaiting live URL'
        )
    else:
        payload['healthStatus'] = status_value

    if status_value in (DeploymentStatus.RUNNING, 'deployed', 'RUNNING'):
        payload['clusterUptime'] = _format_uptime(latest.created_at)
        if latest.live_url:
            healthy, http_status = _probe_url(latest.live_url)
            payload['healthStatus'] = 'Healthy' if healthy else 'Unhealthy'
            payload['httpStatus'] = http_status

    return Response({'success': True, 'data': payload}, status=status.HTTP_200_OK)


def _format_uptime(since) -> str:
    delta = timezone.now() - since
    total = int(delta.total_seconds())
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    return f'{days}d {hours:02d}h {minutes:02d}m'


def _probe_url(url: str, timeout: float = 5.0):
    """Real HTTP GET against the live URL. Returns (healthy, http_status)."""
    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('User-Agent', 'CloudWise-Monitoring/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500, resp.status
    except urllib.error.HTTPError as exc:
        return exc.code < 500, exc.code
    except Exception:  # noqa: BLE001 — unreachable/timeout is the signal
        return False, None


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_view(request):
    return Response({
        'status': 'ok',
        'service': 'CloudWise API Backend (Django REST Framework)',
        'version': '1.2.0',
        'timestamp': timezone.now().isoformat()
    }, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# GitHub OAuth — connect the *current* CloudWise user's GitHub account.
#
# Flow:
#   React  --(JWT)-->  GET /api/github/oauth/start
#        --> GitHub authorize page (signed `state` carries the CloudWise user id)
#        --> GET /api/github/oauth/callback?code&state        (browser redirect)
#        --> backend exchanges the code, stores an ENCRYPTED per-user token
#        --> redirect back to the React app (?github=connected)
#
# The GitHub access token never leaves the backend.
# -------------------------------------------------------------

def _github_oauth_missing_config():
    missing = []
    if not settings.GITHUB_CLIENT_ID:
        missing.append('GITHUB_CLIENT_ID')
    if not settings.GITHUB_CLIENT_SECRET:
        missing.append('GITHUB_CLIENT_SECRET')
    return missing


def _github_oauth_state_payload(user_id):
    """Signed, tamper-proof state binding the OAuth round-trip to one user."""
    return signing.dumps(
        {'uid': str(user_id), 'nonce': secrets.token_urlsafe(32)},
        salt=GITHUB_OAUTH_STATE_SALT,
    )


def _github_oauth_load_state(state):
    """Verify the state (CSRF check). Returns (payload, error_code)."""
    try:
        payload = signing.loads(
            state or '',
            max_age=getattr(settings, 'GITHUB_OAUTH_STATE_MAX_AGE', 600),
            salt=GITHUB_OAUTH_STATE_SALT,
        )
    except signing.SignatureExpired:
        return None, 'state_expired'
    except signing.BadSignature:
        return None, 'state_invalid'
    if not isinstance(payload, dict) or not payload.get('uid'):
        return None, 'state_invalid'
    return payload, None


def _map_github_token_error(github_error):
    """Translate GitHub's OAuth error slug into a safe frontend error code."""
    return {
        'bad_verification_code': 'invalid_code',
        'expired_code': 'invalid_code',
        'redirect_uri_mismatch': 'redirect_uri_mismatch',
        'incorrect_client_credentials': 'bad_client_credentials',
        'invalid_client': 'bad_client_credentials',
        'unauthorized_client': 'bad_client_credentials',
        'access_denied': 'access_denied',
        'unsupported_grant_type': 'exchange_failed',
    }.get(github_error, 'exchange_failed')


def _github_oauth_frontend_redirect(result, detail=None):
    """Send the browser back to React with a safe, non-sensitive error code."""
    params = {'github': result}
    if detail:
        params['github_detail'] = detail
    return redirect(f'{settings.FRONTEND_URL}/generate?{urllib.parse.urlencode(params)}')


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_oauth_start_view(request):
    # The signed state carries the CloudWise user id, so we must know who is
    # connecting. Always answer with the {success, error} envelope (never DRF's
    # bare {"detail": ...}) so the React client can show the real reason.
    if not request.user.is_authenticated:
        return Response({
            'success': False,
            'code': 'AUTH_REQUIRED',
            'error': 'Please sign in to CloudWise before connecting your GitHub account.',
        }, status=status.HTTP_401_UNAUTHORIZED)

    missing = _github_oauth_missing_config()
    if missing:
        logger.error(
            "GitHub OAuth start rejected: missing environment variable(s) %s. "
            "Copy backend/.env.example to backend/.env and fill them in.",
            ', '.join(missing),
        )
        return Response({
            'success': False,
            'code': 'GITHUB_OAUTH_NOT_CONFIGURED',
            'error': (
                'GitHub OAuth is not configured on the server. Set '
                + ', '.join(missing)
                + ' in backend/.env (see backend/.env.example), then restart the backend.'
            ),
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not settings.GITHUB_REDIRECT_URI.startswith(('http://', 'https://')):
        logger.error(
            "GitHub OAuth start rejected: GITHUB_REDIRECT_URI is not an absolute URL (%r).",
            settings.GITHUB_REDIRECT_URI,
        )
        return Response({
            'success': False,
            'code': 'GITHUB_REDIRECT_URI_INVALID',
            'error': 'GITHUB_REDIRECT_URI must be an absolute http(s) URL.',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    state = _github_oauth_state_payload(request.user.pk)
    authorization_url = 'https://github.com/login/oauth/authorize?' + urllib.parse.urlencode({
        'client_id': settings.GITHUB_CLIENT_ID,
        'redirect_uri': settings.GITHUB_REDIRECT_URI,
        'scope': settings.GITHUB_OAUTH_SCOPES,
        'response_type': 'code',
        'state': state,
        'allow_signup': 'true',
    })

    logger.info(
        "Starting GitHub OAuth for CloudWise user=%s (redirect_uri=%s, scope=%r).",
        request.user.pk, settings.GITHUB_REDIRECT_URI, settings.GITHUB_OAUTH_SCOPES,
    )

    return Response({
        'success': True,
        'authorizationUrl': authorization_url,
        'redirectUri': settings.GITHUB_REDIRECT_URI,
        'scopes': settings.GITHUB_OAUTH_SCOPES,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_oauth_callback_view(request):
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    github_error = request.query_params.get('error')
    github_error_description = request.query_params.get('error_description')

    # 1. GitHub can bounce back with an error (user pressed Cancel,
    #    redirect_uri mismatch, bad client credentials, ...).
    if github_error:
        logger.warning(
            "GitHub OAuth returned error=%r description=%r (state present=%s).",
            github_error, github_error_description, bool(state),
        )
        return _github_oauth_frontend_redirect('error', github_error)

    # 2. Verify the signed state. This is the CSRF check and it also carries
    #    the CloudWise user id that started the flow, so the GitHub token is
    #    always stored against the right account.
    state_data, state_error = _github_oauth_load_state(state)
    if state_error or not code:
        reason = state_error or 'missing_code'
        logger.warning(
            "GitHub OAuth callback rejected (%s): state valid=%s, code present=%s.",
            reason, state_data is not None, bool(code),
        )
        return Response({
            'success': False,
            'code': reason.upper(),
            'error': 'Invalid or expired GitHub authorization state. Please try authorizing again.',
        }, status=status.HTTP_400_BAD_REQUEST)

    missing = _github_oauth_missing_config()
    if missing:
        logger.error(
            "GitHub OAuth callback rejected: missing environment variable(s) %s.",
            ', '.join(missing),
        )
        return Response({
            'success': False,
            'code': 'GITHUB_OAUTH_NOT_CONFIGURED',
            'error': (
                'GitHub OAuth is not configured on the server. Set '
                + ', '.join(missing) + ' in backend/.env (see backend/.env.example).'
            ),
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    user_id = state_data['uid']
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        logger.error("GitHub OAuth callback: CloudWise user %s no longer exists.", user_id)
        return _github_oauth_frontend_redirect('error', 'cloudwise_user_missing')

    # 3. Exchange the authorization code for an access token — server side only.
    try:
        token_payload = urllib.parse.urlencode({
            'client_id': settings.GITHUB_CLIENT_ID,
            'client_secret': settings.GITHUB_CLIENT_SECRET,
            'code': code,
            'redirect_uri': settings.GITHUB_REDIRECT_URI,
        }).encode()
        token_request = urllib.request.Request(
            'https://github.com/login/oauth/access_token',
            data=token_payload,
            headers={'Accept': 'application/json', 'User-Agent': 'CloudWise'},
            method='POST',
        )
        with urllib.request.urlopen(token_request, timeout=15) as response:
            token_data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors='replace')
        logger.error(
            "GitHub token exchange failed with HTTP %s for CloudWise user %s: %s",
            exc.code, user_id, details,
        )
        return _github_oauth_frontend_redirect('error', 'exchange_failed')
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        logger.error(
            "GitHub token exchange failed for CloudWise user %s: %s", user_id, exc,
        )
        return _github_oauth_frontend_redirect('error', 'exchange_failed')

    access_token = token_data.get('access_token')
    if not access_token:
        github_error = token_data.get('error') or 'unknown_error'
        logger.error(
            "GitHub token exchange rejected for CloudWise user %s: error=%r "
            "description=%r (client_id set=%s, redirect_uri=%s).",
            user_id,
            github_error,
            token_data.get('error_description'),
            bool(settings.GITHUB_CLIENT_ID),
            settings.GITHUB_REDIRECT_URI,
        )
        return _github_oauth_frontend_redirect(
            'error', _map_github_token_error(github_error),
        )

    # 4. Identify the GitHub account that was actually authorized.
    try:
        profile_request = urllib.request.Request(
            'https://api.github.com/user',
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'CloudWise',
            },
        )
        with urllib.request.urlopen(profile_request, timeout=15) as response:
            profile = json.loads(response.read().decode())
        github_login = profile.get('login', '')
        if not github_login:
            raise ValueError('GitHub profile did not include a login.')
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors='replace')
        logger.error(
            "GitHub /user lookup failed with HTTP %s for CloudWise user %s: %s",
            exc.code, user_id, details,
        )
        return _github_oauth_frontend_redirect('error', 'profile_failed')
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError, AttributeError) as exc:
        logger.error(
            "GitHub /user lookup failed for CloudWise user %s: %s", user_id, exc,
        )
        return _github_oauth_frontend_redirect('error', 'profile_failed')

    # 5. Persist exactly one connection per CloudWise user, token encrypted.
    try:
        connection, _created = GitHubConnection.objects.get_or_create(user=user)
        connection.set_token(access_token)
        connection.github_user_id = str(profile.get('id', ''))
        connection.github_login = github_login
        connection.scopes = token_data.get('scope') or settings.GITHUB_OAUTH_SCOPES
        connection.status = 'connected'
        connection.save()
    except Exception:
        logger.exception(
            "Failed to store the GitHub connection for CloudWise user %s.", user_id,
        )
        return _github_oauth_frontend_redirect('error', 'save_failed')

    logger.info(
        "GitHub OAuth completed: CloudWise user=%s -> GitHub %s (id=%s), scopes=%r.",
        user_id, connection.github_login, connection.github_user_id, connection.scopes,
    )
    return redirect(f'{settings.FRONTEND_URL}/generate?github=connected')



@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_repositories_view(request):
    # Repositories are always resolved from the *authenticated* CloudWise
    # user's own GitHub connection — never from a shared/global token.
    unauthorized = require_cloudwise_user(request)
    if unauthorized is not None:
        return unauthorized
    connection = get_user_github_connection(request.user)
    if connection is None:
        return Response({
            'success': False,
            'code': 'GITHUB_NOT_CONNECTED',
            'error': 'Connect a GitHub account before retrieving repositories. Use "Authorize GitHub Account" first.'
        }, status=status.HTTP_400_BAD_REQUEST)

    token = connection.get_token()
    if not token:
        connection.status = 'expired'
        connection.save(update_fields=['status', 'updated_at'])
        return Response({
            'success': False,
            'code': 'GITHUB_TOKEN_MISSING',
            'error': 'No GitHub access token is stored for your account. Re-authorize your GitHub account.'
        }, status=status.HTTP_401_UNAUTHORIZED)

    github_request = urllib.request.Request(
        'https://api.github.com/user/repos?sort=updated&per_page=100',
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'User-Agent': 'CloudWise',
        },
    )
    try:
        with urllib.request.urlopen(github_request, timeout=15) as response:
            repositories = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors='replace')
        if exc.code == 401:
            connection.status = 'expired'
            connection.save(update_fields=['status', 'updated_at'])
            logger.warning(
                "GitHub /user/repos returned 401 for CloudWise user %s (GitHub account %s).",
                request.user.pk, connection.github_login,
            )
            return Response({
                'success': False,
                'code': 'GITHUB_TOKEN_EXPIRED',
                'error': 'GitHub token is invalid or expired. Re-authorize your GitHub account.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        if exc.code == 403:
            rate_limited = 'rate limit' in details.lower()
            logger.warning(
                "GitHub /user/repos returned 403 for CloudWise user %s: %s",
                request.user.pk, details,
            )
            return Response({
                'success': False,
                'code': 'GITHUB_RATE_LIMITED' if rate_limited else 'GITHUB_FORBIDDEN',
                'error': (
                    'GitHub API rate limit exceeded. Please wait and try again.'
                    if rate_limited else
                    'GitHub denied access to your repositories. Re-authorize your GitHub account.'
                )
            }, status=status.HTTP_403_FORBIDDEN)
        if exc.code == 404:
            return Response({
                'success': False,
                'code': 'GITHUB_REPO_NOT_FOUND',
                'error': 'GitHub repository not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        if exc.code == 429:
            return Response({
                'success': False,
                'code': 'GITHUB_RATE_LIMITED',
                'error': 'GitHub API rate limit exceeded. Please wait and try again.'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        logger.error(
            "GitHub /user/repos returned HTTP %s for CloudWise user %s: %s",
            exc.code, request.user.pk, details,
        )
        return Response({
            'success': False,
            'code': 'GITHUB_UPSTREAM_ERROR',
            'error': f'GitHub API returned HTTP {exc.code}. Please try again later.'
        }, status=status.HTTP_502_BAD_GATEWAY)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.error(
            "GitHub /user/repos request failed for CloudWise user %s: %s",
            request.user.pk, exc,
        )
        return Response({
            'success': False,
            'code': 'GITHUB_UPSTREAM_ERROR',
            'error': 'Unable to retrieve GitHub repositories: the GitHub API could not be reached.'
        }, status=status.HTTP_502_BAD_GATEWAY)

    return Response({
        'success': True,
        'data': [{
            'id': repo.get('id'),
            'name': repo.get('name'),
            'full_name': repo.get('full_name'),
            'private': repo.get('private'),
            'default_branch': repo.get('default_branch'),
        } for repo in repositories]
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def ai_recommend_view(request):
    return Response({
        'success': True,
        'status': 'stub_pending_ml_model',
        'message': 'CloudWise ML inference stub called.',
        'aiRecommendations': {
            'suggestedVcpu': 6,
            'suggestedRam': 24,
            'confidenceScore': 0.94,
            'predictedCostSavingsPercent': 28.5
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def terraform_export_view(request):
    provider = request.data.get('provider', 'aws')
    return Response({
        'success': True,
        'status': 'stub_ready',
        'provider': provider,
        'filename': f'main_{provider.lower()}.tf',
        'hclSnippet': f'provider "{provider.lower()}" {{ region = "ap-south-1" }}'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_deployment_files_view(request):
    files = request.data.get('files')
    provider = request.data.get('provider', 'AWS')
    tree = request.data.get('tree')
    if not isinstance(tree, list):
        tree = None

    if str(provider).upper() != 'AWS':
        return Response({
            'success': False,
            'stage': 'PROJECT',
            'status': 'RETIRED',
            'error': (
                f'{provider} deployments are retired. '
                'CloudWise deploys to AWS EC2 only.'
            ),
            'supported': ['AWS'],
        }, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(files, dict) or not files:
        return Response({
            'success': False,
            'error': 'Repository files must be provided as a non-empty object.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        generated = generate_deployment_files(files, provider=provider, tree=tree)
    except (TypeError, ValueError) as exc:
        return Response({
            'success': False,
            'error': str(exc)
        }, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'success': True,
        'data': generated
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def aws_pricing_view(request):
    instance_type = request.query_params.get('instanceType', 'c6i.xlarge')
    region = request.query_params.get('region', 'Asia Pacific (Mumbai)')
    try:
        snapshot = get_aws_price_snapshot(instance_type, region)
    except AwsPricingError as exc:
        return Response({
            'success': False,
            'error': str(exc),
            'source': 'AWS Pricing API',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response({'success': True, 'data': snapshot}, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# AWS account connection (Part 3 — IAM role + temporary credentials)
# -------------------------------------------------------------

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def aws_connect_info_view(request):
    """
    Everything the user needs to create the IAM role in their own AWS
    account: a unique External ID, trust policy, least-privilege
    permissions policy and step-by-step instructions. Contains no secrets.
    """
    connection = ensure_pending_connection(request.user)
    policies = build_policies(connection.external_id)
    return Response({
        'success': True,
        'data': {
            'externalId': policies['externalId'],
            'trustedAccountId': policies['trustedAccountId'],
            'trustPolicy': policies['trustPolicy'],
            'permissionsPolicy': policies['permissionsPolicy'],
            'instructions': policies['instructions'],
            'defaultRegion': connection.region or settings.AWS_DEFAULT_REGION,
            'platformCredentialsConfigured': platform_credentials_configured(),
            'connection': connection_public_dict(connection),
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def aws_connect_view(request):
    """
    Validate and activate the user's AWS connection.

    Validates by assuming the IAM role with SHORT-LIVED STS credentials
    and calling sts:GetCallerIdentity. Stores only the role ARN,
    external id and account id — never AWS access keys.
    """
    role_arn = request.data.get('roleArn', '')
    region = request.data.get('region', '')
    try:
        connection = aws_connect(
            request.user, role_arn, region=region or None
        )
    except AwsConnectionError as exc:
        return Response({
            'success': False,
            'error': str(exc),
        }, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        'success': True,
        'message': (
            f'AWS account {connection.account_id} connected via IAM role. '
            'CloudWise uses temporary credentials only.'
        ),
        'data': connection_public_dict(connection),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def aws_connection_view(request):
    """Return the caller's AWS connection status (no secrets)."""
    connection = AWSConnection.objects.filter(user=request.user).first()
    return Response({
        'success': True,
        'data': connection_public_dict(connection),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def aws_disconnect_view(request):
    """Remove the stored AWS connection (role ARN + external id only)."""
    aws_disconnect(request.user)
    return Response({
        'success': True,
        'message': 'AWS account disconnected. No cloud resources were changed.',
        'data': {'connected': False},
    }, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# Deployment Management Endpoints
#
# Records are addressed by their own id (``dep_...``); the provider
# deployment id (the EC2 instance id) is accepted as a fallback for
# older links. Ownership is enforced on every read and every write: a
# record owned by another user is reported as not found, so its
# existence is never leaked.
# -------------------------------------------------------------

# Deterministic progress derived from the real deployment status.
# There are no timers and no fabricated intermediate percentages.
_STATUS_PROGRESS = {
    DeploymentStatus.QUEUED: 5,
    DeploymentStatus.PREPARING: 15,
    DeploymentStatus.BUILDING: 45,
    DeploymentStatus.DEPLOYING: 70,
    DeploymentStatus.HEALTH_CHECK: 90,
    DeploymentStatus.RUNNING: 100,
    DeploymentStatus.FAILED: 60,
    DeploymentStatus.ROLLING_BACK: 50,
    DeploymentStatus.ROLLED_BACK: 100,
    DeploymentStatus.TERMINATED: 100,
    # legacy lowercase values from records created before migration 0007
    'deployed': 100,
    'deploying': 45,
    'failed': 60,
}

_IN_FLIGHT = (
    DeploymentStatus.QUEUED,
    DeploymentStatus.PREPARING,
    DeploymentStatus.BUILDING,
    DeploymentStatus.DEPLOYING,
    DeploymentStatus.HEALTH_CHECK,
    DeploymentStatus.ROLLING_BACK,
)

_ALIVE = (DeploymentStatus.RUNNING, 'deployed')


def _find_deployment_record(deployment_id, user=None):
    """
    Resolve a deployment by its own id, or by provider deployment id.

    When ``user`` is provided, ownership is enforced: a record owned by
    another user is treated as not found (no existence leak).
    """
    if not deployment_id:
        return None
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        record = DeploymentRecord.objects.filter(
            provider_deployment_id=deployment_id
        ).first()
    if record is None:
        return None
    if user is not None and record.user_id is not None and record.user_id != user.id:
        return None
    return record


def _deployment_payload(record, include_logs=True):
    """Serializer output plus derived progress and the openable live URL."""
    data = DeploymentRecordSerializer(record).data
    data['progress'] = _STATUS_PROGRESS.get(record.deployment_status, 0)
    data['openUrl'] = record.live_url or ''
    if not include_logs:
        data['logCount'] = len(record.logs or [])
        data.pop('logs', None)
    return data


def _stored_status_payload(record, message=None):
    """Status payload for a deployment that is not (yet) queryable in AWS."""
    return {
        'deploymentId': record.pk,
        'deploymentStatus': record.deployment_status,
        'progress': _STATUS_PROGRESS.get(record.deployment_status, 0),
        'providerType': record.provider,
        'repository': record.repository,
        'liveUrl': record.live_url or '',
        'ipAddress': record.ip_address or None,
        'instanceId': record.instance_id or None,
        'instanceState': None,
        'awsAccountId': record.aws_account_id or None,
        'region': record.region,
        'message': message or 'Stored deployment status.',
    }


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def deployments_list_view(request):
    """List the calling user's own deployments (newest first)."""
    records = DeploymentRecord.objects.filter(
        user=request.user
    ).order_by('-created_at')

    raw_limit = request.query_params.get('limit')
    try:
        limit = max(1, min(int(raw_limit), 100)) if raw_limit else 20
    except (TypeError, ValueError):
        limit = 20

    items = [
        _deployment_payload(record, include_logs=False)
        for record in records[:limit]
    ]
    total = records.count()
    return Response({
        'success': True,
        'count': len(items),
        'total': total,
        'data': items,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def deployment_detail_view(request, deployment_id):
    """
    Full details for one deployment: repository, commit, project type,
    AWS account/region, instance, status, logs, live URL and timestamps.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'success': True,
        'data': _deployment_payload(record, include_logs=True),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def deployment_status_view(request, deployment_id):
    """
    Real deployment status.

    While the background pipeline is running, the record's own status is
    reported (it is the source of truth — there is no instance to query
    yet, or the application is still being deployed). Once the
    deployment is live, the EC2 instance state is queried in the user's
    AWS account via the user's own assumed role.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    provider = (record.provider or '').upper()

    if record.deployment_status in _IN_FLIGHT:
        payload = _stored_status_payload(
            record,
            message=(
                f'Deployment pipeline is running '
                f'({record.deployment_status}). Follow the logs for live '
                'progress.'
            ),
        )
        payload['pipelineInFlight'] = True
        return Response({'success': True, 'data': payload}, status=status.HTTP_200_OK)

    if provider != 'AWS':
        return Response({
            'success': True,
            'data': _stored_status_payload(
                record,
                message=f'Returning stored status for provider {provider}.',
            ),
        }, status=status.HTTP_200_OK)

    if not record.instance_id:
        return Response({
            'success': True,
            'data': _stored_status_payload(
                record,
                message='No EC2 instance recorded for this deployment.',
            ),
        }, status=status.HTTP_200_OK)

    if record.deployment_status == DeploymentStatus.FAILED:
        return Response({
            'success': True,
            'data': _stored_status_payload(
                record,
                message='Deployment failed. Retry it or inspect the logs.',
            ),
        }, status=status.HTTP_200_OK)

    aws_connection = AWSConnection.objects.filter(
        user_id=record.user_id, status='active'
    ).first()
    if aws_connection is None:
        return Response({
            'success': True,
            'data': _stored_status_payload(
                record,
                message=(
                    'AWS account connection not found; returning stored '
                    'status.'
                ),
            ),
        }, status=status.HTTP_200_OK)

    try:
        aws_provider = AwsEc2Provider(user=record.user, connection=aws_connection)
        live = aws_provider.get_status(record.instance_id)
    except AwsEc2Error as exc:
        return Response({
            'success': True,
            'data': _stored_status_payload(
                record,
                message=f'AWS EC2 error: {exc}',
            ),
        }, status=status.HTTP_200_OK)

    instance_state = str(live.get('instance_state') or '')
    public_ip = live.get('ip_address') or record.ip_address
    deployment_status = record.deployment_status

    if instance_state in ('terminated', 'shutting-down'):
        deployment_status = DeploymentStatus.TERMINATED
    elif instance_state not in ('running', 'pending', 'stopped'):
        deployment_status = DeploymentStatus.FAILED
    elif record.deployment_status in _ALIVE and instance_state == 'running':
        deployment_status = DeploymentStatus.RUNNING

    update_fields = []
    if deployment_status != record.deployment_status:
        record.deployment_status = deployment_status
        update_fields.append('deployment_status')
    if public_ip and public_ip != record.ip_address:
        record.ip_address = public_ip
        update_fields.append('ip_address')
    if update_fields:
        DeploymentRecord.objects.filter(pk=record.pk).update(
            **{f: getattr(record, f) for f in update_fields},
            updated_at=timezone.now(),
        )

    return Response({
        'success': True,
        'data': {
            'deploymentId': record.pk,
            'deploymentStatus': deployment_status,
            'progress': _STATUS_PROGRESS.get(deployment_status, 0),
            'providerType': record.provider,
            'repository': record.repository,
            'liveUrl': record.live_url or '',
            'ipAddress': public_ip or None,
            'instanceId': record.instance_id or None,
            'instanceState': instance_state or None,
            'awsAccountId': record.aws_account_id or None,
            'region': live.get('region') or record.region,
            'message': live.get('message', ''),
        },
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def deployment_logs_view(request, deployment_id):
    """Structured logs for a deployment. Ownership enforced."""
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'success': True,
        'data': list(record.logs or []),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deployment_health_view(request, deployment_id):
    """
    Real HTTP health check against the stored live URL.

    Makes an actual GET request and returns the actual HTTP status and
    latency. Ownership enforced.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    endpoint_url = record.live_url
    if not endpoint_url:
        return Response({
            'success': True,
            'data': {
                'deploymentId': record.pk,
                'healthy': False,
                'providerType': record.provider,
                'message': 'No live URL stored for this deployment yet.',
                'detail': {'httpStatus': None, 'latencyMs': None},
            }
        }, status=status.HTTP_200_OK)

    import time as _time
    start_time = _time.monotonic()
    try:
        hc_req = urllib.request.Request(endpoint_url, method='GET')
        hc_req.add_header('User-Agent', 'CloudWise-HealthCheck/1.0')
        with urllib.request.urlopen(hc_req, timeout=15) as hc_resp:
            elapsed_ms = round((_time.monotonic() - start_time) * 1000)
            http_status = hc_resp.status
            healthy = http_status < 500
            return Response({
                'success': True,
                'data': {
                    'deploymentId': record.pk,
                    'healthy': healthy,
                    'providerType': record.provider,
                    'message': f'HTTP {http_status} from {endpoint_url}',
                    'detail': {
                        'httpStatus': http_status,
                        'latencyMs': elapsed_ms,
                        'url': endpoint_url,
                    },
                }
            }, status=status.HTTP_200_OK)
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((_time.monotonic() - start_time) * 1000)
        return Response({
            'success': True,
            'data': {
                'deploymentId': record.pk,
                'healthy': False,
                'providerType': record.provider,
                'message': f'HTTP {exc.code} from {endpoint_url}',
                'detail': {
                    'httpStatus': exc.code,
                    'latencyMs': elapsed_ms,
                    'url': endpoint_url,
                    'error': str(exc),
                },
            }
        }, status=status.HTTP_200_OK)
    except Exception as exc:
        elapsed_ms = round((_time.monotonic() - start_time) * 1000)
        return Response({
            'success': True,
            'data': {
                'deploymentId': record.pk,
                'healthy': False,
                'providerType': record.provider,
                'message': f'Health check failed for {endpoint_url}: {exc}',
                'detail': {
                    'httpStatus': None,
                    'latencyMs': elapsed_ms,
                    'url': endpoint_url,
                    'error': str(exc),
                },
            }
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deployment_retry_view(request, deployment_id):
    """
    Re-run a failed deployment from scratch.

    Re-inspects the repository, regenerates the deployment files,
    re-validates the environment variables and restarts the pipeline on
    the same record. Environment variables must be supplied again in the
    request body — CloudWise never stores secret values.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    if record.deployment_status not in (
        DeploymentStatus.FAILED,
        DeploymentStatus.ROLLED_BACK,
        'failed',
    ):
        return Response({
            'success': False,
            'stage': 'PROJECT',
            'error': (
                f'Only a failed deployment can be retried '
                f'(current status: {record.deployment_status}).'
            ),
            'currentStatus': record.deployment_status,
        }, status=status.HTTP_409_CONFLICT)

    data = request.data or {}
    retry_data = {
        'environmentName': record.environment_name,
        'region': record.region,
        'instanceType': record.instance_type,
        'monthlyCost': float(record.monthly_cost or 0),
        'specs': dict(record.specs or {}),
    }
    retry_data.update({k: v for k, v in data.items() if v is not None})

    payload, project, error = _prepare_repository_payload(
        record.user,
        str(record.project_id or ''),
        retry_data,
        data.get('envVars') or {},
    )
    if error is not None:
        return error

    aws_connection = payload.pop('aws_connection')
    github_connection = payload.pop('github_connection')
    commit_sha = payload['commit_sha']
    commit_suffix = f' @ {commit_sha[:7]}' if commit_sha else ''

    logs = list(record.logs or [])
    logs.append({
        'timestamp': timezone.now().isoformat(),
        'level': 'INFO',
        'stage': DeploymentStage.PREPARING,
        'message': (
            f'Retry requested for {payload["repository"]}{commit_suffix} '
            f'after status {record.deployment_status}. Restarting the '
            'pipeline.'
        ),
    })

    record.project = project
    record.github_connection = github_connection
    record.aws_connection = aws_connection
    record.environment_name = payload['environment_name']
    record.repository = payload['repository']
    record.commit_sha = commit_sha
    record.project_type = payload['project_type']
    record.aws_account_id = aws_connection.account_id or ''
    record.region = payload['region']
    record.instance_type = payload['instance_type']
    record.monthly_cost = payload['monthly_cost']
    record.specs = payload['specs']
    record.deployment_status = DeploymentStatus.QUEUED
    record.live_url = None
    record.logs = logs
    record.save()

    start_pipeline(record.id, payload)
    record.refresh_from_db()
    return Response({
        'success': True,
        'stage': 'QUEUED',
        'message': f'Deployment {record.id} restarted for {record.repository}.',
        'deployment_id': record.id,
        'data': _deployment_payload(record),
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deployment_terminate_view(request, deployment_id):
    """
    Terminate the EC2 instance backing this deployment — always inside
    the owning user's own AWS account, and only for instances tagged
    ``ManagedBy=CloudWise``.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    if not record.instance_id:
        return Response({
            'success': False,
            'stage': 'AWS',
            'error': 'No EC2 instance recorded for this deployment.',
        }, status=status.HTTP_400_BAD_REQUEST)

    if record.deployment_status == DeploymentStatus.TERMINATED:
        return Response({
            'success': False,
            'stage': 'AWS',
            'error': f'Instance {record.instance_id} is already terminated.',
            'currentStatus': record.deployment_status,
        }, status=status.HTTP_409_CONFLICT)

    aws_connection = AWSConnection.objects.filter(
        user_id=record.user_id, status='active'
    ).first()
    if aws_connection is None:
        return Response({
            'success': False,
            'stage': 'AWS',
            'error': 'AWS account connection not found.',
            'connectUrl': '/connect-aws',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        aws_provider = AwsEc2Provider(user=record.user, connection=aws_connection)
        result = aws_provider.terminate_instance(record.instance_id)
    except AwsEc2Error as exc:
        return Response({
            'success': False,
            'stage': 'AWS',
            'error': f'Terminate failed: {exc}',
        }, status=status.HTTP_502_BAD_GATEWAY)

    logs = list(record.logs or []) + list(result.get('logs') or [])
    record.deployment_status = DeploymentStatus.TERMINATED
    record.logs = logs
    record.save(update_fields=['deployment_status', 'logs', 'updated_at'])

    return Response({
        'success': True,
        'data': {
            'deploymentId': record.pk,
            'deploymentStatus': record.deployment_status,
            'instanceId': record.instance_id,
            'region': result.get('region') or record.region,
            'message': result.get('message', ''),
            'logs': logs,
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deployment_rollback_view(request, deployment_id):
    """
    Roll back the last deployment: stop the application containers on
    the instance (the instance itself is retained).

    AWS EC2 is the only supported target. Ownership enforced.
    """
    record = _find_deployment_record(deployment_id, user=request.user)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    provider = (record.provider or '').upper()
    if provider != 'AWS':
        return Response({
            'success': False,
            'error': f'Rollback not supported for provider "{provider}".',
            'supported': ['AWS'],
        }, status=status.HTTP_400_BAD_REQUEST)

    aws_connection = AWSConnection.objects.filter(
        user_id=record.user_id, status='active'
    ).first()
    if aws_connection is None:
        return Response({
            'success': False,
            'error': 'AWS account connection not found. Cannot trigger rollback.',
            'connectUrl': '/connect-aws',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not record.instance_id:
        return Response({
            'success': False,
            'error': 'No EC2 instance recorded for this deployment.',
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        aws_provider = AwsEc2Provider(user=record.user, connection=aws_connection)
        result = aws_provider.rollback(record.instance_id)
    except AwsEc2Error as exc:
        return Response({
            'success': False,
            'error': f'AWS rollback failed: {exc}',
        }, status=status.HTTP_502_BAD_GATEWAY)

    record.deployment_status = result['status']
    record.logs = (record.logs or []) + list(result.get('logs') or [])
    record.save(update_fields=['deployment_status', 'logs', 'updated_at'])
    return Response({
        'success': True,
        'data': {
            'deploymentId': record.pk,
            'deploymentStatus': record.deployment_status,
            'instanceId': record.instance_id,
            'message': result['message'],
            'logs': record.logs,
        },
    }, status=status.HTTP_200_OK)
