import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

def generate_custom_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

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


def default_estimation():
    return {
        "appType": "Microservices & Web APIs",
        "vcpu": 8,
        "ram": 32,
        "storage": 500,
        "traffic": "1,000,000 req/day",
        "region": "Gujarat (GIFT City / Gandhinagar)",
        "performanceTier": "High Performance",
        "budgetTier": "Balanced",
        "calculatedResult": {
            "minCost": 14800,
            "maxCost": 21700,
            "suggestedInstances": 3,
            "bandwidthGB": 450
        }
    }

def default_recommendation():
    return {
        "id": "aws-rec-1",
        "title": "AWS Production Cluster (c6i.xlarge)",
        "provider": "AWS",
        "badge": "Recommended",
        "specs": {"vcpu": 8, "ram": 32, "storage": "500 GB NVMe SSD", "network": "10 Gbps"},
        "monthlyCost": 12280,
        "hourlyCost": 17.00,
        "reliability": "99.99% SLA",
        "features": [
            "Auto-scaling enabled",
            "AWS Shield Standard DDoS Protection",
            "Automated Daily EBS Snapshots",
            "Multi-AZ Replication"
        ],
        "reasoning": "AWS c6i.xlarge provides the optimal balance of compute throughput and low-latency IOPS."
    }

def default_deployment():
    return {
        "status": "idle",
        "progress": 0,
        "logs": [],
        "deployedAt": None,
        "endpointUrl": None,
        "ipAddress": None,
        "environmentName": "cloudwise-prod-cluster"
    }

def default_optimizations():
    return [
        {
            "id": "opt-1",
            "title": "Rightsize Underutilized Compute Instance",
            "category": "Compute",
            "description": "Average CPU utilization over past 7 days was 14%. Downgrading from 8 vCPUs to 4 vCPUs will maintain headroom while cutting cost.",
            "currentCost": 12280,
            "savings": 3480,
            "impact": "High",
            "applied": False
        },
        {
            "id": "opt-2",
            "title": "Delete Unattached EBS Storage Volume",
            "category": "Storage",
            "description": "Found 1 unattached 120GB gp3 volume left over from a previous staging instance setup.",
            "currentCost": 1240,
            "savings": 1240,
            "impact": "Medium",
            "applied": False
        },
        {
            "id": "opt-3",
            "title": "Purchase 1-Year Compute Savings Plan",
            "category": "Reservation",
            "description": "Commit to steady-state baseline usage for 12 months to receive automatic 34% discount off on-demand rates.",
            "currentCost": 8800,
            "savings": 2980,
            "impact": "High",
            "applied": False
        },
        {
            "id": "opt-4",
            "title": "Automate Off-Peak Staging Database Shutdown",
            "category": "Database",
            "description": "Shut down non-production database clusters during weekend non-business hours.",
            "currentCost": 2320,
            "savings": 1490,
            "impact": "Low",
            "applied": False
        }
    ]

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
    selected_recommendation = models.JSONField(default=default_recommendation)
    github_repo = models.JSONField(null=True, blank=True)
    deployment = models.JSONField(default=default_deployment)
    optimizations = models.JSONField(default=default_optimizations)
    
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
    id = models.CharField(max_length=100, primary_key=True, editable=False)
    environment_name = models.CharField(max_length=255)
    provider = models.CharField(max_length=100, default='AWS')
    monthly_cost = models.DecimalField(max_digits=12, decimal_places=2, default=12280.00)
    specs = models.JSONField(default=dict)
    region = models.CharField(max_length=100, default='Asia Pacific (Mumbai)')
    status = models.CharField(max_length=50, default='deployed')
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    endpoint_url = models.CharField(max_length=255, blank=True, null=True)
    logs = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = generate_custom_id('dep')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Deployment {self.environment_name} ({self.status})"


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
