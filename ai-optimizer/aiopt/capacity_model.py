"""Check whether an :class:`InfraSpec` can actually carry a workload.

The optimizer must never trade cost for a config that cannot serve the traffic,
so every candidate is validated against these constraints. Each check returns a
``Violation`` with a *severity* (how far short it falls, normalized) that the
genetic algorithm turns into a fitness penalty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import catalog
from .spec import InfraSpec
from .spec import WorkloadSpec


# --- Tunable capacity assumptions ----------------------------------------- #
# Requests/second a single vCPU can serve for a typical stateless web service.
RPS_PER_VCPU = 120.0
# Fraction of node capacity we allow to be used (leave headroom for spikes / DaemonSets).
NODE_UTILIZATION_TARGET = 0.65
# Memory reserved by the kubelet/OS per node, not available to pods.
NODE_MEM_RESERVED_GIB = 1.0
# PostgreSQL max_connections scales roughly with memory.
DB_CONNECTIONS_PER_GIB = 50.0
# Storage headroom: provision for this many years of growth on top of current size.
STORAGE_GROWTH_YEARS = 2.0
STORAGE_FREE_HEADROOM = 1.25  # keep ~25% free


@dataclass
class Violation:
    check: str
    detail: str
    severity: float  # 0 = just met, grows with how badly the constraint is missed


def check(infra: InfraSpec, workload: WorkloadSpec) -> List[Violation]:
    """Return the list of unmet constraints (empty == feasible)."""
    violations: List[Violation] = []
    node = catalog.compute(infra.kubernetes.node_instance_type)
    db = catalog.database(infra.database.instance_class)
    k8s = infra.kubernetes

    # 1. Compute throughput: can the running nodes serve peak RPS with headroom?
    serveable_rps = (
        node.vcpu * RPS_PER_VCPU * k8s.node_desired * NODE_UTILIZATION_TARGET
    )
    if serveable_rps < workload.peak_rps:
        violations.append(
            Violation(
                "compute_throughput",
                f"nodes serve ~{serveable_rps:.0f} rps < peak {workload.peak_rps:.0f} rps",
                severity=(workload.peak_rps - serveable_rps) / max(workload.peak_rps, 1),
            )
        )

    # 2. Pod scheduling: do the requested replicas fit in node memory?
    node_pod_mem_gib = node.mem_gib - NODE_MEM_RESERVED_GIB
    pods_per_node = int(node_pod_mem_gib // max(workload.avg_pod_mem_mib / 1024.0, 0.001))
    capacity_pods = pods_per_node * k8s.node_desired
    if pods_per_node < 1:
        violations.append(
            Violation(
                "pod_fit",
                f"pod needs {workload.avg_pod_mem_mib:.0f}MiB > node free mem",
                severity=1.0,
            )
        )
    elif capacity_pods < workload.replicas:
        violations.append(
            Violation(
                "pod_capacity",
                f"cluster fits {capacity_pods} pods < {workload.replicas} replicas",
                severity=(workload.replicas - capacity_pods) / max(workload.replicas, 1),
            )
        )

    # 3. Database connections: enough memory to back the connection pool?
    max_conns = db.mem_gib * DB_CONNECTIONS_PER_GIB
    if max_conns < workload.db_connections:
        violations.append(
            Violation(
                "db_connections",
                f"db supports ~{max_conns:.0f} conns < {workload.db_connections}",
                severity=(workload.db_connections - max_conns) / max(workload.db_connections, 1),
            )
        )

    # 4. Storage: room for current data plus growth plus free headroom.
    needed = (
        workload.data_size_gb
        + workload.data_growth_gb_yr * STORAGE_GROWTH_YEARS
    ) * STORAGE_FREE_HEADROOM
    if infra.database.allocated_storage_gb < needed:
        violations.append(
            Violation(
                "db_storage",
                f"{infra.database.allocated_storage_gb}GB < needed {needed:.0f}GB",
                severity=(needed - infra.database.allocated_storage_gb) / max(needed, 1),
            )
        )

    # 5. High availability policy for prod / ha_required workloads.
    if workload.high_availability():
        if not infra.database.multi_az:
            violations.append(Violation("ha_database", "multi_az required", 0.5))
        if infra.network.single_nat_gateway:
            violations.append(Violation("ha_nat", "per-AZ NAT required", 0.3))
        if k8s.node_desired < 3:
            violations.append(
                Violation("ha_nodes", "at least 3 nodes required for HA", 0.5)
            )
        if infra.network.az_count < 3:
            violations.append(Violation("ha_az", "3 AZs required for HA", 0.3))

    return violations


def is_feasible(infra: InfraSpec, workload: WorkloadSpec) -> bool:
    return len(check(infra, workload)) == 0


def total_severity(infra: InfraSpec, workload: WorkloadSpec) -> float:
    return sum(v.severity for v in check(infra, workload))
