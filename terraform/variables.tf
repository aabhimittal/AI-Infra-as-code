# =============================================================================
# Root input variables.
#
# These mirror the shared design contract exactly (see terraform/README.md):
# the same shape is emitted by the AI optimizer and consumed by the Pulumi
# implementation, so field names/types here MUST stay in sync with both.
# =============================================================================

variable "project" {
  description = "Short project/application name; used as a prefix for resource names (e.g. \"myapp\")."
  type        = string
}

variable "region" {
  description = "AWS region to deploy into (e.g. \"us-east-1\")."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "network" {
  description = "VPC networking configuration: CIDR block and number of AZs to span."
  type = object({
    vpc_cidr = string
    az_count = number
  })

  validation {
    condition     = contains([2, 3], var.network.az_count)
    error_message = "network.az_count must be 2 or 3."
  }
}

variable "kubernetes" {
  description = "EKS cluster version and managed node group sizing."
  type = object({
    version            = string
    node_instance_type = string
    node_min           = number
    node_max           = number
    node_desired       = number
  })
}

variable "database" {
  description = "RDS (PostgreSQL) engine, sizing, and availability configuration."
  type = object({
    engine               = string
    engine_version       = string
    instance_class       = string
    allocated_storage_gb = number
    multi_az             = bool
  })
}

variable "load_balancer" {
  description = "Application load balancer type and exposure configuration."
  type = object({
    type            = string
    internet_facing = bool
  })
}

variable "single_nat_gateway" {
  description = <<-EOT
    Optional override for the VPC's NAT gateway strategy:
      true  = a single shared NAT gateway (cheaper, single point of failure -
              suitable for dev/staging).
      false = one NAT gateway per AZ (higher cost, AZ-isolated failure domain
              - recommended for prod).
    Leave as null to auto-select based on `environment` (false for prod,
    true otherwise).
  EOT
  type    = bool
  default = null
}

variable "tags" {
  description = "Common resource tags merged into every resource created by this stack."
  type        = map(string)
  default     = {}
}
