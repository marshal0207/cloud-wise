from dataclasses import dataclass


@dataclass(frozen=True)
class FreeTierLimits:
    max_vcpu: int = 2
    max_ram_gb: int = 2
    max_storage_gb: int = 30
    max_instances: int = 1


class FreeTierLimitError(ValueError):
    pass


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
