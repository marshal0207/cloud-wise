from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser, Project, ContactInquiry, EstimationRecord, DeploymentRecord,
    WaitlistSubscriber, AWSConnection, EC2Instance,
)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'first_name', 'company', 'role', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('CloudWise Custom Fields', {'fields': ('company', 'role')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CloudWise Custom Fields', {'fields': ('company', 'role')}),
    )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'environment', 'user_role', 'current_step', 'user_id_str', 'created_at', 'updated_at']
    list_filter = ['environment', 'user_role', 'current_step']
    search_fields = ['name', 'description', 'user_id_str']


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'subject', 'created_at']
    search_fields = ['name', 'email', 'subject', 'message']


@admin.register(EstimationRecord)
class EstimationRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'app_type', 'vcpu', 'ram', 'storage', 'region', 'created_at']
    list_filter = ['app_type', 'region', 'performance_tier']


@admin.register(DeploymentRecord)
class DeploymentRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'environment_name', 'provider', 'monthly_cost', 'status', 'ip_address', 'created_at']
    list_filter = ['provider', 'status', 'region']


@admin.register(WaitlistSubscriber)
class WaitlistSubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'source', 'created_at']
    search_fields = ['email', 'source']


@admin.register(AWSConnection)
class AWSConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_id', 'role_arn', 'region', 'status', 'connected_at', 'updated_at']
    list_filter = ['status', 'region']
    search_fields = ['user__email', 'user__username', 'account_id', 'role_arn']
    # Never expose secrets: the model stores no access keys by design.


@admin.register(EC2Instance)
class EC2InstanceAdmin(admin.ModelAdmin):
    list_display = ['instance_id', 'user', 'region', 'instance_type', 'status', 'public_ip', 'docker_installed', 'deployment_count', 'created_at']
    list_filter = ['status', 'region', 'instance_type', 'docker_installed']
    search_fields = ['instance_id', 'public_ip', 'user__email']
