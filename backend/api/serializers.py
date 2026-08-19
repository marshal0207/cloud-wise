import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Project, ContactInquiry, EstimationRecord, DeploymentRecord, WaitlistSubscriber

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'company', 'role']

    def get_name(self, obj):
        return obj.first_name or obj.username


class UserSignupSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    company = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate_email(self, value):
        email_clean = value.strip().lower()
        if User.objects.filter(email__iexact=email_clean).exists():
            raise serializers.ValidationError("An account with this email address already exists. Please sign in.")
        return email_clean

    def validate_password(self, value):
        # Strict password validation matching Auth.tsx requirements:
        # Exactly 8 characters, includes uppercase, lowercase, and number
        is_valid = (
            len(value) == 8 and
            re.search(r'[A-Z]', value) and
            re.search(r'[a-z]', value) and
            re.search(r'[0-9]', value)
        )
        if not is_valid:
            raise serializers.ValidationError(
                "Password must be exactly 8 characters and include an uppercase letter, a lowercase letter, and a number."
            )
        return value

    def create(self, validated_data):
        name = validated_data.get('name', '').strip()
        company = validated_data.get('company', 'CloudWise Enterprise').strip() or 'CloudWise Enterprise'
        email = validated_data.get('email', '').strip().lower()
        password = validated_data.get('password')

        username = email.split('@')[0] + '_' + User.objects.count().__str__()

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=name,
            company=company,
            role='owner'
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class ProjectSerializer(serializers.ModelSerializer):
    userId = serializers.CharField(source='user_id_str', read_only=True)
    userRole = serializers.CharField(source='user_role')
    currentStep = serializers.CharField(source='current_step')
    selectedRecommendation = serializers.JSONField(source='selected_recommendation')
    githubRepo = serializers.JSONField(source='github_repo', required=False, allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Project
        fields = [
            'id',
            'userId',
            'name',
            'description',
            'environment',
            'userRole',
            'currentStep',
            'estimation',
            'selectedRecommendation',
            'githubRepo',
            'deployment',
            'optimizations',
            'createdAt',
            'updatedAt'
        ]

    def create(self, validated_data):
        return super().create(validated_data)


class ContactInquirySerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = ContactInquiry
        fields = ['id', 'name', 'email', 'subject', 'message', 'createdAt']

    def validate_email(self, value):
        email_clean = value.strip().lower()
        email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_regex, email_clean):
            raise serializers.ValidationError("Please enter a valid email address.")
        return email_clean


class EstimationRecordSerializer(serializers.ModelSerializer):
    appType = serializers.CharField(source='app_type')
    performanceTier = serializers.CharField(source='performance_tier')
    budgetTier = serializers.CharField(source='budget_tier')
    calculatedResult = serializers.JSONField(source='calculated_result')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = EstimationRecord
        fields = [
            'id',
            'appType',
            'vcpu',
            'ram',
            'storage',
            'traffic',
            'region',
            'performanceTier',
            'budgetTier',
            'calculatedResult',
            'createdAt'
        ]


class DeploymentRecordSerializer(serializers.ModelSerializer):
    environmentName = serializers.CharField(source='environment_name')
    monthlyCost = serializers.DecimalField(source='monthly_cost', max_digits=12, decimal_places=2)
    ipAddress = serializers.CharField(source='ip_address', allow_blank=True, allow_null=True)
    endpointUrl = serializers.CharField(source='endpoint_url', allow_blank=True, allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = DeploymentRecord
        fields = [
            'id',
            'environmentName',
            'provider',
            'monthlyCost',
            'specs',
            'region',
            'status',
            'ipAddress',
            'endpointUrl',
            'logs',
            'createdAt'
        ]


class WaitlistSubscriberSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = WaitlistSubscriber
        fields = ['id', 'email', 'source', 'createdAt']
