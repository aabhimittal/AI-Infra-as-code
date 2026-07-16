# `aiopt` — AI-based Infrastructure-as-Code optimizer

`aiopt` turns a **workload description** (traffic, data, availability needs,
budget) into a **right-sized AWS infrastructure spec**, then renders that spec
directly into Terraform `tfvars` and Pulumi stack config. It is the "AI" in
*AI-Infra-as-Code*: instead of hand-picking instance types and node counts, you
describe the workload and let a search algorithm find the cheapest configuration
that still meets your constraints.

```
 workload.yaml ─▶ [ k-NN recommender ] ─▶ seed configs
                          │
                          ▼
                 [ genetic search ] ── cost model ──┐
                          │           capacity model │
                          ▼                           │
                     InfraSpec ◀───── feasibility ◀──┘
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
 terraform.auto.tfvars  Pulumi.<stack>.yaml  infra.yaml
```

## Why these algorithms?

| Component | Algorithm | Role |
|-----------|-----------|------|
| `recommender.py` | **k-Nearest-Neighbors** over past deployments | Learns from `data/history.json` and warm-starts the search near known-good configs. Improves as real deployments are appended. |
| `genetic.py` | **Genetic algorithm** (tournament selection, crossover, mutation, elitism) | Searches the discrete, constrained config space (node type × count × DB class × storage) for the cheapest *feasible* option. |
| `cost_model.py` | Line-item **cost estimation** | Monthly USD estimate — the value the GA minimizes. |
| `capacity_model.py` | **Constraint checks** (throughput, pod fit, DB connections, storage, HA policy) | Turns "does this config actually work?" into a fitness penalty so the search is driven to feasibility first, cost second. |

The search space is small enough today that brute force would also work — the GA
is used because it scales cleanly as the catalog and the number of tunable
dimensions grow, and because it naturally consumes the recommender's seeds.

## Install

```bash
cd ai-optimizer
python -m venv .venv && source .venv/bin/activate
pip install -e .            # or: pip install -r requirements.txt
```

The core library and tests need **only the standard library**. `PyYAML` is
optional and used only for reading/writing YAML (the CLI accepts JSON without
it).

## Usage

```bash
# Human-readable plan:
python -m aiopt.cli optimize -w examples/workload-prod.yaml

# Also emit IaC artifacts into ./out for the "prod" Pulumi stack:
python -m aiopt.cli optimize -w examples/workload-prod.yaml \
    --emit-dir out --stack prod
```

This writes:

* `out/infra.yaml` — the canonical spec (human review / commit / history).
* `out/terraform.auto.tfvars` — drop into `terraform/environments/<env>/`.
* `out/Pulumi.prod.yaml` — drop into `pulumi/`.

The CLI exits non-zero if no feasible configuration exists within the catalog
(useful as a CI gate).

### As a library

```python
from aiopt import Optimizer, WorkloadSpec

workload = WorkloadSpec(project="myapp", environment="prod",
                        peak_rps=900, replicas=10, db_connections=250,
                        data_size_gb=180, data_growth_gb_yr=120)

result = Optimizer().optimize(workload)
print(result.summary())
print(result.cost.to_dict())
print(result.infra.to_dict())   # feed into emit.to_terraform_tfvars(...)
```

## Workload fields

| Field | Meaning |
|-------|---------|
| `project`, `environment`, `region` | naming, HA policy, AWS region |
| `peak_rps` | peak requests/sec at the app tier |
| `avg_pod_mem_mib`, `replicas` | per-pod memory + desired pod count (pod-fit check) |
| `db_connections` | peak concurrent DB connections |
| `data_size_gb`, `data_growth_gb_yr` | current data + growth (sizes storage) |
| `monthly_budget_usd` | soft cap; overruns are flagged |
| `ha_required` | force high availability regardless of environment (`prod` implies it) |

## Tuning the models

The capacity assumptions (RPS per vCPU, DB connections per GiB, storage
headroom) live at the top of `capacity_model.py`. Prices live in `catalog.py`.
Both are deliberately in one place so you can calibrate them to your own
benchmarks or wire `catalog.py` to a live pricing API.

## Feeding the recommender

Append real `(workload → chosen infra)` records to `data/history.json` after
each deployment. The k-NN recommender picks the nearest past workloads (by
log-scaled, normalized features) and seeds the GA with their configs — so the
system gets faster and more accurate the more you use it.

## Tests

```bash
python -m unittest discover -s tests -v
```
