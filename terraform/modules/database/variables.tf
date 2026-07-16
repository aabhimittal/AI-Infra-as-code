variable "project" {
  description = "Short project/application name; used as a resource name prefix."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev|staging|prod)."
  type        = string
}

variable "engine" {
  description = "Database engine (contract currently only supports \"postgres\")."
  type        = string
  default     = "postgres"
}

variable "engine_version" {
  description = "Database engine version (e.g. \"15\")."
  type        = string
}

variable "instance_class" {
  description = "RDS instance class (e.g. \"db.r6g.large\")."
  type        = string
}

variable "allocated_storage_gb" {
  description = "Allocated storage for the RDS instance, in GB."
  type        = number
}

variable "multi_az" {
  description = "Whether to deploy a Multi-AZ standby replica for high availability."
  type        = bool
}

variable "vpc_id" {
  description = "ID of the VPC to deploy the database security group into."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC, used to scope the database security group's ingress rule."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs the RDS instance's subnet group spans."
  type        = list(string)
}

variable "db_name" {
  description = "Name of the default database created on the instance."
  type        = string
  default     = "appdb"
}

variable "db_username" {
  description = "Master username for the database."
  type        = string
  default     = "dbadmin"
}

variable "tags" {
  description = "Common resource tags to merge onto every resource in this module."
  type        = map(string)
  default     = {}
}
