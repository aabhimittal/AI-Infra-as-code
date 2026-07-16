"""Priced AWS resource catalog — the domain the optimizer searches over.

Prices are representative us-east-1 on-demand rates (USD) and are intentionally
kept in one place so they are easy to refresh or swap for a live pricing API.
They are estimates for planning, not billing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ComputeType:
    """A worker-node (EKS managed node group) instance type."""

    name: str
    vcpu: int
    mem_gib: float
    hourly_usd: float


@dataclass(frozen=True)
class DatabaseType:
    """An RDS instance class."""

    name: str
    vcpu: int
    mem_gib: float
    hourly_usd: float


# --- EKS worker node instance types --------------------------------------- #
# A deliberately diverse slice: burstable (t3), general (m5), compute (c5),
# and memory optimized (r5) so the search can trade CPU for memory for price.
COMPUTE_TYPES: List[ComputeType] = [
    ComputeType("t3.medium", 2, 4, 0.0416),
    ComputeType("t3.large", 2, 8, 0.0832),
    ComputeType("m5.large", 2, 8, 0.096),
    ComputeType("m5.xlarge", 4, 16, 0.192),
    ComputeType("m5.2xlarge", 8, 32, 0.384),
    ComputeType("c5.xlarge", 4, 8, 0.17),
    ComputeType("c5.2xlarge", 8, 16, 0.34),
    ComputeType("r5.large", 2, 16, 0.126),
    ComputeType("r5.xlarge", 4, 32, 0.252),
]

# --- RDS (PostgreSQL) instance classes ------------------------------------ #
DATABASE_TYPES: List[DatabaseType] = [
    DatabaseType("db.t3.medium", 2, 4, 0.068),
    DatabaseType("db.t3.large", 2, 8, 0.136),
    DatabaseType("db.m6g.large", 2, 8, 0.171),
    DatabaseType("db.r6g.large", 2, 16, 0.258),
    DatabaseType("db.m6g.xlarge", 4, 16, 0.342),
    DatabaseType("db.r6g.xlarge", 4, 32, 0.516),
    DatabaseType("db.r6g.2xlarge", 8, 64, 1.032),
]

# --- Fixed / usage prices used by the cost model -------------------------- #
HOURS_PER_MONTH = 730.0
EKS_CONTROL_PLANE_HOURLY = 0.10          # per cluster
NAT_GATEWAY_HOURLY = 0.045               # per NAT gateway
ALB_HOURLY = 0.0225                      # per application load balancer
ALB_LCU_MONTHLY_EST = 8.0                # rough LCU allowance for planning
RDS_STORAGE_GB_MONTHLY = 0.115           # gp3 per-GB-month
EBS_GB_MONTHLY = 0.08                    # node root volume gp3 per-GB-month
NODE_ROOT_VOLUME_GIB = 20

COMPUTE_BY_NAME: Dict[str, ComputeType] = {c.name: c for c in COMPUTE_TYPES}
DATABASE_BY_NAME: Dict[str, DatabaseType] = {d.name: d for d in DATABASE_TYPES}


def compute(name: str) -> ComputeType:
    return COMPUTE_BY_NAME[name]


def database(name: str) -> DatabaseType:
    return DATABASE_BY_NAME[name]
