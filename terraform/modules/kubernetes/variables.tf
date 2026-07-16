variable "project" {
  description = "Short project/application name; used as a resource name prefix."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev|staging|prod)."
  type        = string
}

variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS control plane (e.g. \"1.29\")."
  type        = string
}

variable "node_instance_type" {
  description = "EC2 instance type for the managed node group (e.g. \"m5.large\")."
  type        = string
}

variable "node_min" {
  description = "Minimum number of worker nodes in the managed node group."
  type        = number
}

variable "node_max" {
  description = "Maximum number of worker nodes in the managed node group."
  type        = number
}

variable "node_desired" {
  description = "Desired number of worker nodes in the managed node group."
  type        = number
}

variable "vpc_id" {
  description = "ID of the VPC to deploy the cluster's security group into."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs the EKS control plane ENIs and worker nodes are deployed into."
  type        = list(string)
}

variable "tags" {
  description = "Common resource tags to merge onto every resource in this module."
  type        = map(string)
  default     = {}
}
