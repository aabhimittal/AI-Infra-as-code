# 2. Getting started

## Prerequisites

| Tool | Version | Needed for |
|------|---------|-----------|
| AWS account + credentials | — | any deploy |
| AWS CLI | ≥ 2.x | `aws configure`, `aws eks update-kubeconfig` |
| Python | ≥ 3.9 | the AI optimizer |
| Terraform | ≥ 1.5 | the Terraform path (optional if using Pulumi) |
| Pulumi | ≥ 3.0 | the Pulumi path (optional if using Terraform) |
| kubectl | ≥ 1.27 | talking to the cluster |

You only need **one** of Terraform / Pulumi.

## 1. Configure AWS credentials

```bash
aws configure          # access key, secret, default region (e.g. us-east-1)
aws sts get-caller-identity   # verify
```

The identity you use needs permission to create VPC, EKS, RDS, ELB, IAM roles,
and Secrets Manager secrets.

## 2. Install the optimizer

```bash
cd ai-optimizer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m unittest discover -s tests -v   # should pass
cd ..
```

## 3. Pick your remote state / backend (recommended for real use)

State should not live only on your laptop.

- **Terraform** — create an S3 bucket (and optionally a DynamoDB lock table) and
  fill in the `backend "s3"` block in
  `terraform/environments/<env>/backend.tf`. For a first local try you can leave
  the backend commented and use local state.
- **Pulumi** — either log in to Pulumi Cloud (`pulumi login`) or use a self-managed
  backend such as S3 (`pulumi login s3://my-pulumi-state-bucket`).

## 4. Choose your path

- Terraform → [03-terraform-guide.md](03-terraform-guide.md)
- Pulumi → [04-pulumi-guide.md](04-pulumi-guide.md)
- The full guided flow → [06-end-to-end-walkthrough.md](06-end-to-end-walkthrough.md)

## Cost & cleanup warning

EKS, NAT gateways, and RDS bill by the hour whether or not you send traffic. A
dev stack is roughly a few hundred USD/month if left running. **Always tear down
experiments:**

```bash
make tf-destroy ENV=dev        # Terraform
# or
cd pulumi && pulumi destroy --stack dev
```
