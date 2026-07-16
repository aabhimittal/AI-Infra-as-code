"""Typed configuration model for the AI-Infra-as-code Pulumi program.

This module mirrors the cloud-agnostic "infra spec" schema that the AI
optimizer emits and that the Terraform implementation also consumes (see
../../terraform). Keeping the schema identical across both IaC backends is
the whole point of this repo: the AI optimizer should not need to know or
care whether the target stack is realized with Pulumi or Terraform.

Spec shape (dot-paths map onto structured Pulumi config keys):

    project, region, environment(dev|staging|prod)
    network.vpc_cidr, network.az_count(2|3)
    kubernetes.version, kubernetes.node_instance_type,
        node_min, node_max, node_desired
    database.engine("postgres"), database.engine_version,
        database.instance_class, database.allocated_storage_gb,
        database.multi_az(bool)
    load_balancer.type("application"), load_balancer.internet_facing(bool)
    tags (map)

In Pulumi config (Pulumi.<stack>.yaml) these are expressed as structured
YAML under the project's own config namespace, e.g.:

    config:
      ai-infra-as-code:project: my-app
      ai-infra-as-code:region: us-east-1
      ai-infra-as-code:environment: dev
      ai-infra-as-code:network:
        vpc_cidr: 10.0.0.0/16
        az_count: 2
        single_nat_gateway: true
      ai-infra-as-code:kubernetes:
        version: "1.29"
        node_instance_type: t3.medium
        node_min: 1
        node_max: 3
        node_desired: 2
      ai-infra-as-code:database:
        engine: postgres
        engine_version: "15.4"
        instance_class: db.t3.medium
        allocated_storage_gb: 20
        multi_az: false
      ai-infra-as-code:load_balancer:
        type: application
        internet_facing: true
      ai-infra-as-code:tags:
        Team: platform
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

import pulumi


@dataclass(frozen=True)
class NetworkConfig:
    """network.* section of the infra spec."""

    vpc_cidr: str
    az_count: int
    # Implementation detail (not a top-level spec field, but required to
    # satisfy "single NAT gateway for dev, one per-AZ otherwise"). Defaults
    # to True for cost-conscious dev/staging stacks and should be set to
    # false explicitly for prod via stack config.
    single_nat_gateway: bool = True

    def __post_init__(self) -> None:
        if self.az_count not in (2, 3):
            raise ValueError(f"network.az_count must be 2 or 3, got {self.az_count}")


@dataclass(frozen=True)
class KubernetesConfig:
    """kubernetes.* section of the infra spec (plus the sibling node_* fields)."""

    version: str
    node_instance_type: str
    node_min: int
    node_max: int
    node_desired: int

    def __post_init__(self) -> None:
        if not (self.node_min <= self.node_desired <= self.node_max):
            raise ValueError(
                "kubernetes node sizing must satisfy node_min <= node_desired <= "
                f"node_max, got min={self.node_min}, desired={self.node_desired}, "
                f"max={self.node_max}"
            )


@dataclass(frozen=True)
class DatabaseConfig:
    """database.* section of the infra spec."""

    engine: str
    engine_version: str
    instance_class: str
    allocated_storage_gb: int
    multi_az: bool

    def __post_init__(self) -> None:
        if self.engine != "postgres":
            raise ValueError(f"database.engine must be 'postgres', got {self.engine!r}")


@dataclass(frozen=True)
class LoadBalancerConfig:
    """load_balancer.* section of the infra spec."""

    type: str
    internet_facing: bool

    def __post_init__(self) -> None:
        if self.type != "application":
            raise ValueError(
                f"load_balancer.type must be 'application', got {self.type!r}"
            )


@dataclass(frozen=True)
class InfraSpec:
    """Top-level infra spec, fully resolved from Pulumi stack config."""

    project: str
    region: str
    environment: str
    network: NetworkConfig
    kubernetes: KubernetesConfig
    database: DatabaseConfig
    load_balancer: LoadBalancerConfig
    tags: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.environment not in ("dev", "staging", "prod"):
            raise ValueError(
                f"environment must be one of dev|staging|prod, got {self.environment!r}"
            )

    def base_tags(self) -> Dict[str, str]:
        """Common tags applied to every resource, merging spec tags with
        standard bookkeeping tags."""
        return {
            **self.tags,
            "Project": self.project,
            "Environment": self.environment,
            "ManagedBy": "pulumi",
        }


def _get_int(cfg: pulumi.Config, container: dict, key: str, default: Optional[int] = None) -> int:
    value = container.get(key, default)
    if value is None:
        raise ValueError(f"missing required config value: {key}")
    return int(value)


def load_config() -> InfraSpec:
    """Read the infra spec out of Pulumi stack config (Pulumi.<stack>.yaml)
    and return a validated, strongly-typed InfraSpec.

    Uses the project's own config namespace (no explicit prefix needed when
    calling pulumi.Config() with no args from within this project).
    """
    cfg = pulumi.Config()

    project = cfg.require("project")
    region = cfg.require("region")
    environment = cfg.require("environment")

    network_raw = cfg.require_object("network")
    network = NetworkConfig(
        vpc_cidr=network_raw["vpc_cidr"],
        az_count=int(network_raw["az_count"]),
        single_nat_gateway=bool(network_raw.get("single_nat_gateway", True)),
    )

    k8s_raw = cfg.require_object("kubernetes")
    kubernetes = KubernetesConfig(
        version=str(k8s_raw["version"]),
        node_instance_type=k8s_raw["node_instance_type"],
        node_min=_get_int(cfg, k8s_raw, "node_min"),
        node_max=_get_int(cfg, k8s_raw, "node_max"),
        node_desired=_get_int(cfg, k8s_raw, "node_desired"),
    )

    db_raw = cfg.require_object("database")
    database = DatabaseConfig(
        engine=db_raw.get("engine", "postgres"),
        engine_version=str(db_raw["engine_version"]),
        instance_class=db_raw["instance_class"],
        allocated_storage_gb=int(db_raw["allocated_storage_gb"]),
        multi_az=bool(db_raw["multi_az"]),
    )

    lb_raw = cfg.require_object("load_balancer")
    load_balancer = LoadBalancerConfig(
        type=lb_raw.get("type", "application"),
        internet_facing=bool(lb_raw["internet_facing"]),
    )

    tags = cfg.get_object("tags") or {}

    return InfraSpec(
        project=project,
        region=region,
        environment=environment,
        network=network,
        kubernetes=kubernetes,
        database=database,
        load_balancer=load_balancer,
        tags=tags,
    )
