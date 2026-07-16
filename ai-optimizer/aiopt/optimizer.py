"""High-level orchestration: workload in, optimized :class:`InfraSpec` out.

Pipeline
--------
1. Build a *policy template* from the workload — the fields that are decided by
   rules, not search (environment, AZ count, multi-AZ, NAT strategy, node
   min/max autoscaling bounds, tags).
2. Ask the k-NN recommender for seed genomes from similar past deployments.
3. Run the genetic algorithm, warm-started with those seeds, to pick the
   cheapest feasible node type / count / DB class / storage.
4. Return the winning infra plus a human-readable report (cost breakdown,
   feasibility, budget check).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from . import capacity_model, cost_model
from .capacity_model import STORAGE_FREE_HEADROOM, STORAGE_GROWTH_YEARS
from .cost_model import CostBreakdown
from .genetic import GeneticOptimizer, Genome
from .recommender import KNNRecommender, load_default_history
from .spec import (
    DatabaseSpec,
    InfraSpec,
    KubernetesSpec,
    LoadBalancerSpec,
    NetworkSpec,
    WorkloadSpec,
)


@dataclass
class OptimizationResult:
    infra: InfraSpec
    cost: CostBreakdown
    feasible: bool
    violations: List[str] = field(default_factory=list)
    within_budget: Optional[bool] = None
    seeds_used: int = 0
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        k = self.infra.kubernetes
        d = self.infra.database
        lines = [
            f"Project        : {self.infra.project} ({self.infra.environment})",
            f"Region         : {self.infra.region}",
            f"Nodes          : {k.node_desired}x {k.node_instance_type} "
            f"(autoscale {k.node_min}-{k.node_max})",
            f"Database       : {d.instance_class}, {d.allocated_storage_gb}GB, "
            f"multi_az={d.multi_az}",
            f"Network        : {self.infra.network.az_count} AZs, "
            f"single_nat={self.infra.network.single_nat_gateway}",
            f"Est. cost/mo   : ${self.cost.total:,.2f}",
            f"Feasible       : {self.feasible}",
        ]
        if self.within_budget is not None:
            lines.append(f"Within budget  : {self.within_budget}")
        if self.violations:
            lines.append("Violations     : " + "; ".join(self.violations))
        if self.notes:
            lines.append("Notes          : " + "; ".join(self.notes))
        return "\n".join(lines)


class Optimizer:
    def __init__(
        self,
        recommender: Optional[KNNRecommender] = None,
        *,
        generations: int = 60,
        population_size: int = 40,
        seed: Optional[int] = 42,
    ) -> None:
        # Fall back to the bundled history file if no recommender is injected.
        self.recommender = recommender if recommender is not None else load_default_history()
        self.generations = generations
        self.population_size = population_size
        self.seed = seed

    # --- policy template -------------------------------------------------- #
    def _policy_template(self, w: WorkloadSpec) -> InfraSpec:
        ha = w.high_availability()
        az_count = 3 if ha else 2
        # Autoscaling bounds sized around the workload's replica count.
        node_min = 3 if ha else 2
        node_max = max(node_min + 4, w.replicas)
        recommended_storage = int(
            (w.data_size_gb + w.data_growth_gb_yr * STORAGE_GROWTH_YEARS)
            * STORAGE_FREE_HEADROOM
        )
        tags = {
            "project": w.project,
            "environment": w.environment,
            "managed-by": "ai-infra-as-code",
        }
        return InfraSpec(
            project=w.project,
            region=w.region,
            environment=w.environment,
            network=NetworkSpec(
                vpc_cidr="10.0.0.0/16",
                az_count=az_count,
                single_nat_gateway=not ha,
            ),
            kubernetes=KubernetesSpec(
                version="1.29",
                node_instance_type="m5.large",
                node_min=node_min,
                node_max=node_max,
                node_desired=node_min,
            ),
            database=DatabaseSpec(
                engine="postgres",
                engine_version="15",
                instance_class="db.t3.medium",
                allocated_storage_gb=max(20, recommended_storage),
                multi_az=ha,
            ),
            load_balancer=LoadBalancerSpec(type="application", internet_facing=True),
            tags=tags,
        )

    # --- main entry point ------------------------------------------------- #
    def optimize(self, workload: WorkloadSpec) -> OptimizationResult:
        template = self._policy_template(workload)

        seeds: List[Genome] = []
        notes: List[str] = []
        if self.recommender and not self.recommender.is_empty():
            seeds = self.recommender.recommend(workload)
            notes.append(f"warm-started from {len(seeds)} similar past deployment(s)")
        else:
            notes.append("no history available; cold search")

        ga = GeneticOptimizer(
            workload,
            template,
            population_size=self.population_size,
            generations=self.generations,
            seed=self.seed,
            storage_choices=sorted(
                {20, 50, 100, 200, 400, 800, template.database.allocated_storage_gb}
            ),
        )
        best = ga.run(seeds=seeds)

        infra = best.infra
        violations = capacity_model.check(infra, workload)
        cost = cost_model.estimate_cost(infra)
        within_budget = (
            None
            if workload.monthly_budget_usd is None
            else cost.total <= workload.monthly_budget_usd
        )
        if within_budget is False:
            notes.append(
                f"cheapest feasible config ${cost.total:,.0f} exceeds "
                f"budget ${workload.monthly_budget_usd:,.0f}"
            )

        return OptimizationResult(
            infra=infra,
            cost=cost,
            feasible=len(violations) == 0,
            violations=[f"{v.check}: {v.detail}" for v in violations],
            within_budget=within_budget,
            seeds_used=len(seeds),
            notes=notes,
        )
