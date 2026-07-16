# AI-Infra-as-Code

Provision a complete AWS platform — **VPC, PostgreSQL database, application load
balancer, and a Kubernetes (EKS) cluster** — using **Terraform *and* Pulumi**,
with an **AI optimizer** that sizes the infrastructure to your workload before
you deploy.

You describe *what your application needs* (traffic, data, availability,
budget). The optimizer searches the space of AWS configurations and emits a
right-sized spec. That same spec drives either IaC tool, so Terraform and Pulumi
build **identical** infrastructure.

```
                         ┌────────────────────────┐
   workload.yaml  ─────▶ │      AI optimizer       │
 (traffic, data, budget) │  k-NN + genetic search  │
                         └───────────┬────────────┘
                                     │ canonical InfraSpec
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
          terraform.auto.tfvars              Pulumi.<stack>.yaml
                     │                               │
                     ▼                               ▼
              ┌────────────┐                  ┌────────────┐
              │ Terraform  │                  │   Pulumi   │
              └─────┬──────┘                  └─────┬──────┘
                    └──────────────┬────────────────┘
                                   ▼
              VPC · EKS · RDS PostgreSQL · Application LB (AWS)
```

## Repository layout

| Path | What it is |
|------|------------|
| [`ai-optimizer/`](ai-optimizer/) | Python package: genetic search + k-NN recommender that right-sizes infra and emits `tfvars` / Pulumi config. |
| [`terraform/`](terraform/) | Terraform modules (`vpc`, `kubernetes`, `database`, `load-balancer`) + `dev`/`staging`/`prod` environments. |
| [`pulumi/`](pulumi/) | The same infrastructure as a Pulumi Python program with one component per resource group. |
| [`docs/`](docs/) | Step-by-step guides — architecture, getting started, per-tool guides, and a full end-to-end walkthrough. |
| [`.github/workflows/`](.github/workflows/) | CI: optimizer tests, `terraform validate`, Pulumi compile-check. |
| `Makefile` | Shortcuts: `make optimize`, `make tf-plan`, `make pulumi-preview`, … |

## The shared contract

Everything is tied together by one canonical spec (see
[`ai-optimizer/aiopt/spec.py`](ai-optimizer/aiopt/spec.py)). The optimizer
*produces* it; Terraform variables and Pulumi config *consume* it field-for-field:

```yaml
project: myapp
region: us-east-1
environment: prod
network:      { vpc_cidr: 10.0.0.0/16, az_count: 3, single_nat_gateway: false }
kubernetes:   { version: "1.29", node_instance_type: m5.large,
                node_min: 3, node_max: 10, node_desired: 3 }
database:     { engine: postgres, engine_version: "15",
                instance_class: db.r6g.large, allocated_storage_gb: 200, multi_az: true }
load_balancer:{ type: application, internet_facing: true }
tags:         { managed-by: ai-infra-as-code }
```

## Quick start (5 steps)

```bash
# 1. Install the optimizer
cd ai-optimizer && pip install -e ".[dev]" && cd ..

# 2. Right-size infra for a workload → writes tfvars + pulumi config into out/prod/
make optimize ENV=prod STACK=prod

# 3a. Deploy with Terraform
cp out/prod/terraform.auto.tfvars terraform/environments/prod/
make tf-init ENV=prod && make tf-plan ENV=prod && make tf-apply ENV=prod

# 3b. …or deploy the same thing with Pulumi
cp out/prod/Pulumi.prod.yaml pulumi/
cd pulumi && pulumi up --stack prod
```

Prefer the guided path? Read [`docs/06-end-to-end-walkthrough.md`](docs/06-end-to-end-walkthrough.md).

## Documentation

1. [Architecture](docs/01-architecture.md) — what gets built and how the pieces fit.
2. [Getting started](docs/02-getting-started.md) — prerequisites and setup.
3. [Terraform guide](docs/03-terraform-guide.md) — modules, environments, state.
4. [Pulumi guide](docs/04-pulumi-guide.md) — components, stacks, config.
5. [AI optimizer](docs/05-ai-optimizer.md) — the algorithms and how to tune them.
6. [End-to-end walkthrough](docs/06-end-to-end-walkthrough.md) — zero → running platform.

## Requirements

- **AWS account** + credentials (`aws configure`) with permission to create VPC/EKS/RDS/ELB.
- **Terraform** ≥ 1.5 *or* **Pulumi** ≥ 3.0 (you only need one).
- **Python** ≥ 3.9 for the optimizer.
- **kubectl** to talk to the cluster after it is up.

> ⚠️ This provisions real, billable AWS resources (EKS, NAT gateways, RDS). Run
> `make tf-destroy` / `pulumi destroy` when you are done experimenting.

## License

MIT — see [LICENSE](LICENSE).
