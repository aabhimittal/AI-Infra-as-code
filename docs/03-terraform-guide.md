# 3. Terraform guide

## Layout

```
terraform/
├── versions.tf          # required providers / versions (root module)
├── variables.tf         # inputs mirroring the canonical spec
├── main.tf              # wires the four modules together
├── outputs.tf           # vpc/eks/rds/alb outputs
├── modules/
│   ├── vpc/
│   ├── kubernetes/
│   ├── database/
│   └── load-balancer/
└── environments/
    ├── dev/     { main.tf, terraform.tfvars, backend.tf }
    ├── staging/
    └── prod/
```

The repo root of `terraform/` is a **reusable module** — it declares variables
and wires the sub-modules but configures no provider or backend. The real
Terraform roots are `environments/<env>/`: each configures the `aws` provider,
sets a backend, and calls the shared stack:

```hcl
module "stack" {
  source = "../.."
  # ... pass-through of the environment's variables ...
}
```

## Modules

| Module | Key resources |
|--------|---------------|
| `vpc` | VPC, `az_count` public + private subnets, IGW, NAT gateway(s) (`single_nat_gateway` toggles one shared vs. one per AZ), route tables, EKS/ELB discovery tags |
| `kubernetes` | `aws_eks_cluster`, `aws_eks_node_group`, cluster + node IAM roles, OIDC provider (IRSA), deployed into private subnets |
| `database` | `aws_db_instance` (PostgreSQL), DB subnet group, security group (5432 from VPC CIDR), `random_password` → Secrets Manager, encryption + backups |
| `load-balancer` | `aws_lb` (application), security group (80/443), target group, HTTP listener |

## Deploy

Set the environment with `ENV` (the `Makefile` wraps these):

```bash
cd terraform/environments/dev
terraform init            # make tf-init ENV=dev
terraform plan            # make tf-plan ENV=dev
terraform apply           # make tf-apply ENV=dev
```

### Using optimizer output

The optimizer writes a `terraform.auto.tfvars`. Terraform auto-loads any
`*.auto.tfvars`, and it **overrides** the hand-authored `terraform.tfvars`
defaults, so you just drop it in:

```bash
make optimize ENV=prod STACK=prod
cp out/prod/terraform.auto.tfvars terraform/environments/prod/
make tf-plan ENV=prod
```

## After apply

```bash
# outputs include the cluster name and region
aws eks update-kubeconfig --name $(terraform output -raw eks_cluster_name) \
    --region $(terraform output -raw region)
kubectl get nodes
```

The RDS endpoint and ALB DNS name are also in `terraform output`. The database
password lives in Secrets Manager — retrieve it with:

```bash
aws secretsmanager get-secret-value --secret-id <name-from-output>
```

## State

Each environment keeps **separate state**. For team use, configure the S3
backend in `environments/<env>/backend.tf` (bucket + key + region, optionally a
DynamoDB lock table). CI runs `terraform init -backend=false` so it can validate
without credentials.

## Destroy

```bash
make tf-destroy ENV=dev
```
