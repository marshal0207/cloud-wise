import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

def generate_custom_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def default_estimation():
    return {}

def default_recommendation():
    return None

def default_deployment():
    return None

def default_optimizations():
    return None

class CustomUser(AbstractUser):
    company = models.CharField(max_length=255, default='CloudWise Enterprise')
    role = models.CharField(
        max_length=50, 
        choices=[
            ('owner', 'Owner'),
            ('editor', 'Editor'),
            ('viewer', 'Viewer'),
            ('admin', 'Admin')
        ], 
        default='owner'
    )

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return f"{self.email} ({self.company})"




class Project(models.Model):
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='projects', null=True, blank=True)
    user_id_str = models.CharField(max_length=100, default='default_user')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='Cloud deployment advisory project')
    environment = models.CharField(max_length=100, default='Production')
    user_role = models.CharField(max_length=50, default='owner')
    current_step = models.CharField(max_length=50, default='estimation')
    
    estimation = models.JSONField(default=default_estimation)
    selected_recommendation = models.JSONField(null=True, blank=True, default=default_recommendation)
    github_repo = models.JSONField(null=True, blank=True)
    deployment = models.JSONField(null=True, blank=True, default=default_deployment)
    optimizations = models.JSONField(null=True, blank=True, default=default_optimizations)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('proj')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.environment})"


class ContactInquiry(models.Model):
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255, default='General Inquiry')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('contact')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Contact from {self.name} ({self.email})"


class EstimationRecord(models.Model):
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    app_type = models.CharField(max_length=255, default='Microservices & Web APIs')
    vcpu = models.IntegerField(default=8)
    ram = models.IntegerField(default=32)
    storage = models.IntegerField(default=500)
    traffic = models.CharField(max_length=255, default='1,000,000 req/day')
    region = models.CharField(max_length=255, default='Gujarat (GIFT City / Gandhinagar)')
    performance_tier = models.CharField(max_length=255, default='High Performance')
    budget_tier = models.CharField(max_length=255, default='Balanced')
    calculated_result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('est')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Estimation {self.id} ({self.app_type})"


class DeploymentRecord(models.Model):
    """
    One end-to-end deployment of a user's GitHub repository into the
    same user's AWS account.

    Every row is owned by exactly one user and pins the GitHub
    connection, the AWS connection, the repository and the EC2
    instance that were used, so authorization and auditing never have
    to guess.
    """
    id = models.CharField(max_length=100, primary_key=True, editable=False)

    # --- ownership / provenance -------------------------------------
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='deployment_records')
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='deployment_records')
    github_connection = models.ForeignKey('GitHubConnection', on_delete=models.SET_NULL, null=True, blank=True, related_name='deployment_records')
    aws_connection = models.ForeignKey('AWSConnection', on_delete=models.SET_NULL, null=True, blank=True, related_name='deployment_records')

    # --- source -----------------------------------------------------
    environment_name = models.CharField(max_length=255)
    repository = models.CharField(max_length=255, blank=True, default='')
    commit_sha = models.CharField(max_length=64, blank=True, default='')
    project_type = models.CharField(max_length=150, blank=True, default='')

    # --- provider ---------------------------------------------------
    provider = models.CharField(max_length=100, default='AWS')
    provider_deployment_id = models.CharField(max_length=255, blank=True, null=True)
    provider_project_id = models.CharField(max_length=255, blank=True, null=True)

    # --- target infrastructure (inside the user's AWS account) ------
    aws_account_id = models.CharField(max_length=64, blank=True, default='')
    region = models.CharField(max_length=100, default='Asia Pacific (Mumbai)')
    instance_id = models.CharField(max_length=64, blank=True, default='')
    instance_type = models.CharField(max_length=50, blank=True, default='')

    # --- outcome ----------------------------------------------------
    monthly_cost = models.DecimalField(max_digits=12, decimal_places=2, default=12280.00)
    specs = models.JSONField(default=dict)
    deployment_status = models.CharField(max_length=50, default='QUEUED')
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    live_url = models.CharField(max_length=255, blank=True, null=True)
    logs = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # Compatibility aliases — the canonical columns are
    # ``deployment_status`` and ``live_url``.
    # ------------------------------------------------------------------
    @property
    def status(self):
        return self.deployment_status

    @status.setter
    def status(self, value):
        self.deployment_status = value

    @property
    def endpoint_url(self):
        return self.live_url

    @endpoint_url.setter
    def endpoint_url(self, value):
        self.live_url = value

    @property
    def failure_stage(self):
        """Stage of the most recent ERROR log entry, if the deployment failed."""
        for entry in reversed(self.logs or []):
            if entry.get('level') == 'ERROR':
                return str(entry.get('stage') or '')
        return ''

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('dep')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Deployment {self.environment_name} ({self.deployment_status})"


class WaitlistSubscriber(models.Model):
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    email = models.EmailField(unique=True)
    source = models.CharField(max_length=100, default='home_page')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('wait')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class GitHubConnection(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='github_connection')
    access_token = models.TextField()  # Encrypted access token storage
    github_user_id = models.CharField(max_length=100, blank=True, default='')
    github_login = models.CharField(max_length=255, blank=True, default='')
    scopes = models.CharField(max_length=255, default='repo,workflow', blank=True)
    status = models.CharField(max_length=50, default='connected', blank=True)  # connected | expired | revoked
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_token(self, plain_token: str):
        from .services.token_encryption import encrypt_token
        self.access_token = encrypt_token(plain_token)

    def get_token(self) -> str:
        from .services.token_encryption import decrypt_token
        return decrypt_token(self.access_token)

    def __str__(self):
        return f"GitHub connection for {self.user.email or self.user.username} ({self.github_login or 'connected'})"


class AWSConnection(models.Model):
    """
    User's AWS account connection via IAM Role + STS AssumeRole.

    Stores ONLY the minimum required connection information:
    the target role ARN, a per-user external ID, and the resolved
    AWS account ID. No long-lived AWS secret keys are ever stored.
    Temporary credentials are assumed on demand and kept in memory only.
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='aws_connection')
    role_arn = models.CharField(max_length=255)
    external_id = models.CharField(max_length=128)
    account_id = models.CharField(max_length=64, blank=True, default='')
    region = models.CharField(max_length=50, default='ap-south-1')
    status = models.CharField(max_length=30, default='active')  # pending | active
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AWS connection for {self.user.email or self.user.username} ({self.account_id or 'unverified'})"


class EC2Instance(models.Model):
    """
    CloudWise-managed EC2 instance in the user's AWS account.

    Used to reuse existing instances across deployments instead of
    creating a new EC2 instance for every deployment.
    """
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True, related_name='ec2_instances')
    instance_id = models.CharField(max_length=64, unique=True)
    region = models.CharField(max_length=50, default='ap-south-1')
    instance_type = models.CharField(max_length=50, default='t3.micro')
    ami_id = models.CharField(max_length=64, blank=True, default='')
    public_ip = models.CharField(max_length=64, blank=True, default='')
    private_ip = models.CharField(max_length=64, blank=True, default='')
    security_group_id = models.CharField(max_length=64, blank=True, default='')
    security_group_name = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=30, default='pending')
    environment_name = models.CharField(max_length=255, blank=True, default='')
    docker_installed = models.BooleanField(default=False)
    deployment_count = models.IntegerField(default=1)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('eci')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.instance_id} ({self.status})"
