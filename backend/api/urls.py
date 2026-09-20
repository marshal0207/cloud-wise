from django.urls import path
from . import views

urlpatterns = [
    # Health check
    path('health', views.health_view, name='health'),
    
    # Auth
    path('auth/signup', views.signup_view, name='signup'),
    path('auth/login', views.login_view, name='login'),
    
    # Projects API
    path('projects', views.projects_list_create_view, name='projects_list_create'),
    path('projects/<str:pk>', views.project_detail_view, name='project_detail'),
    path('projects/<str:pk>/github', views.project_github_connect_view, name='project_github_connect'),
    path('projects/<str:pk>/github/inspect', views.project_github_inspect_view, name='project_github_inspect'),
    path('projects/<str:pk>/github/push', views.project_github_push_view, name='project_github_push'),
    
    # Core APIs
    path('contact', views.contact_view, name='contact'),
    path('estimate', views.estimate_view, name='estimate'),
    path('deploy', views.deploy_view, name='deploy'),
    path('waitlist', views.waitlist_view, name='waitlist'),
    path('monitoring', views.monitoring_view, name='monitoring'),
    
    # Deployment Management
    path('deployments/<str:deployment_id>/status', views.deployment_status_view, name='deployment_status'),
    path('deployments/<str:deployment_id>/logs', views.deployment_logs_view, name='deployment_logs'),
    path('deployments/<str:deployment_id>/health', views.deployment_health_view, name='deployment_health'),
    path('deployments/<str:deployment_id>/fail', views.deployment_fail_view, name='deployment_fail'),
    path('deployments/<str:deployment_id>/rollback', views.deployment_rollback_view, name='deployment_rollback'),
    
    # Stubs
    path('ai/recommend-workload', views.ai_recommend_view, name='ai_recommend'),
    path('cloud/terraform-export', views.terraform_export_view, name='terraform_export'),
    path('deployment/generate-files', views.generate_deployment_files_view, name='generate_deployment_files'),
    path('github/oauth/start', views.github_oauth_start_view, name='github_oauth_start'),
    path('github/oauth/callback', views.github_oauth_callback_view, name='github_oauth_callback'),
    path('github/repos', views.github_repositories_view, name='github_repositories'),
    path('pricing/aws', views.aws_pricing_view, name='aws_pricing'),
]
