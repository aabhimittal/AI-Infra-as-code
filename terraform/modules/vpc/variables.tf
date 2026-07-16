variable "project" {
  description = "Short project/application name; used as a resource name prefix."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev|staging|prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC (e.g. \"10.0.0.0/16\")."
  type        = string
}

variable "az_count" {
  description = "Number of availability zones to spread public/private subnets across (2 or 3)."
  type        = number

  validation {
    condition     = contains([2, 3], var.az_count)
    error_message = "az_count must be 2 or 3."
  }
}

variable "single_nat_gateway" {
  description = "If true, create one shared NAT gateway; if false, create one NAT gateway per AZ."
  type        = bool
  default     = true
}

variable "cluster_name" {
  description = "EKS cluster name used to tag subnets with kubernetes.io/cluster/<name>=shared so the AWS load balancer controller can discover them."
  type        = string
}

variable "tags" {
  description = "Common resource tags to merge onto every resource in this module."
  type        = map(string)
  default     = {}
}
