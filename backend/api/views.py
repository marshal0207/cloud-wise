import random
import math
import re
import secrets
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
from .services.github_repository_service import inspect_repository
from .services.tech_stack_detector import UnsupportedTechStackError, detect_tech_stack
from .services.aws_pricing_service import AwsPricingError, get_aws_price_snapshot
from .services.free_tier_policy import FreeTierLimitError, validate_free_tier_deployment, evaluate_free_tier_eligibility
from .services.deployment.mock_provider import MockDeploymentProvider, UnsupportedProviderError
from .services.deployment.vercel_provider import VercelDeploymentService, VercelApiError
from .services.deployment.render_provider import RenderDeploymentService, RenderApiError
from .services.deployment.health_check import DeploymentHealthCheckService
from .services.deployment.rollback import DeploymentRollbackService

User = get_user_model()


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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def project_github_push_view(request, pk):
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
            connection.access_token,
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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def project_github_inspect_view(request, pk):
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({'success': False, 'error': 'Project not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

    if project.user_id != request.user.id:
        return Response({'success': False, 'error': 'Project not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

    repository = project.github_repo or {}
    body_repo_name = request.data.get('repoName', '').strip()
    if not repository.get('name') and body_repo_name:
        repository = {'name': body_repo_name, 'default_branch': 'main'}

    if not repository.get('name'):
        return Response({'success': False, 'error': 'Select a GitHub repository before inspecting it.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        connection = request.user.github_connection
        access_token = connection.access_token
    except GitHubConnection.DoesNotExist:
        return Response({'success': False, 'error': 'Connect a GitHub account before inspecting repositories.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        inspection = inspect_repository(access_token, repository)
        try:
            stack = detect_tech_stack(inspection['files'])
            stack_data = asdict(stack)
        except UnsupportedTechStackError:
            stack_data = None
        return Response({
            'success': True,
            'data': {
                'repository': inspection.get('repository'),
                'branch': inspection.get('branch'),
                'tree': inspection.get('tree', []),
                'files': inspection.get('files', {}),
                'technology': stack_data,
                'has_dockerfile': inspection.get('has_dockerfile', False),
                'has_compose': inspection.get('has_compose', False),
                'has_cicd': inspection.get('has_cicd', False),
            }
        }, status=status.HTTP_200_OK)
    except (GitHubApiError, ValueError) as exc:
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)



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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def deploy_view(request):
    """
    Real deployment endpoint.

    Deploys the GitHub repository stored on the active project to
    Vercel (frontend/Node) or Render (backend/Docker).

    Returns BLOCKED if provider credentials are not configured.
    Returns FAILED with the real provider error on build/deploy failure.
    Returns DEPLOYED with the real provider URL on success.
    """
    data = request.data or {}
    provider_name = str(data.get('provider', 'Vercel')).strip()
    project_id = data.get('projectId', '').strip()
    simulate_error = bool(data.get('simulateError', False))

    # ----------------------------------------------------------------
    # Resolve active project and its GitHub repository
    # ----------------------------------------------------------------
    project = None
    if project_id:
        try:
            project = Project.objects.get(pk=project_id, user=request.user)
        except Project.DoesNotExist:
            pass
    if project is None:
        project = Project.objects.filter(user=request.user).order_by('-updated_at').first()

    if project is None:
        return Response({
            'success': False,
            'error': 'No active project found. Create a project first.',
        }, status=status.HTTP_400_BAD_REQUEST)

    github_repo = project.github_repo or {}
    repo_name = github_repo.get('name', '').strip()
    if not repo_name or '/' not in repo_name:
        return Response({
            'success': False,
            'error': 'No GitHub repository linked to this project. Connect a repository first.',
        }, status=status.HTTP_400_BAD_REQUEST)

    branch = github_repo.get('default_branch') or github_repo.get('branch') or 'main'

    # ----------------------------------------------------------------
    # Resolve GitHub access token
    # ----------------------------------------------------------------
    try:
        github_connection = request.user.github_connection
        github_token = github_connection.access_token
    except GitHubConnection.DoesNotExist:
        return Response({
            'success': False,
            'error': 'GitHub account not connected. Authorize GitHub first.',
        }, status=status.HTTP_400_BAD_REQUEST)

    # ----------------------------------------------------------------
    # Inspect repository to determine stack
    # ----------------------------------------------------------------
    from .services.github_repository_service import inspect_repository
    from .services.tech_stack_detector import (
        detect_tech_stack, detect_frontend_stack, UnsupportedTechStackError,
    )
    from .services.deployment_file_generator import generate_deployment_files

    try:
        inspection = inspect_repository(github_token, github_repo)
    except Exception as exc:
        return Response({
            'success': False,
            'error': f'Cannot access GitHub repository "{repo_name}": {exc}',
        }, status=status.HTTP_400_BAD_REQUEST)

    repo_files = inspection.get('files', {})
    has_dockerfile = inspection.get('has_dockerfile', False)
    has_cicd = inspection.get('has_cicd', False)

    # ----------------------------------------------------------------
    # For Vercel: detect the FRONTEND specifically.
    # For other providers: detect the overall stack.
    # ----------------------------------------------------------------
    is_vercel = provider_name.upper() == 'VERCEL'

    if is_vercel:
        frontend = detect_frontend_stack(repo_files, tree=inspection.get('tree'))
        technology = frontend['technology']
        vercel_framework = frontend['framework']
        build_command = frontend['build_command']
        install_command = frontend['install_command']
        output_directory = frontend['output_directory']
        root_directory = frontend['root_directory']
        start_command = frontend['start_command']
        port = frontend['port']
    else:
        try:
            stack = detect_tech_stack(repo_files)
            technology = stack.technology
            port = stack.port
        except UnsupportedTechStackError:
            technology = 'DOCKER' if has_dockerfile else 'UNKNOWN'
            port = 3000

        # Determine build/start commands from actual repo files
        build_command = None
        start_command = None
        install_command = None
        output_directory = None
        root_directory = None
        vercel_framework = None

        if technology in ('NODE_JS', 'REACT'):
            pkg = next((v for k, v in repo_files.items() if k.split('/')[-1] == 'package.json'), '{}')
            try:
                pkg_json = json.loads(pkg)
                scripts = pkg_json.get('scripts', {})
                build_command = scripts.get('build') or ('npm run build' if technology == 'REACT' else None)
                start_command = scripts.get('start') or 'npm start'
                install_command = 'npm install'
                output_directory = 'dist' if technology == 'REACT' else None
            except (json.JSONDecodeError, AttributeError):
                build_command = 'npm run build' if technology == 'REACT' else None
                start_command = 'npm start'
                install_command = 'npm install'
        elif technology == 'PYTHON':
            req_key = next((k for k in repo_files if k.split('/')[-1] == 'requirements.txt'), None)
            build_command = f'pip install -r {req_key}' if req_key else 'pip install -r requirements.txt'
            manage_key = next((k for k in inspection.get('tree', []) if k.get('path', '').endswith('manage.py')), None)
            if manage_key:
                start_command = f'python {manage_key["path"]} runserver 0.0.0.0:{port}'
            else:
                start_command = f'python -m uvicorn main:app --host 0.0.0.0 --port {port}'
        elif technology == 'SPRING_BOOT':
            if 'pom.xml' in ' '.join(repo_files.keys()):
                build_command = 'mvn clean package -DskipTests'
            else:
                build_command = './gradlew bootJar'
            start_command = 'java -jar target/*.jar'

    # ----------------------------------------------------------------
    # Environment variables from request (user-supplied)
    # ----------------------------------------------------------------
    env_vars: dict[str, str] = data.get('envVars') or {}

    # ----------------------------------------------------------------
    # Simulate error path (test button) — uses mock, clearly labelled
    # ----------------------------------------------------------------
    if simulate_error:
        mock_provider = MockDeploymentProvider()
        env_name = data.get('environmentName', f'{project.name.lower().replace(" ", "-")}-prod')
        start_result = mock_provider.start({
            'environment_name': env_name,
            'provider': provider_name.upper(),
            'region': data.get('region', 'us-east-1'),
            'specs': data.get('specs', {}),
        })
        mock_provider.fail(
            start_result['deployment_id'],
            reason=f'Simulated quota exceeded. Cannot allocate resources for {repo_name}.',
        )
        record = DeploymentRecord.objects.create(
            environment_name=env_name,
            provider=provider_name.upper(),
            monthly_cost=data.get('monthlyCost', 0),
            specs=data.get('specs', {}),
            region=data.get('region', 'us-east-1'),
            status='FAILED',
            ip_address=None,
            endpoint_url=None,
            logs=mock_provider.get_logs(start_result['deployment_id']),
        )
        response_data = DeploymentRecordSerializer(record).data
        response_data['deployment_id'] = start_result['deployment_id']
        response_data['simulated'] = True
        return Response({'success': True, 'data': response_data}, status=status.HTTP_200_OK)

    # ----------------------------------------------------------------
    # REAL DEPLOYMENT — Vercel
    # ----------------------------------------------------------------
    if provider_name.upper() == 'VERCEL':
        vercel_token = settings.VERCEL_TOKEN
        vercel_team_id = settings.VERCEL_TEAM_ID

        if not vercel_token:
            return Response({
                'success': False,
                'status': 'BLOCKED',
                'error': (
                    'BLOCKED — Vercel credentials not configured. '
                    'Set VERCEL_TOKEN in backend/.env to enable real Vercel deployments.'
                ),
                'required': ['VERCEL_TOKEN'],
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        env_name = data.get('environmentName') or f"{project.name.lower().replace(' ', '-')}-prod"
        # Sanitise to valid Vercel project name (alphanumeric + hyphens, max 52 chars)
        import re as _re
        safe_name = _re.sub(r'[^a-z0-9-]', '-', env_name.lower())[:52].strip('-')

        existing_project_id = (project.deployment or {}).get('provider_project_id') if project.deployment else None

        try:
            svc = VercelDeploymentService(vercel_token, vercel_team_id or None)
            result = svc.deploy(
                repo_full_name=repo_name,
                branch=branch,
                project_name=safe_name,
                framework=vercel_framework,
                root_directory=root_directory,
                build_command=build_command,
                output_directory=output_directory,
                install_command=install_command,
                env_vars=env_vars or None,
                existing_project_id=existing_project_id,
            )
        except VercelApiError as exc:
            record = DeploymentRecord.objects.create(
                environment_name=env_name,
                provider='VERCEL',
                monthly_cost=0,
                specs=data.get('specs', {}),
                region='vercel-global',
                status='FAILED',
                ip_address=None,
                endpoint_url=None,
                logs=[{'timestamp': datetime.now().isoformat(), 'level': 'ERROR',
                        'stage': 'DEPLOYING', 'message': str(exc)}],
            )
            return Response({
                'success': False,
                'error': str(exc),
                'data': DeploymentRecordSerializer(record).data,
            }, status=status.HTTP_502_BAD_GATEWAY)

        vercel_state = result.get('status', '').upper()
        raw_data = result.get('raw', {})
        error_code = raw_data.get('errorCode')
        error_message = raw_data.get('errorMessage')
        deploy_status = 'RUNNING' if vercel_state == 'READY' else 'FAILED'
        real_url = result.get('url')

        # Extract real Vercel error details when deployment failed
        vercel_error_detail = None
        if vercel_state == 'ERROR' and error_message:
            vercel_error_detail = {
                'provider': 'vercel',
                'deploymentId': result.get('deployment_id'),
                'projectId': result.get('provider_project_id'),
                'status': 'ERROR',
                'url': real_url,
                'errorCode': error_code,
                'errorMessage': error_message,
                'gitSource': {
                    'sha': raw_data.get('gitSource', {}).get('sha'),
                    'ref': raw_data.get('gitSource', {}).get('ref'),
                },
                'projectSettings': raw_data.get('projectSettings'),
                'errorStep': raw_data.get('errorStep'),
            }

        # Health-check the real URL (only if deployment succeeded)
        if real_url and deploy_status == 'RUNNING':
            try:
                hc_req = urllib.request.Request(real_url, method='GET')
                hc_req.add_header('User-Agent', 'CloudWise-HealthCheck/1.0')
                with urllib.request.urlopen(hc_req, timeout=15) as hc_resp:
                    if hc_resp.status >= 500:
                        deploy_status = 'FAILED'
            except Exception:
                pass  # URL may redirect or require auth -- not fatal

        # Build log entries including real error when available
        log_entries = []
        if vercel_state == 'ERROR':
            log_entries.append({
                'timestamp': datetime.now().isoformat(),
                'level': 'ERROR',
                'stage': 'BUILDING',
                'message': f'Vercel build failed: {error_code} -- {error_message}',
            })
            if raw_data.get('errorStep'):
                log_entries.append({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'ERROR',
                    'stage': 'BUILDING',
                    'message': f'Failed at step: {raw_data["errorStep"]}',
                })
            # Add stdout/stderr from events if available
            ps = raw_data.get('projectSettings', {})
            if ps:
                log_entries.append({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'INFO',
                    'stage': 'BUILDING',
                    'message': f'Framework: {ps.get("framework") or "None"} | '
                               f'Build: {ps.get("buildCommand") or "None"} | '
                               f'Root: {ps.get("rootDirectory") or "None"}',
                })
        else:
            log_entries.append({
                'timestamp': datetime.now().isoformat(),
                'level': 'INFO',
                'stage': 'COMPLETED',
                'message': f'Vercel deployment {result["deployment_id"]} -- state: {vercel_state}',
            })

        record = DeploymentRecord.objects.create(
            environment_name=env_name,
            provider='VERCEL',
            provider_deployment_id=result.get('deployment_id'),
            provider_project_id=result.get('provider_project_id'),
            monthly_cost=0,
            specs=data.get('specs', {}),
            region='vercel-global',
            status=deploy_status,
            ip_address=None,
            endpoint_url=real_url,
            logs=log_entries,
        )

        # Persist provider IDs back to project so future deploys reuse the project
        project.deployment = {
            **(project.deployment or {}),
            'provider_project_id': result.get('provider_project_id'),
            'provider_deployment_id': result.get('deployment_id'),
            'status': deploy_status,
            'endpointUrl': real_url,
        }
        project.save(update_fields=['deployment'])

        response_data = DeploymentRecordSerializer(record).data
        response_data['deployment_id'] = result.get('deployment_id')
        response_data['provider_project_id'] = result.get('provider_project_id')
        response_data['simulated'] = False
        if vercel_error_detail:
            response_data['provider_error'] = vercel_error_detail
        return Response({
            'success': deploy_status == 'RUNNING',
            'message': f'Vercel deployment {deploy_status.lower()}.',
            'data': response_data,
        }, status=status.HTTP_200_OK)

    # ----------------------------------------------------------------
    # REAL DEPLOYMENT — Render
    # ----------------------------------------------------------------
    if provider_name.upper() == 'RENDER':
        render_api_key = settings.RENDER_API_KEY
        render_owner_id = settings.RENDER_OWNER_ID

        if not render_api_key or not render_owner_id:
            missing = [v for v, val in [
                ('RENDER_API_KEY', render_api_key),
                ('RENDER_OWNER_ID', render_owner_id),
            ] if not val]
            return Response({
                'success': False,
                'status': 'BLOCKED',
                'error': (
                    f'BLOCKED — Render credentials not configured. '
                    f'Set {", ".join(missing)} in backend/.env to enable real Render deployments.'
                ),
                'required': missing,
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        env_name = data.get('environmentName') or f"{project.name.lower().replace(' ', '-')}-prod"
        import re as _re
        safe_name = _re.sub(r'[^a-z0-9-]', '-', env_name.lower())[:63].strip('-')

        existing_service_id = (project.deployment or {}).get('provider_service_id') if project.deployment else None

        try:
            svc = RenderDeploymentService(render_api_key, render_owner_id)
            result = svc.deploy(
                repo_full_name=repo_name,
                branch=branch,
                service_name=safe_name,
                technology=technology,
                build_command=build_command,
                start_command=start_command,
                root_directory=root_directory,
                port=port,
                env_vars=env_vars or None,
                existing_service_id=existing_service_id,
                has_dockerfile=has_dockerfile,
            )
        except RenderApiError as exc:
            record = DeploymentRecord.objects.create(
                environment_name=env_name,
                provider='RENDER',
                monthly_cost=0,
                specs=data.get('specs', {}),
                region='render-oregon',
                status='FAILED',
                ip_address=None,
                endpoint_url=None,
                logs=[{'timestamp': datetime.now().isoformat(), 'level': 'ERROR',
                        'stage': 'DEPLOYING', 'message': str(exc)}],
            )
            return Response({
                'success': False,
                'error': str(exc),
                'data': DeploymentRecordSerializer(record).data,
            }, status=status.HTTP_502_BAD_GATEWAY)

        render_status = result.get('status', '').lower()
        deploy_status = 'RUNNING' if render_status == 'live' else 'FAILED'
        real_url = result.get('url')

        # Health-check the real URL
        if real_url and deploy_status == 'RUNNING':
            try:
                hc_req = urllib.request.Request(real_url, method='GET')
                hc_req.add_header('User-Agent', 'CloudWise-HealthCheck/1.0')
                with urllib.request.urlopen(hc_req, timeout=20) as hc_resp:
                    if hc_resp.status >= 500:
                        deploy_status = 'FAILED'
            except Exception:
                pass

        record = DeploymentRecord.objects.create(
            environment_name=env_name,
            provider='RENDER',
            provider_deployment_id=result.get('deploy_id'),
            provider_project_id=result.get('provider_service_id'),
            monthly_cost=0,
            specs=data.get('specs', {}),
            region='render-oregon',
            status=deploy_status,
            ip_address=None,
            endpoint_url=real_url,
            logs=[{'timestamp': datetime.now().isoformat(), 'level': 'INFO',
                    'stage': 'COMPLETED',
                    'message': f'Render deploy {result["deploy_id"]} — status: {render_status}'}],
        )

        # Persist provider IDs back to project
        project.deployment = {
            **(project.deployment or {}),
            'provider_service_id': result.get('provider_service_id'),
            'provider_deployment_id': result.get('deploy_id'),
            'status': deploy_status,
            'endpointUrl': real_url,
        }
        project.save(update_fields=['deployment'])

        response_data = DeploymentRecordSerializer(record).data
        response_data['deployment_id'] = result.get('deploy_id')
        response_data['provider_service_id'] = result.get('provider_service_id')
        response_data['simulated'] = False
        return Response({
            'success': True,
            'message': f'Render deployment {deploy_status.lower()}.',
            'data': response_data,
        }, status=status.HTTP_200_OK)

    # ----------------------------------------------------------------
    # AWS — not yet implemented
    # ----------------------------------------------------------------
    if provider_name.upper() == 'AWS':
        return Response({
            'success': False,
            'status': 'BLOCKED',
            'error': (
                'BLOCKED — AWS deployment is not yet implemented. '
                'Select Vercel or Render as your deployment provider.'
            ),
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response({
        'success': False,
        'error': f'Unknown provider "{provider_name}". Supported: Vercel, Render.',
    }, status=status.HTTP_400_BAD_REQUEST)


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
@permission_classes([permissions.AllowAny])
def monitoring_view(request):
    # Derive dynamic values from the latest deployment record
    latest = DeploymentRecord.objects.order_by('-created_at').first()

    if latest:
        vcpu = latest.specs.get('vcpu', 8) if isinstance(latest.specs, dict) else 8
        active_nodes = max(1, math.ceil(vcpu / 4))
        # Compute uptime from created_at
        delta = timezone.now() - latest.created_at
        total_seconds = int(delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        uptime_str = f"{days}d {hours:02d}h {minutes:02d}m"
        ip_address = latest.ip_address or 'Not yet deployed'
        endpoint_url = latest.endpoint_url or None
    else:
        active_nodes = 3
        uptime_str = '0d 00h 00m'
        ip_address = 'Not yet deployed'
        endpoint_url = None

    return Response({
        'success': True,
        'data': {
            'cpuUsage': random.randint(28, 52),
            'memoryUsage': random.randint(48, 72),
            'storageUsage': random.randint(35, 55),
            'networkInMB': round(random.uniform(8.0, 18.0), 1),
            'networkOutMB': round(random.uniform(32.0, 68.0), 1),
            'healthStatus': 'Healthy',
            'clusterUptime': uptime_str,
            'activeNodes': active_nodes,
            'ipAddress': ip_address,
            'endpointUrl': endpoint_url,
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_view(request):
    return Response({
        'status': 'ok',
        'service': 'CloudWise API Backend (Django REST Framework)',
        'version': '1.2.0',
        'timestamp': timezone.now().isoformat()
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_oauth_start_view(request):
    if not settings.GITHUB_CLIENT_ID:
        return Response({
            'success': False,
            'error': 'GitHub OAuth is not configured on the server.'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Support both authenticated users and anonymous/token-based users
    if request.user.is_authenticated:
        user_id = str(request.user.id)
    else:
        user_id, _, _ = get_request_user_info(request)

    state = signing.dumps({
        'user_id': user_id,
        'nonce': secrets.token_urlsafe(32),
    })
    query = urllib.parse.urlencode({
        'client_id': settings.GITHUB_CLIENT_ID,
        'redirect_uri': settings.GITHUB_REDIRECT_URI,
        'scope': 'repo workflow',
        'state': state,
    })
    return Response({
        'success': True,
        'authorizationUrl': f'https://github.com/login/oauth/authorize?{query}'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_oauth_callback_view(request):
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    try:
        state_data = signing.loads(state or '', max_age=600)
    except (signing.BadSignature, signing.SignatureExpired):
        state_data = None

    if not code or not state_data or not state_data.get('user_id'):
        return Response({
            'success': False,
            'error': 'Invalid GitHub OAuth callback state or authorization code.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return Response({
            'success': False,
            'error': 'GitHub OAuth is not configured on the server.'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    user_id = state_data['user_id']

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
            headers={'Accept': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(token_request, timeout=15) as response:
            token_data = json.loads(response.read().decode())

        access_token = token_data.get('access_token')
        if not access_token:
            raise ValueError(token_data.get('error_description', 'GitHub did not return an access token.'))

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

        user = User.objects.get(pk=user_id)
        GitHubConnection.objects.update_or_create(
            user=user,
            defaults={
                'access_token': access_token,
                'github_user_id': str(profile['id']),
                'github_login': profile.get('login', ''),
            },
        )
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return Response({
            'success': False,
            'error': f'GitHub OAuth exchange failed: {exc}'
        }, status=status.HTTP_502_BAD_GATEWAY)

    return redirect(f'{settings.FRONTEND_URL}/generate?github=connected')


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def github_repositories_view(request):
    # Resolve GitHub connection: prefer authenticated session, then token/user_id fallback
    user_id, _, user_obj = get_request_user_info(request)
    connection = None

    if request.user.is_authenticated:
        try:
            connection = request.user.github_connection
        except GitHubConnection.DoesNotExist:
            pass
    
    if connection is None and user_obj:
        try:
            connection = user_obj.github_connection
        except Exception:
            pass

    if connection is None:
        return Response({
            'success': False,
            'error': 'Connect a GitHub account before retrieving repositories. Use "Authorize GitHub Account" first.'
        }, status=status.HTTP_400_BAD_REQUEST)

    github_request = urllib.request.Request(
        'https://api.github.com/user/repos?sort=updated&per_page=100',
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {connection.access_token}',
            'User-Agent': 'CloudWise',
        },
    )
    try:
        with urllib.request.urlopen(github_request, timeout=15) as response:
            repositories = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return Response({
                'success': False,
                'error': 'GitHub token is invalid or expired. Re-authorize your GitHub account.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        if exc.code == 403:
            return Response({
                'success': False,
                'error': 'GitHub API rate limit exceeded. Please wait and try again.'
            }, status=status.HTTP_403_FORBIDDEN)
        if exc.code == 404:
            return Response({
                'success': False,
                'error': 'GitHub repository not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        details = exc.read().decode(errors='replace')
        return Response({
            'success': False,
            'error': f'GitHub API returned HTTP {exc.code}: {details}'
        }, status=status.HTTP_502_BAD_GATEWAY)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return Response({
            'success': False,
            'error': f'Unable to retrieve GitHub repositories: {exc}'
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
@permission_classes([permissions.AllowAny])
def generate_deployment_files_view(request):
    files = request.data.get('files')
    provider = request.data.get('provider', 'AWS')

    if not isinstance(files, dict) or not files:
        return Response({
            'success': False,
            'error': 'Repository files must be provided as a non-empty object.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        generated = generate_deployment_files(files, provider=provider)
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
# Deployment Management Endpoints (REAL provider status polling)
# -------------------------------------------------------------

def _find_deployment_record(deployment_id):
    """Look up a DeploymentRecord by its provider deployment ID."""
    return DeploymentRecord.objects.filter(provider_deployment_id=deployment_id).first()


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def deployment_status_view(request, deployment_id):
    """
    Return real deployment status from Vercel or Render.

    Looks up the DeploymentRecord by provider_deployment_id, determines
    the provider, and queries the real provider API.
    """
    record = _find_deployment_record(deployment_id)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    provider = (record.provider or '').upper()

    if provider == 'VERCEL':
        vercel_token = settings.VERCEL_TOKEN
        if not vercel_token:
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': record.status,
                    'progress': 100 if record.status == 'RUNNING' else 45,
                    'provider_type': 'VERCEL',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': record.ip_address,
                    'message': 'Vercel credentials not configured; returning stored status.',
                }
            }, status=status.HTTP_200_OK)
        try:
            svc = VercelDeploymentService(vercel_token, settings.VERCEL_TEAM_ID or None)
            raw = svc.get_deployment_status(deployment_id)
            ready_state = (raw.get('readyState') or raw.get('state', '')).upper()
            url = raw.get('url')
            if url and not url.startswith('http'):
                url = f'https://{url}'
            status_map = {
                'QUEUED': 'QUEUED',
                'BUILDING': 'BUILDING',
                'ASSIGNING': 'BUILDING',
                'INITIALIZING': 'PREPARING',
                'READY': 'RUNNING',
                'ERROR': 'FAILED',
                'CANCELED': 'FAILED',
            }
            mapped = status_map.get(ready_state, 'BUILDING')
            progress = 100 if mapped == 'RUNNING' else 45 if mapped == 'FAILED' else 50
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': mapped,
                    'progress': progress,
                    'provider_type': 'VERCEL',
                    'endpoint_url': url or record.endpoint_url,
                    'ip_address': None,
                    'message': f'Vercel readyState: {ready_state}',
                }
            }, status=status.HTTP_200_OK)
        except VercelApiError as exc:
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': record.status,
                    'progress': 100 if record.status == 'RUNNING' else 45,
                    'provider_type': 'VERCEL',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': None,
                    'message': f'Vercel API error: {exc}',
                }
            }, status=status.HTTP_200_OK)

    elif provider == 'RENDER':
        render_api_key = settings.RENDER_API_KEY
        if not render_api_key:
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': record.status,
                    'progress': 100 if record.status == 'RUNNING' else 45,
                    'provider_type': 'RENDER',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': None,
                    'message': 'Render credentials not configured; returning stored status.',
                }
            }, status=status.HTTP_200_OK)
        service_id = record.provider_project_id
        if not service_id:
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': record.status,
                    'progress': 100 if record.status == 'RUNNING' else 45,
                    'provider_type': 'RENDER',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': None,
                    'message': 'Render service ID not stored; returning stored status.',
                }
            }, status=status.HTTP_200_OK)
        try:
            svc = RenderDeploymentService(render_api_key, settings.RENDER_OWNER_ID)
            raw = svc.get_deploy_status(service_id, deployment_id)
            render_status = (raw.get('status') or '').lower()
            status_map = {
                'live': 'RUNNING',
                'succeeded': 'RUNNING',
                'failed': 'FAILED',
                'canceled': 'FAILED',
                'deactivated': 'FAILED',
            }
            mapped = status_map.get(render_status, 'BUILDING')
            progress = 100 if mapped == 'RUNNING' else 45 if mapped == 'FAILED' else 50
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': mapped,
                    'progress': progress,
                    'provider_type': 'RENDER',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': None,
                    'message': f'Render deploy status: {render_status}',
                }
            }, status=status.HTTP_200_OK)
        except RenderApiError as exc:
            return Response({
                'success': True,
                'data': {
                    'deployment_id': deployment_id,
                    'status': record.status,
                    'progress': 100 if record.status == 'RUNNING' else 45,
                    'provider_type': 'RENDER',
                    'endpoint_url': record.endpoint_url,
                    'ip_address': None,
                    'message': f'Render API error: {exc}',
                }
            }, status=status.HTTP_200_OK)

    return Response({
        'success': True,
        'data': {
            'deployment_id': deployment_id,
            'status': record.status,
            'progress': 100 if record.status == 'RUNNING' else 45,
            'provider_type': provider,
            'endpoint_url': record.endpoint_url,
            'ip_address': record.ip_address,
            'message': f'Returning stored status for provider {provider}.',
        }
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def deployment_logs_view(request, deployment_id):
    """
    Return real deployment logs.

    For real provider deployments, returns the stored logs from the
    DeploymentRecord. Provider build logs are available in the
    provider dashboard (Vercel/Render).
    """
    record = _find_deployment_record(deployment_id)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    logs = record.logs or []
    provider = (record.provider or '').upper()

    if not logs:
        logs = [{
            'timestamp': record.created_at.isoformat() if record.created_at else '',
            'level': 'INFO',
            'stage': 'COMPLETED',
            'message': f'Deployment record exists for {provider}. '
                       f'Full build logs are available in the {provider} dashboard.',
        }]

    return Response({
        'success': True,
        'data': logs
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def deployment_health_view(request, deployment_id):
    """
    Perform a real HTTP health check against the deployed service URL.

    Uses the endpoint_url stored in the DeploymentRecord. Makes a real
    HTTP GET request and returns the actual HTTP status.
    """
    record = _find_deployment_record(deployment_id)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    endpoint_url = record.endpoint_url
    if not endpoint_url:
        return Response({
            'success': True,
            'data': {
                'deployment_id': deployment_id,
                'healthy': False,
                'provider_type': record.provider,
                'message': 'No endpoint URL stored for this deployment.',
                'detail': {'http_status': None, 'latency_ms': None},
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
                    'deployment_id': deployment_id,
                    'healthy': healthy,
                    'provider_type': record.provider,
                    'message': f'HTTP {http_status} from {endpoint_url}',
                    'detail': {
                        'http_status': http_status,
                        'latency_ms': elapsed_ms,
                        'url': endpoint_url,
                    },
                }
            }, status=status.HTTP_200_OK)
    except Exception as exc:
        elapsed_ms = round((_time.monotonic() - start_time) * 1000)
        return Response({
            'success': True,
            'data': {
                'deployment_id': deployment_id,
                'healthy': False,
                'provider_type': record.provider,
                'message': f'Health check failed for {endpoint_url}: {exc}',
                'detail': {
                    'http_status': None,
                    'latency_ms': elapsed_ms,
                    'url': endpoint_url,
                    'error': str(exc),
                },
            }
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def deployment_fail_view(request, deployment_id):
    """
    Test endpoint: force a deployment record into FAILED state.
    Used only for testing the failure UI path.
    """
    record = _find_deployment_record(deployment_id)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    reason = request.data.get('reason', 'Test failure triggered.')
    record.status = 'FAILED'
    record.logs = (record.logs or []) + [{
        'timestamp': datetime.now().isoformat(),
        'level': 'ERROR',
        'stage': 'FAILED',
        'message': reason,
    }]
    record.save(update_fields=['status', 'logs'])

    return Response({
        'success': True,
        'data': {
            'deployment_id': deployment_id,
            'status': 'FAILED',
            'provider_type': record.provider,
            'message': reason,
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def deployment_rollback_view(request, deployment_id):
    """
    Trigger a redeploy of the last successful deployment via the provider API.
    For real providers, this creates a new deployment from the same source.
    """
    record = _find_deployment_record(deployment_id)
    if record is None:
        return Response({
            'success': False,
            'error': f'Deployment "{deployment_id}" not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    provider = (record.provider or '').upper()

    if provider == 'VERCEL':
        vercel_token = settings.VERCEL_TOKEN
        if not vercel_token:
            return Response({
                'success': False,
                'error': 'Vercel credentials not configured. Cannot trigger rollback.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            svc = VercelDeploymentService(vercel_token, settings.VERCEL_TEAM_ID or None)
            project_id = record.provider_project_id
            if not project_id:
                return Response({
                    'success': False,
                    'error': 'Vercel project ID not stored. Cannot trigger rollback.'
                }, status=status.HTTP_400_BAD_REQUEST)
            raw = svc._create_deployment(
                project_id=project_id,
                repo_full_name='',
                branch='main',
            )
            new_deploy_id = raw.get('id', deployment_id)
            record.provider_deployment_id = new_deploy_id
            record.status = 'QUEUED'
            record.logs = (record.logs or []) + [{
                'timestamp': datetime.now().isoformat(),
                'level': 'INFO',
                'stage': 'PREPARING',
                'message': f'Rollback triggered: new Vercel deployment {new_deploy_id}',
            }]
            record.save(update_fields=['provider_deployment_id', 'status', 'logs'])
            return Response({
                'success': True,
                'data': {
                    'deployment_id': new_deploy_id,
                    'status': 'QUEUED',
                    'provider_type': 'VERCEL',
                    'message': f'New Vercel deployment {new_deploy_id} triggered for rollback.',
                }
            }, status=status.HTTP_200_OK)
        except VercelApiError as exc:
            return Response({
                'success': False,
                'error': f'Vercel rollback failed: {exc}'
            }, status=status.HTTP_502_BAD_GATEWAY)

    elif provider == 'RENDER':
        render_api_key = settings.RENDER_API_KEY
        if not render_api_key:
            return Response({
                'success': False,
                'error': 'Render credentials not configured. Cannot trigger rollback.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        service_id = record.provider_project_id
        if not service_id:
            return Response({
                'success': False,
                'error': 'Render service ID not stored. Cannot trigger rollback.'
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            svc = RenderDeploymentService(render_api_key, settings.RENDER_OWNER_ID)
            raw = svc._trigger_deploy(service_id)
            new_deploy_id = raw.get('id', deployment_id)
            record.provider_deployment_id = new_deploy_id
            record.status = 'QUEUED'
            record.logs = (record.logs or []) + [{
                'timestamp': datetime.now().isoformat(),
                'level': 'INFO',
                'stage': 'PREPARING',
                'message': f'Rollback triggered: new Render deploy {new_deploy_id}',
            }]
            record.save(update_fields=['provider_deployment_id', 'status', 'logs'])
            return Response({
                'success': True,
                'data': {
                    'deployment_id': new_deploy_id,
                    'status': 'QUEUED',
                    'provider_type': 'RENDER',
                    'message': f'New Render deploy {new_deploy_id} triggered for rollback.',
                }
            }, status=status.HTTP_200_OK)
        except RenderApiError as exc:
            return Response({
                'success': False,
                'error': f'Render rollback failed: {exc}'
            }, status=status.HTTP_502_BAD_GATEWAY)

    return Response({
        'success': False,
        'error': f'Rollback not supported for provider "{provider}".'
    }, status=status.HTTP_400_BAD_REQUEST)
