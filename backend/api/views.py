import random
import math
from datetime import datetime
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
@permission_classes([permissions.AllowAny])
def projects_list_create_view(request):
    user_id, user_role, user_obj = get_request_user_info(request)

    if request.method == 'GET':
        if user_obj:
            projects = Project.objects.filter(user=user_obj).order_by('-created_at')
        else:
            projects = Project.objects.filter(user_id_str=user_id).order_by('-created_at')

        # If no projects exist for default_user, auto-seed an initial default project
        if not projects.exists():
            default_proj = Project.objects.create(
                user=user_obj,
                user_id_str=user_id,
                name="E-Commerce API Service",
                description="High-availability microservices backend for payment processing & order handling.",
                environment="Production",
                user_role=user_role,
                current_step="estimation",
                estimation=default_estimation(),
                selected_recommendation=default_recommendation(),
                deployment=default_deployment(),
                optimizations=default_optimizations()
            )
            projects = [default_proj]

        serializer = ProjectSerializer(projects, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        role = request.data.get('role', user_role)
        if role == 'viewer':
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

        description = request.data.get('description', '').strip() or 'Cloud deployment advisory project'
        environment = request.data.get('environment', 'Production')

        project = Project.objects.create(
            user=user_obj,
            user_id_str=user_id,
            name=name,
            description=description,
            environment=environment,
            user_role=role,
            current_step='estimation',
            estimation=default_estimation(),
            selected_recommendation=default_recommendation(),
            deployment={
                **default_deployment(),
                'environmentName': f"{name.lower().replace(' ', '-')}-prod"
            },
            optimizations=default_optimizations()
        )

        return Response({
            'success': True,
            'message': 'Project created successfully',
            'data': ProjectSerializer(project).data
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([permissions.AllowAny])
def project_detail_view(request, pk):
    user_id, user_role, user_obj = get_request_user_info(request)

    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Project not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    role = request.headers.get('x-user-role', request.data.get('role', project.user_role))
    if user_obj and hasattr(user_obj, 'role'):
        role = user_obj.role or role

    if request.method == 'GET':
        return Response({
            'success': True,
            'data': ProjectSerializer(project).data
        }, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        if role == 'viewer':
            return Response({
                'success': False,
                'error': 'Access Denied (RBAC): Read-only "Viewer" role cannot modify project settings.'
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        if 'name' in data:
            project.name = data['name']
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
        if role not in ['owner', 'admin']:
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
def project_github_connect_view(request, pk):
    user_id, user_role, user_obj = get_request_user_info(request)

    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Project not found.'
        }, status=status.HTTP_404_NOT_FOUND)

    role = request.headers.get('x-user-role', user_role)
    if role == 'viewer':
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
@permission_classes([permissions.AllowAny])
def deploy_view(request):
    data = request.data or {}
    env_name = data.get('environmentName', 'cloudwise-prod-cluster')
    provider = data.get('provider', 'AWS')
    monthly_cost = data.get('monthlyCost', 12280)
    specs = data.get('specs', {'vcpu': 8, 'ram': 32, 'storage': '500 GB NVMe'})
    region = data.get('region', 'Asia Pacific (Mumbai)')

    random_ip = f"35.{random.randint(10, 210)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    endpoint = f"https://{env_name.lower().replace(' ', '-')}.cloudwise.app"
    now_time = datetime.now().strftime("%I:%M:%S %p")

    logs = [
        f"[{now_time}] Provisioning initiated for {env_name}...",
        f"[{now_time}] Allocating elastic IP {random_ip}...",
        f"[{now_time}] Mounting storage and establishing VPC routes...",
        f"[{now_time}] Health probes passed. Deployment live at {endpoint}"
    ]

    record = DeploymentRecord.objects.create(
        environment_name=env_name,
        provider=provider,
        monthly_cost=monthly_cost,
        specs=specs,
        region=region,
        status='deployed',
        ip_address=random_ip,
        endpoint_url=endpoint,
        logs=logs
    )

    return Response({
        'success': True,
        'message': 'Deployment recorded successfully',
        'data': DeploymentRecordSerializer(record).data
    }, status=status.HTTP_200_OK)


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
    return Response({
        'success': True,
        'data': {
            'cpuUsage': 38,
            'memoryUsage': 62,
            'storageUsage': 41,
            'networkInMB': 12.4,
            'networkOutMB': 48.7,
            'healthStatus': 'Healthy',
            'clusterUptime': '14d 08h 32m',
            'activeNodes': 3
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
