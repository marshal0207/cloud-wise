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
    
    # Core APIs
    path('contact', views.contact_view, name='contact'),
    path('estimate', views.estimate_view, name='estimate'),
    path('deploy', views.deploy_view, name='deploy'),
    path('waitlist', views.waitlist_view, name='waitlist'),
    path('monitoring', views.monitoring_view, name='monitoring'),
    
    # Stubs
    path('ai/recommend-workload', views.ai_recommend_view, name='ai_recommend'),
    path('cloud/terraform-export', views.terraform_export_view, name='terraform_export'),
]
