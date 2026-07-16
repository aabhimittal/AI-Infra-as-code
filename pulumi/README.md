# Pulumi (AWS, Python)

This directory provisions the same AWS infrastructure as the sibling
`../terraform` implementation — a VPC, an EKS cluster, an RDS Postgres
database, and an Application Load Balancer — from the identical
cloud-agnostic **infra spec** that the AI optimizer emits. The two IaC
backends are interchangeable: whichever one a given environment uses, the
spec schema (and thus the optimizer's output) does not change.

## Layout

```
pulumi/
  Pulumi.yaml            # project definition (name: ai-infra-as-code, runtime: python)
  Pulumi.dev.yaml         # dev stack config (small, single NAT, multi_az=false)
  Pulumi.staging.yaml     # staging stack config (prod-like HA networking, smaller compute)
  Pulumi.prod.yaml        # prod stack config (large, multi_az=true, per-AZ NAT)
  requirements.txt        # pulumi, pulumi-aws, pulumi-random
  __main__.py             # entrypoint: loads config, wires up components, exports outputs
  components/
    config.py             # dataclasses mirroring the infra spec + load_config()
    vpc.py                # VpcComponent
    kubernetes.py          # EksComponent
    database.py            # DatabaseComponent
    load_balancer.py       # LoadBalancerComponent
```

## Infra spec -> Pulumi config mapping

The infra spec's dot-path fields map onto structured Pulumi config keys
under this project's own namespace (`ai-infra-as-code:*`). See
`components/config.py` for the full schema and `Pulumi.dev.yaml` /
`Pulumi.staging.yaml` / `Pulumi.prod.yaml` for worked examples:

| Spec field                          | Pulumi config key                              |
|--------------------------------------|-------------------------------------------------|
| `project`                            | `ai-infra-as-code:project`                       |
| `region`                             | `ai-infra-as-code:region`                        |
| `environment`                        | `ai-infra-as-code:environment`                   |
| `network.vpc_cidr`                   | `ai-infra-as-code:network.vpc_cidr`              |
| `network.az_count`                   | `ai-infra-as-code:network.az_count`              |
| `kubernetes.version`                 | `ai-infra-as-code:kubernetes.version`            |
| `kubernetes.node_instance_type`      | `ai-infra-as-code:kubernetes.node_instance_type` |
| `node_min` / `node_max` / `node_desired` | `ai-infra-as-code:kubernetes.node_{min,max,desired}` |
| `database.*`                         | `ai-infra-as-code:database.*`                    |
| `load_balancer.*`                    | `ai-infra-as-code:load_balancer.*`               |
| `tags`                               | `ai-infra-as-code:tags`                          |

One extra, implementation-only knob lives alongside `network.*`:
`network.single_nat_gateway` (bool) — a single shared NAT gateway for
cost-sensitive stacks (dev) versus one NAT gateway per AZ for
high-availability stacks (staging/prod). It defaults to `true` if omitted.

## Components

* **VpcComponent** (`components/vpc.py`) — VPC, `az_count` public + private
  subnets (CIDRs carved automatically from `vpc_cidr`), an Internet Gateway,
  NAT Gateway(s) (single or per-AZ), and route tables. Public subnets are
  tagged `kubernetes.io/role/elb=1`, private subnets
  `kubernetes.io/role/internal-elb=1`, and every subnet
  `kubernetes.io/cluster/<cluster-name>=shared` so the AWS Load Balancer
  Controller and the Kubernetes AWS cloud provider can auto-discover them.

* **EksComponent** (`components/kubernetes.py`) — an `aws.eks.Cluster`
  deployed into the private subnets, an IAM role for the control plane, an
  IAM OIDC provider (enabling IRSA), a worker-node IAM role, and an
  `aws.eks.NodeGroup` sized from `node_min` / `node_max` / `node_desired`.

* **DatabaseComponent** (`components/database.py`) — an `aws.rds.SubnetGroup`
  over the private subnets, a security group that only allows Postgres
  (5432) traffic from inside the VPC CIDR, a `pulumi_random.RandomPassword`
  master password (never hardcoded, never emitted as a literal in this
  code), an `aws.rds.Instance` (encrypted, backed up, optionally Multi-AZ),
  and an AWS Secrets Manager secret holding the live connection details.

* **LoadBalancerComponent** (`components/load_balancer.py`) — an
  application Load Balancer in the public subnets (internet-facing or
  internal per `load_balancer.internet_facing`), a security group allowing
  80/443, a target group (IP target type, for routing to Kubernetes
  pods/services), and an HTTP listener.

## Usage

```bash
cd pulumi
pulumi stack select dev   # or staging / prod (pulumi stack init <name> first time)
pulumi up
```

Outputs exported by `__main__.py`: `vpc_id`, `cluster_name`,
`cluster_endpoint`, `db_endpoint`, `alb_dns_name`.
