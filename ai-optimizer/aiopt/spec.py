"""Input and output data types for the optimizer.

``WorkloadSpec`` is what a user provides (what the application needs).
``InfraSpec`` is what the optimizer produces (the concrete AWS shape) and is the
canonical contract also consumed by the Terraform and Pulumi implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional


# --------------------------------------------------------------------------- #
# Workload (optimizer input)
# --------------------------------------------------------------------------- #
@dataclass
class WorkloadSpec:
    """Application requirements the infrastructure must satisfy.

    Attributes
    ----------
    project:            short name, used for tagging / resource naming.
    environment:        ``dev`` | ``staging`` | ``prod`` (drives HA policy).
    region:             AWS region.
    peak_rps:           expected peak HTTP requests/second at the app tier.
    avg_pod_mem_mib:    memory a single app pod requests.
    replicas:           desired number of application pods.
    db_connections:     peak concurrent database connections needed.
    data_size_gb:       current relational data size.
    data_growth_gb_yr:  expected yearly data growth (sizes storage headroom).
    monthly_budget_usd: soft cap; the optimizer minimizes cost and flags overrun.
    ha_required:        require multi-AZ / redundancy regardless of environment.
    """

    project: str
    environment: str = "dev"
    region: str = "us-east-1"
    peak_rps: float = 200.0
    avg_pod_mem_mib: float = 512.0
    replicas: int = 6
    db_connections: int = 100
    data_size_gb: float = 50.0
    data_growth_gb_yr: float = 50.0
    monthly_budget_usd: Optional[float] = None
    ha_required: bool = False

    def high_availability(self) -> bool:
        """Whether this workload must be provisioned for high availability."""
        return self.ha_required or self.environment == "prod"

    @classmethod
    def from_dict(cls, d: Dict) -> "WorkloadSpec":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> Dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Infrastructure (optimizer output / shared IaC contract)
# --------------------------------------------------------------------------- #
@dataclass
class NetworkSpec:
    vpc_cidr: str = "10.0.0.0/16"
    az_count: int = 2
    single_nat_gateway: bool = True


@dataclass
class KubernetesSpec:
    version: str = "1.29"
    node_instance_type: str = "m5.large"
    node_min: int = 2
    node_max: int = 6
    node_desired: int = 2


@dataclass
class DatabaseSpec:
    engine: str = "postgres"
    engine_version: str = "15"
    instance_class: str = "db.t3.medium"
    allocated_storage_gb: int = 20
    multi_az: bool = False


@dataclass
class LoadBalancerSpec:
    type: str = "application"
    internet_facing: bool = True


@dataclass
class InfraSpec:
    """A concrete, deployable AWS infrastructure shape.

    This mirrors — field for field — the variables consumed by the Terraform
    modules and the Pulumi components in this repo.
    """

    project: str
    region: str = "us-east-1"
    environment: str = "dev"
    network: NetworkSpec = field(default_factory=NetworkSpec)
    kubernetes: KubernetesSpec = field(default_factory=KubernetesSpec)
    database: DatabaseSpec = field(default_factory=DatabaseSpec)
    load_balancer: LoadBalancerSpec = field(default_factory=LoadBalancerSpec)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "InfraSpec":
        return cls(
            project=d["project"],
            region=d.get("region", "us-east-1"),
            environment=d.get("environment", "dev"),
            network=NetworkSpec(**d.get("network", {})),
            kubernetes=KubernetesSpec(**d.get("kubernetes", {})),
            database=DatabaseSpec(**d.get("database", {})),
            load_balancer=LoadBalancerSpec(**d.get("load_balancer", {})),
            tags=d.get("tags", {}),
        )
