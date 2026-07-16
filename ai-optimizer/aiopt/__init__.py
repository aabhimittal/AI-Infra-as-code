"""aiopt — AI-based Infrastructure-as-Code optimizer.

Given a *workload* description (expected traffic, data size, availability
requirements, budget) this package searches the space of AWS infrastructure
configurations and emits an *infra spec* that is cheapest while still meeting
the workload's capacity and high-availability constraints.

The emitted infra spec is the canonical contract shared by the Terraform and
Pulumi implementations in this repository, so the optimizer's output can be fed
directly into either tool.

Core pieces
-----------
* ``catalog``        — priced AWS instance / RDS catalog (the search domain).
* ``spec``           — ``WorkloadSpec`` (input) and ``InfraSpec`` (output) types.
* ``cost_model``     — estimates the monthly USD cost of an ``InfraSpec``.
* ``capacity_model`` — checks whether an ``InfraSpec`` satisfies a workload.
* ``genetic``        — the ``GeneticOptimizer`` search algorithm.
* ``recommender``    — ``KNNRecommender`` that warm-starts the search from history.
* ``optimizer``      — ``Optimizer`` orchestrating recommender + GA + constraints.
* ``emit``           — renders the result to tfvars / Pulumi config / YAML.
"""

from .spec import WorkloadSpec, InfraSpec
from .optimizer import Optimizer, OptimizationResult

__all__ = [
    "WorkloadSpec",
    "InfraSpec",
    "Optimizer",
    "OptimizationResult",
]

__version__ = "0.1.0"
