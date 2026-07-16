# 4. Pulumi guide

The Pulumi program builds the **same** VPC / EKS / RDS / ALB architecture as the
Terraform stack, written in Python.

## Layout

```
pulumi/
├── Pulumi.yaml              # project: ai-infra-as-code, runtime python
├── Pulumi.dev.yaml          # per-stack config (dev / staging / prod)
├── Pulumi.staging.yaml
├── Pulumi.prod.yaml
├── requirements.txt         # pulumi, pulumi-aws, pulumi-random
├── __main__.py              # entrypoint: load config → build components → export
└── components/
    ├── config.py            # dataclasses + load_config() reading pulumi.Config
    ├── vpc.py               # VpcComponent
    ├── kubernetes.py        # EksComponent
    ├── database.py          # DatabaseComponent
    └── load_balancer.py     # LoadBalancerComponent
```

Each component is a `pulumi.ComponentResource`, so resources are grouped under a
single logical node in the Pulumi resource graph and outputs are registered
cleanly.

## Setup

```bash
cd pulumi
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# choose a state backend
pulumi login                       # Pulumi Cloud
# or: pulumi login s3://my-pulumi-state-bucket
```

## Stacks

One stack per environment. Configuration lives in `Pulumi.<stack>.yaml`, with
keys namespaced under `ai-infra-as-code:` (plus `aws:region`). Select and deploy:

```bash
pulumi stack select dev            # or: pulumi stack init dev
pulumi preview  --stack dev
pulumi up       --stack dev
```

### Using optimizer output

The optimizer emits a ready-made stack config:

```bash
make optimize ENV=prod STACK=prod
cp out/prod/Pulumi.prod.yaml pulumi/
cd pulumi && pulumi up --stack prod
```

You can also set individual values by hand:

```bash
pulumi config set ai-infra-as-code:node_instance_type m5.large --stack dev
pulumi config set ai-infra-as-code:db_multi_az true --stack prod
```

## Outputs

`__main__.py` exports the same values the Terraform stack outputs:

```bash
pulumi stack output cluster_name
pulumi stack output cluster_endpoint
pulumi stack output db_endpoint
pulumi stack output alb_dns_name
```

Connect `kubectl`:

```bash
aws eks update-kubeconfig \
    --name $(pulumi stack output cluster_name) \
    --region $(pulumi config get aws:region)
kubectl get nodes
```

The database password is generated with `pulumi-random` and stored in Secrets
Manager — it is never written into the stack config.

## Destroy

```bash
pulumi destroy --stack dev
```

## Terraform vs. Pulumi — which to pick?

They produce identical infrastructure here. Choose Terraform for HCL and a large
module ecosystem; choose Pulumi to express infrastructure in Python (and share
language/tooling with the optimizer). You do **not** run both against the same
account — pick one per environment.
