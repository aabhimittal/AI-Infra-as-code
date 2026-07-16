# 5. The AI optimizer

The optimizer answers one question: **"What is the cheapest AWS configuration
that still runs my workload?"** It replaces manual instance-type guesswork with
a search that is constraint-aware and learns from history.

## Pipeline

```
 WorkloadSpec
     │
     ├─▶ policy template         (environment → AZ count, multi-AZ, NAT, autoscale bounds)
     │
     ├─▶ k-NN recommender        (data/history.json → seed genomes)
     │
     ▼
 genetic search  ──uses──▶  cost_model  (minimize)
     │                      capacity_model (must satisfy)
     ▼
 OptimizationResult  ──▶  emit → tfvars / Pulumi config / YAML
```

## The two algorithms

### 1. k-NN recommender (`recommender.py`) — *learn from data*

Historical `(workload → infra)` records live in `data/history.json`. For a new
workload the recommender:

1. builds a feature vector — `peak_rps`, `replicas`, `avg_pod_mem_mib`,
   `db_connections`, `data_size_gb` — **log-scaled** so a 10× traffic difference
   is treated proportionally;
2. **min-max normalizes** across the history so no feature dominates;
3. returns the infra configs of the **k nearest** past workloads.

Those become **seed genomes** for the genetic search — a warm start near
known-good answers. Append real deployments to `history.json` and recommendations
keep improving. The interface (`recommend(workload) -> [Genome]`) can later be
backed by a trained model with no change to callers.

### 2. Genetic algorithm (`genetic.py`) — *search under constraints*

The genome has four genes: `node_instance_type`, `node_desired`,
`db_instance_class`, `allocated_storage_gb`. (AZ count, multi-AZ, and NAT
strategy are fixed by environment policy, not searched.)

**Fitness** (higher is better):

```
feasible    →  -monthly_cost
infeasible  →  -monthly_cost − PENALTY × total_constraint_severity
```

so the population is driven to **feasibility first, then low cost**. Standard GA
operators are used: tournament selection, uniform crossover, per-gene mutation,
and elitism (the best individuals survive each generation). The RNG is seeded, so
runs are **reproducible**.

> Why a GA and not brute force? Today's catalog is small enough to enumerate, but
> a GA scales as the catalog and the number of tunable dimensions grow, and it
> consumes the recommender's seeds naturally. It is the extensible choice.

## The models it optimizes against

### Cost model (`cost_model.py`)

Sums the dominant monthly line items: EKS control plane, worker nodes + root
volumes, NAT gateway(s), RDS compute (×2 for Multi-AZ) + storage, and the ALB.
Prices are representative us-east-1 on-demand rates centralized in `catalog.py`.
It is a **planning estimate**, not a bill.

### Capacity model (`capacity_model.py`)

Every candidate must pass:

| Check | Rule (tunable at top of file) |
|-------|------|
| `compute_throughput` | `vcpu × RPS_PER_VCPU × nodes × utilization ≥ peak_rps` |
| `pod_capacity` / `pod_fit` | requested replicas fit in node memory |
| `db_connections` | `db_mem_gib × CONNECTIONS_PER_GIB ≥ db_connections` |
| `db_storage` | storage ≥ `(data + growth×years) × headroom` |
| `ha_*` (prod / `ha_required`) | multi-AZ RDS, ≥3 nodes, 3 AZs, per-AZ NAT |

## CLI

```bash
python -m aiopt.cli optimize -w examples/workload-prod.yaml           # print plan
python -m aiopt.cli optimize -w examples/workload-prod.yaml \
    --emit-dir out --stack prod                                       # + write artifacts
```

Flags: `--generations`, `--population`, `--seed`, `--stack`, `--emit-dir`.
Exit code is non-zero when no feasible config exists — handy as a CI gate.

## Library

```python
from aiopt import Optimizer, WorkloadSpec
result = Optimizer().optimize(WorkloadSpec(project="myapp", environment="prod",
                                           peak_rps=900, replicas=10,
                                           db_connections=250, data_size_gb=180))
print(result.summary())
print(result.cost.to_dict())
```

## Tuning

- **Prices** → `catalog.py` (or wire it to a live pricing API).
- **Capacity assumptions** (RPS/vCPU, connections/GiB, storage headroom) → the
  constants at the top of `capacity_model.py`. Calibrate them to your own
  load tests for sharper sizing.
- **Search effort** → `--generations` / `--population`.

## Extending

- Add instance families to `catalog.py` and the GA automatically considers them.
- Add genes (e.g. spot vs. on-demand, disk type) by extending `Genome` and the
  operators in `genetic.py`.
- Swap the recommender for a trained regressor behind the same `recommend()` API.
