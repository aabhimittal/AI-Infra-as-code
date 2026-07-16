"""Estimate the monthly USD cost of an :class:`InfraSpec`.

The model sums the dominant line items of the reference architecture (EKS
control plane + worker nodes + node storage, NAT gateways, RDS compute +
storage, and the application load balancer). It is a planning estimate, not a
billing figure; data-transfer and request-level charges are approximated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from . import catalog
from .spec import InfraSpec


@dataclass
class CostBreakdown:
    eks_control_plane: float
    worker_nodes: float
    node_storage: float
    nat_gateways: float
    database_compute: float
    database_storage: float
    load_balancer: float

    @property
    def total(self) -> float:
        return round(
            self.eks_control_plane
            + self.worker_nodes
            + self.node_storage
            + self.nat_gateways
            + self.database_compute
            + self.database_storage
            + self.load_balancer,
            2,
        )

    def to_dict(self) -> Dict[str, float]:
        d = {k: round(v, 2) for k, v in self.__dict__.items()}
        d["total"] = self.total
        return d


def estimate_cost(infra: InfraSpec) -> CostBreakdown:
    hours = catalog.HOURS_PER_MONTH
    node = catalog.compute(infra.kubernetes.node_instance_type)
    db = catalog.database(infra.database.instance_class)

    eks_control_plane = catalog.EKS_CONTROL_PLANE_HOURLY * hours

    worker_nodes = node.hourly_usd * infra.kubernetes.node_desired * hours

    node_storage = (
        catalog.NODE_ROOT_VOLUME_GIB
        * catalog.EBS_GB_MONTHLY
        * infra.kubernetes.node_desired
    )

    # dev uses a single NAT gateway; HA uses one per AZ.
    nat_count = 1 if infra.network.single_nat_gateway else infra.network.az_count
    nat_gateways = nat_count * catalog.NAT_GATEWAY_HOURLY * hours

    # Multi-AZ RDS roughly doubles the compute cost (standby replica).
    db_multiplier = 2.0 if infra.database.multi_az else 1.0
    database_compute = db.hourly_usd * hours * db_multiplier
    database_storage = (
        infra.database.allocated_storage_gb * catalog.RDS_STORAGE_GB_MONTHLY
    )

    load_balancer = catalog.ALB_HOURLY * hours + catalog.ALB_LCU_MONTHLY_EST

    return CostBreakdown(
        eks_control_plane=eks_control_plane,
        worker_nodes=worker_nodes,
        node_storage=node_storage,
        nat_gateways=nat_gateways,
        database_compute=database_compute,
        database_storage=database_storage,
        load_balancer=load_balancer,
    )


def monthly_cost(infra: InfraSpec) -> float:
    """Convenience: total estimated monthly cost in USD."""
    return estimate_cost(infra).total
