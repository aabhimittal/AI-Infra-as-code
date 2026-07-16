variable "project" {
  description = "Short project/application name; used as a resource name prefix."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev|staging|prod)."
  type        = string
}

variable "lb_type" {
  description = "Load balancer type (contract currently only supports \"application\")."
  type        = string
  default     = "application"
}

variable "internet_facing" {
  description = "Whether the load balancer is internet-facing (true) or internal (false)."
  type        = bool
  default     = true
}

variable "vpc_id" {
  description = "ID of the VPC to deploy the load balancer and its security group into."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs the load balancer is deployed into."
  type        = list(string)
}

variable "tags" {
  description = "Common resource tags to merge onto every resource in this module."
  type        = map(string)
  default     = {}
}
