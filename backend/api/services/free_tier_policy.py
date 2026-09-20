from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FreeTierLimits:
    max_vcpu: int = 2
    max_ram_gb: int = 2
    max_storage_gb: int = 30
    max_instances: int = 1


class FreeTierLimitError(ValueError):
    pass


FREE_TIER_ELIGIBLE_INSTANCES = ("t2.micro", "t3.micro")


def validate_free_tier_deployment(
    *,
    vcpu: int,
    ram_gb: int,
    storage_gb: int,
    instances: int = 1,
    limits: FreeTierLimits | None = None,
) -> dict[str, int]:
    limits = limits or FreeTierLimits()
    values = {
        'vCPU': vcpu,
        'RAM': ram_gb,
        'storage': storage_gb,
        'instances': instances,
    }
    if any(not isinstance(value, int) or value <= 0 for value in values.values()):
        raise FreeTierLimitError('Deployment resources must be positive integers.')

    violations = []
    if vcpu > limits.max_vcpu:
        violations.append(f'vCPU cannot exceed {limits.max_vcpu}.')
    if ram_gb > limits.max_ram_gb:
        violations.append(f'RAM cannot exceed {limits.max_ram_gb} GB.')
    if storage_gb > limits.max_storage_gb:
        violations.append(f'Storage cannot exceed {limits.max_storage_gb} GB.')
    if instances > limits.max_instances:
        violations.append(f'Instances cannot exceed {limits.max_instances}.')

    if violations:
        raise FreeTierLimitError(
            'This deployment exceeds the AWS Free Tier demo limits: '
            + ' '.join(violations)
        )

    return {
        'vCPU': vcpu,
        'ramGB': ram_gb,
        'storageGB': storage_gb,
        'instances': instances,
    }


def evaluate_free_tier_eligibility(
    *,
    vcpu: int,
    ram_gb: int,
    storage_gb: int,
    instances: int = 1,
    instance_type: str = "custom",
) -> dict[str, Any]:
    """
    Evaluates workload specs against AWS Free Tier rules and provides
    cost recommendations if user selected higher-tier or paid instances.
    """
    limits = FreeTierLimits()
    violations = []

    if vcpu > limits.max_vcpu:
        violations.append(f"{vcpu} vCPUs requested (Free Tier covers up to 1-2 vCPU t3.micro)")
    if ram_gb > limits.max_ram_gb:
        violations.append(f"{ram_gb} GB RAM requested (Free Tier covers up to 1 GB RAM)")
    if storage_gb > limits.max_storage_gb:
        violations.append(f"{storage_gb} GB storage requested (Free Tier covers up to 30 GB EBS)")
    if instances > limits.max_instances:
        violations.append(f"{instances} instances requested (Free Tier covers 1 single instance, 750 hrs/mo)")

    is_free_tier = len(violations) == 0

    recommendation_needed = not is_free_tier

    free_tier_rec = {
        "instanceType": "t3.micro",
        "vcpu": 1,
        "ram": 1,
        "storage": 30,
        "monthlyCostUSD": 0,
        "monthlyCostINR": 0,
        "badge": "AWS Free Tier (100% Free)",
        "description": "750 hours/month of t3.micro instance with 30GB EBS SSD storage. Perfect for development, staging, and lightweight APIs."
    }

    low_cost_rec = {
        "instanceType": "t3.small",
        "vcpu": 2,
        "ram": 2,
        "storage": 50,
        "monthlyCostUSD": 15,
        "monthlyCostINR": 1245,
        "badge": "Low-Cost Budget Option",
        "description": "Double compute capacity (2 vCPU, 2GB RAM) at ~$15/mo for small production web apps."
    }

    return {
        "isFreeTier": is_free_tier,
        "violations": violations,
        "recommendationNeeded": recommendation_needed,
        "freeTierRecommendation": free_tier_rec,
        "lowCostRecommendation": low_cost_rec,
        "selectedSpecs": {
            "vcpu": vcpu,
            "ram": ram_gb,
            "storage": storage_gb,
            "instances": instances,
            "instanceType": instance_type,
        }
    }
