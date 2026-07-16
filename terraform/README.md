# Terraform (AWS)

This directory contains the Terraform implementation of the shared infrastructure
design contract used across this repository: the same shape is emitted by the
AI optimizer and consumed by the Pulumi implementation, so the input schema
below stays in lockstep with both.

## Design contract

```
project              (string)   e.g. "myapp"
region               (string)   e.g. "us-east-1"
environment           (string)   dev|staging|prod
network.vpc_cidr      (string)   e.g. "10.0.0.0/16"
network.az_count      (number)   2 or 3
kubernetes.version               (string) e.g. "1.29"
kubernetes.node_instance_type    (string) e.g. "m5.large"
kubernetes.node_min / node_max / node_desired (numbers)
database.engine                  (string) "postgres"
database.engine_version          (string) e.g. "15"
database.instance_class          (string) e.g. "db.r6g.large"
database.allocated_storage_gb    (number) e.g. 100
database.multi_az                (bool)
load_balancer.type               (string) "application"
load_balancer.internet_facing    (bool)
tags                              (map(string))
```

See `variables.tf` for the exact Terraform variable definitions.

## Layout

```
terraform/
  versions.tf                 # Terraform + provider version constraints
  variables.tf                # Root input variables (the contract above)
  main.tf                     # Wires the 4 modules together
  outputs.tf                  # vpc_id, subnet ids, EKS/RDS/ALB info
  modules/
    vpc/            # VPC, public/private subnets, IGW, NAT gateway(s), routes
    kubernetes/     # EKS cluster + managed node group + IAM + OIDC provider
    database/       # RDS Postgres + subnet group + SG + Secrets Manager password
    load-balancer/  # ALB + security group + target group + HTTP listener
  environments/
    dev/      # terraform root: provider config + module "stack" + tfvars
    staging/
    prod/
```

`terraform/` itself (the top-level `main.tf`/`variables.tf`/`outputs.tf`) is a
**reusable module** - it holds no provider or backend configuration. Each
`environments/<env>/main.tf` is the actual Terraform root: it configures the
`aws` provider, declares the same variables as the contract, and calls this
module via `module "stack" { source = "../.." }`.

## Usage

```sh
cd terraform/environments/dev      # or staging / prod
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Remote state

Each environment's `backend.tf` ships with a commented-out `backend "s3"`
block. Provision the state bucket + DynamoDB lock table (e.g. via a small
bootstrap stack, out of band) per account/environment, then uncomment and
fill in the real bucket/table names before running `terraform init`.

## Per-environment sizing

| Environment | AZs | NAT strategy      | Node type   | Node desired | DB class        | Multi-AZ |
|-------------|-----|--------------------|-------------|---------------|------------------|----------|
| dev         | 2   | single shared NAT  | t3.medium   | 2             | db.t3.medium     | false    |
| staging     | 2   | single shared NAT  | m5.large    | 2             | db.r6g.large     | false    |
| prod        | 3   | one NAT per AZ     | m5.xlarge   | 3             | db.r6g.xlarge    | true     |

## Notes

- Subnets are tagged with `kubernetes.io/role/elb` (public) /
  `kubernetes.io/role/internal-elb` (private) and
  `kubernetes.io/cluster/<cluster-name>=shared` so the AWS Load Balancer
  Controller and EKS itself can auto-discover them.
- The RDS master password is generated with `random_password` and stored in
  AWS Secrets Manager (`aws_secretsmanager_secret`) - it is never hardcoded
  and applications should fetch it from Secrets Manager at runtime, not from
  Terraform state/outputs.
- The EKS module provisions an IAM OIDC provider so workloads can use IRSA
  (IAM Roles for Service Accounts) instead of the shared node instance role.
