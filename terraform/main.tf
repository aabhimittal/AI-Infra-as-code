# =============================================================================
# Root module: wires the vpc, kubernetes (EKS), database (RDS), and
# load-balancer (ALB) modules together into a complete AWS stack.
#
# This module is reusable and holds no provider configuration or backend of
# its own - it is always called from environments/<env>/main.tf, which
# supplies environment-specific variable values and owns the AWS provider +
# remote state configuration.
# =============================================================================

locals {
  # Common name prefix applied to most resources for easy identification.
  name_prefix = "${var.project}-${var.environment}"

  # EKS cluster name is shared between the vpc module (for subnet tagging,
  # required by the Kubernetes AWS cloud provider / LB controller to
  # auto-discover subnets) and the kubernetes module itself.
  cluster_name = "${local.name_prefix}-eks"

  # Resolve the NAT gateway strategy: honor an explicit override, otherwise
  # default to per-AZ NAT gateways in prod (resilience) and a single shared
  # NAT gateway everywhere else (cost savings).
  single_nat_gateway = var.single_nat_gateway != null ? var.single_nat_gateway : var.environment != "prod"

  # Tags applied to every resource across all child modules.
  common_tags = merge(
    {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

# ------------------------------------------------------------------------
# Networking: VPC, public/private subnets, IGW/NAT gateways, route tables.
# ------------------------------------------------------------------------
module "vpc" {
  source = "./modules/vpc"

  project            = var.project
  environment        = var.environment
  vpc_cidr           = var.network.vpc_cidr
  az_count           = var.network.az_count
  single_nat_gateway = local.single_nat_gateway
  cluster_name       = local.cluster_name
  tags               = local.common_tags
}

# ------------------------------------------------------------------------
# EKS: managed Kubernetes control plane + worker node group, deployed into
# the private subnets produced by the vpc module.
# ------------------------------------------------------------------------
module "kubernetes" {
  source = "./modules/kubernetes"

  project            = var.project
  environment        = var.environment
  cluster_name       = local.cluster_name
  cluster_version    = var.kubernetes.version
  node_instance_type = var.kubernetes.node_instance_type
  node_min           = var.kubernetes.node_min
  node_max           = var.kubernetes.node_max
  node_desired       = var.kubernetes.node_desired
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  tags               = local.common_tags
}

# ------------------------------------------------------------------------
# RDS: PostgreSQL database for application data, deployed into the private
# subnets and reachable only from within the VPC.
# ------------------------------------------------------------------------
module "database" {
  source = "./modules/database"

  project              = var.project
  environment          = var.environment
  engine               = var.database.engine
  engine_version       = var.database.engine_version
  instance_class       = var.database.instance_class
  allocated_storage_gb = var.database.allocated_storage_gb
  multi_az             = var.database.multi_az
  vpc_id               = module.vpc.vpc_id
  vpc_cidr             = var.network.vpc_cidr
  private_subnet_ids   = module.vpc.private_subnet_ids
  tags                 = local.common_tags
}

# ------------------------------------------------------------------------
# ALB: public (or internal) entry point for ingress traffic into the
# cluster, deployed into the public subnets.
# ------------------------------------------------------------------------
module "load_balancer" {
  source = "./modules/load-balancer"

  project           = var.project
  environment       = var.environment
  lb_type           = var.load_balancer.type
  internet_facing   = var.load_balancer.internet_facing
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  tags              = local.common_tags
}
