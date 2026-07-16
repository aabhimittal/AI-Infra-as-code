# 1. Architecture

This document explains **what** gets built and **how** the pieces fit together.

## The target platform

Every deployment (Terraform or Pulumi) produces the same AWS reference
architecture:

```
                          Internet
                             │
                    ┌────────▼─────────┐
                    │  Application LB   │   (public subnets)
                    │   :80 / :443      │
                    └────────┬─────────┘
                             │
        ┌────────────────────▼─────────────────────┐
        │                  VPC                       │
        │   ┌───────────── private subnets ───────┐ │
        │   │   EKS managed node group (pods)      │ │
        │   │        │                             │ │
        │   │        ▼                             │ │
        │   │   RDS PostgreSQL (Multi-AZ in prod)  │ │
        │   └──────────────────────────────────────┘ │
        │        NAT gateway(s) ── egress to internet │
        └────────────────────────────────────────────┘
```

### Components

| Component | AWS resources | Purpose |
|-----------|---------------|---------|
| **VPC** | VPC, public + private subnets across AZs, IGW, NAT gateway(s), route tables | Network isolation. Public subnets host the load balancer; private subnets host nodes and the database. |
| **Kubernetes** | EKS cluster, managed node group, IAM roles, OIDC provider | Runs your containerized workloads. Nodes live in private subnets; OIDC enables IRSA (per-pod IAM). |
| **Database** | RDS PostgreSQL, DB subnet group, security group, Secrets Manager secret | Managed relational data. Reachable only from inside the VPC; the master password is generated and stored in Secrets Manager — never in code. |
| **Load balancer** | Application Load Balancer, security group, target group, listener | Public entry point. Terminates HTTP(S) and routes to the cluster. |

## Two implementations, one shape

The repo implements this architecture **twice** so you can choose your tool:

- **Terraform** (`terraform/`) — HCL modules + per-environment roots.
- **Pulumi** (`pulumi/`) — Python `ComponentResource` classes + stacks.

Both consume the **same canonical spec**, so given identical input they build
identical infrastructure. Pick one; you never need both.

```
              InfraSpec (canonical)
             /                      \
   terraform.auto.tfvars      Pulumi.<stack>.yaml
        (variables)                (config)
             \                      /
              same AWS resources
```

## Where the "AI" fits

Choosing instance types, node counts, DB classes, and storage by hand is
guesswork that tends toward over-provisioning. The **AI optimizer**
(`ai-optimizer/`) replaces that guesswork:

1. You describe the **workload** (peak RPS, replicas, pod memory, DB
   connections, data size, budget, HA needs).
2. A **k-NN recommender** finds similar past deployments and proposes starting
   configurations.
3. A **genetic algorithm** searches the catalog for the **cheapest configuration
   that still satisfies** throughput, pod-fit, connection, storage, and
   high-availability constraints.
4. The winner is rendered to `tfvars` and Pulumi config.

See [05-ai-optimizer.md](05-ai-optimizer.md) for the algorithm details.

## Environments

Three environments express different cost/availability trade-offs. The optimizer
encodes these as policy (in `optimizer._policy_template`) and the IaC ships
matching hand-authored defaults:

| | dev | staging | prod |
|-|-----|---------|------|
| AZs | 2 | 2 | 3 |
| NAT gateways | 1 (shared) | 1 (shared) | 1 per AZ |
| Multi-AZ RDS | no | no | yes |
| Min nodes | 2 | 2 | 3 |

## Security posture

- Nodes and the database sit in **private subnets**; only the load balancer is
  internet-facing.
- The database security group allows PostgreSQL (5432) **only from within the
  VPC CIDR**.
- The database master password is **generated at apply time** and stored in
  **AWS Secrets Manager** — it never appears in state as plaintext you typed, in
  tfvars, or in Pulumi config.
- EKS **OIDC/IRSA** lets pods assume narrowly scoped IAM roles instead of
  sharing node credentials.

Next: [02-getting-started.md](02-getting-started.md).
