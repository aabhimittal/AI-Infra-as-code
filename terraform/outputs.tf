# =============================================================================
# Root module outputs - re-exported by each environments/<env>/main.tf so
# they surface at `terraform output` time for the actual applied root.
# =============================================================================

output "vpc_id" {
  description = "ID of the VPC created for this stack."
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (one per AZ), used by the ALB."
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (one per AZ), used by EKS nodes and RDS."
  value       = module.vpc.private_subnet_ids
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.kubernetes.cluster_name
}

output "eks_cluster_endpoint" {
  description = "API server endpoint of the EKS cluster."
  value       = module.kubernetes.cluster_endpoint
}

output "rds_endpoint" {
  description = "Connection endpoint (host:port) of the RDS PostgreSQL instance."
  value       = module.database.db_endpoint
}

output "alb_dns_name" {
  description = "Public DNS name of the application load balancer."
  value       = module.load_balancer.alb_dns_name
}
