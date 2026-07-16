"""Entrypoint for the AI-Infra-as-code Pulumi AWS stack.

Reads the cloud-agnostic infra spec from Pulumi stack config (see
components/config.py), then wires up the four building blocks — network,
Kubernetes, database, and load balancer — in the same shape the Terraform
implementation (../terraform) produces, so the AI optimizer's spec output
can drive either backend interchangeably.
"""

import pulumi
import pulumi_aws as aws

from components import (
    DatabaseComponent,
    EksComponent,
    LoadBalancerComponent,
    VpcComponent,
    load_config,
)

# --- Load and validate the infra spec from Pulumi config -----------------------
spec = load_config()

# AWS provider pinned to the region declared in the spec, used explicitly by
# every child resource via ComponentResource parenting + the default
# provider so `pulumi up --stack <name>` always targets the right region
# regardless of the environment's AWS_REGION/AWS_DEFAULT_REGION.
aws_provider = aws.Provider("aws", region=spec.region)
provider_opts = pulumi.ResourceOptions(providers={"aws": aws_provider})

# Deterministic naming prefix shared by every resource, and the EKS cluster
# name in particular — the VPC needs to know it up front so it can apply the
# `kubernetes.io/cluster/<name>=shared` subnet tag before the cluster exists.
name_prefix = f"{spec.project}-{spec.environment}"
cluster_name = f"{name_prefix}-eks"

base_tags = spec.base_tags()

# --- Network ---------------------------------------------------------------
vpc = VpcComponent(
    name_prefix,
    vpc_cidr=spec.network.vpc_cidr,
    az_count=spec.network.az_count,
    single_nat_gateway=spec.network.single_nat_gateway,
    cluster_name=cluster_name,
    tags=base_tags,
    opts=provider_opts,
)

# --- Kubernetes (EKS) --------------------------------------------------------
eks = EksComponent(
    name_prefix,
    cluster_name=cluster_name,
    kubernetes_version=spec.kubernetes.version,
    vpc_id=vpc.vpc_id,
    private_subnet_ids=vpc.private_subnet_ids,
    node_instance_type=spec.kubernetes.node_instance_type,
    node_min=spec.kubernetes.node_min,
    node_max=spec.kubernetes.node_max,
    node_desired=spec.kubernetes.node_desired,
    tags=base_tags,
    opts=provider_opts,
)

# --- Database (RDS Postgres) -------------------------------------------------
database = DatabaseComponent(
    name_prefix,
    vpc_id=vpc.vpc_id,
    vpc_cidr=vpc.vpc_cidr,
    private_subnet_ids=vpc.private_subnet_ids,
    engine_version=spec.database.engine_version,
    instance_class=spec.database.instance_class,
    allocated_storage_gb=spec.database.allocated_storage_gb,
    multi_az=spec.database.multi_az,
    tags=base_tags,
    opts=provider_opts,
)

# --- Load balancer -----------------------------------------------------------
load_balancer = LoadBalancerComponent(
    name_prefix,
    vpc_id=vpc.vpc_id,
    public_subnet_ids=vpc.public_subnet_ids,
    internet_facing=spec.load_balancer.internet_facing,
    tags=base_tags,
    opts=provider_opts,
)

# --- Stack outputs -----------------------------------------------------------
pulumi.export("vpc_id", vpc.vpc_id)
pulumi.export("cluster_name", eks.cluster_name)
pulumi.export("cluster_endpoint", eks.cluster_endpoint)
pulumi.export("db_endpoint", database.db_endpoint)
pulumi.export("alb_dns_name", load_balancer.alb_dns_name)
