# 6. End-to-end walkthrough

Zero to a running platform, with the reasoning at each step. This uses the
Terraform path for the deploy; the Pulumi equivalent is noted inline.

## Step 0 — Prerequisites

Follow [02-getting-started.md](02-getting-started.md): AWS credentials, Python,
and Terraform (or Pulumi) installed. Verify:

```bash
aws sts get-caller-identity
terraform version    # or: pulumi version
```

## Step 1 — Describe your workload

Instead of guessing instance types, describe what the app needs. Create
`my-workload.yaml`:

```yaml
project: shop
environment: prod
region: us-east-1
peak_rps: 900          # peak requests/sec
avg_pod_mem_mib: 640   # memory per app pod
replicas: 10           # desired pods
db_connections: 250    # peak DB connections
data_size_gb: 180      # current data
data_growth_gb_yr: 120 # yearly growth
monthly_budget_usd: 3000
ha_required: true
```

## Step 2 — Let the optimizer size the infrastructure

```bash
cd ai-optimizer && pip install -e ".[dev]" && cd ..
python -m aiopt.cli optimize -w my-workload.yaml --emit-dir out/prod --stack prod
```

You get a plan like:

```
Project        : shop (prod)
Nodes          : 6x t3.medium (autoscale 3-10)
Database       : db.t3.large, 525GB, multi_az=True
Network        : 3 AZs, single_nat=False
Est. cost/mo   : $646.72
Feasible       : True
Within budget  : True
Notes          : warm-started from 3 similar past deployment(s)
```

**What happened:** the k-NN recommender seeded the search from similar past
deployments; the genetic algorithm then searched for the cheapest configuration
that (a) serves 900 rps with headroom, (b) fits 10 pods, (c) supports 250 DB
connections, (d) has room for 2 years of data growth, and (e) meets the prod HA
policy (Multi-AZ RDS, 3 AZs, per-AZ NAT, ≥3 nodes). See
[05-ai-optimizer.md](05-ai-optimizer.md).

Three files were written to `out/prod/`:

- `infra.yaml` — the canonical spec (commit it for review/audit).
- `terraform.auto.tfvars` — Terraform inputs.
- `Pulumi.prod.yaml` — Pulumi stack config.

## Step 3 — Review the plan

Open `out/prod/infra.yaml`. This is a human checkpoint before spending money —
confirm the sizes and cost look sane. Adjust the workload and re-run if not.

## Step 4 — Provision networking + compute + data

### Terraform

```bash
cp out/prod/terraform.auto.tfvars terraform/environments/prod/
cd terraform/environments/prod
terraform init
terraform plan       # read it: ~VPC, subnets, EKS, node group, RDS, ALB
terraform apply      # type "yes"
```

### Pulumi (equivalent)

```bash
cp out/prod/Pulumi.prod.yaml pulumi/
cd pulumi && pulumi up --stack prod
```

Provisioning EKS + RDS typically takes **15–25 minutes** (the control plane and
database are the slow parts).

## Step 5 — Connect to the cluster

```bash
# Terraform
aws eks update-kubeconfig \
    --name $(terraform output -raw eks_cluster_name) \
    --region $(terraform output -raw region)

# Pulumi
# aws eks update-kubeconfig --name $(pulumi stack output cluster_name) --region us-east-1

kubectl get nodes           # should list your node group
```

## Step 6 — Deploy a workload and expose it

Apply your app, then front it with the load balancer. A minimal example:

```yaml
# app.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: shop }
spec:
  replicas: 10
  selector: { matchLabels: { app: shop } }
  template:
    metadata: { labels: { app: shop } }
    spec:
      containers:
        - name: shop
          image: public.ecr.aws/nginx/nginx:latest
          ports: [{ containerPort: 80 }]
          resources:
            requests: { memory: "640Mi" }
---
apiVersion: v1
kind: Service
metadata: { name: shop }
spec:
  type: LoadBalancer
  selector: { app: shop }
  ports: [{ port: 80, targetPort: 80 }]
```

```bash
kubectl apply -f app.yaml
kubectl get svc shop -w      # wait for EXTERNAL-IP (the ALB/NLB DNS name)
```

The subnet tags created by the VPC module
(`kubernetes.io/role/elb`, `kubernetes.io/cluster/<name>`) are what let the
in-cluster load balancer controller place the service correctly.

## Step 7 — Connect the app to PostgreSQL

The database endpoint is an output; the password is in Secrets Manager (never in
code):

```bash
terraform output -raw rds_endpoint
aws secretsmanager get-secret-value --secret-id <secret-name-from-output> \
    --query SecretString --output text
```

Inject these into your app as a Kubernetes `Secret` / env vars (ideally via IRSA
so pods read Secrets Manager directly rather than copying the password around).

## Step 8 — Iterate

Traffic grew? Update the workload (e.g. `peak_rps: 1800`), re-run the optimizer,
copy the new `terraform.auto.tfvars`, and `terraform apply`. The diff shows
exactly what scales. Record the deployment in
`ai-optimizer/data/history.json` so future recommendations improve.

## Step 9 — Tear down

```bash
make tf-destroy ENV=prod
# or: cd pulumi && pulumi destroy --stack prod
```

Confirm in the AWS console that the NAT gateways, EKS cluster, and RDS instance
are gone — those are the meaningful ongoing charges.

---

That is the full loop: **describe → optimize → review → deploy → run → iterate →
destroy**, with a single source of truth feeding either IaC tool.
