# =============================================================================
# Prod environment - the actual Terraform root for "prod". Owns the AWS
# provider configuration and instantiates the shared stack module
# (VPC + EKS + RDS + ALB) defined two directories up (terraform/).
#
# Usage:
#   cd terraform/environments/prod
#   terraform init
#   terraform plan  -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars
# =============================================================================

provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}

# --- Variable declarations (values supplied via terraform.tfvars) ----------
# These mirror the shared design contract 1:1 - see terraform/variables.tf.

variable "project" {
  description = "Short project/application name."
  type        = string
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "prod"
}

variable "network" {
  description = "VPC networking configuration."
  type = object({
    vpc_cidr = string
    az_count = number
  })
}

variable "kubernetes" {
  description = "EKS cluster and managed node group configuration."
  type = object({
    version            = string
    node_instance_type = string
    node_min           = number
    node_max           = number
    node_desired       = number
  })
}

variable "database" {
  description = "RDS database configuration."
  type = object({
    engine               = string
    engine_version       = string
    instance_class       = string
    allocated_storage_gb = number
    multi_az             = bool
  })
}

variable "load_balancer" {
  description = "Application load balancer configuration."
  type = object({
    type            = string
    internet_facing = bool
  })
}

variable "single_nat_gateway" {
  description = "true = one shared NAT gateway; false = one per AZ."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Common resource tags applied across all resources."
  type        = map(string)
  default     = {}
}

# --- Stack ------------------------------------------------------------------
module "stack" {
  source = "../.."

  project            = var.project
  region             = var.region
  environment        = var.environment
  network            = var.network
  kubernetes         = var.kubernetes
  database           = var.database
  load_balancer      = var.load_balancer
  single_nat_gateway = var.single_nat_gateway
  tags               = var.tags
}

# --- Pass-through outputs ----------------------------------------------------
output "vpc_id" {
  value = module.stack.vpc_id
}

output "public_subnet_ids" {
  value = module.stack.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.stack.private_subnet_ids
}

output "eks_cluster_name" {
  value = module.stack.eks_cluster_name
}

output "eks_cluster_endpoint" {
  value = module.stack.eks_cluster_endpoint
}

output "rds_endpoint" {
  value = module.stack.rds_endpoint
}

output "alb_dns_name" {
  value = module.stack.alb_dns_name
}
