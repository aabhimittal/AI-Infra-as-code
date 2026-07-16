output "db_endpoint" {
  description = "Connection endpoint (host:port) of the RDS instance."
  value       = aws_db_instance.this.endpoint
}

output "db_address" {
  description = "Hostname (without port) of the RDS instance."
  value       = aws_db_instance.this.address
}

output "db_instance_id" {
  description = "Identifier of the RDS instance."
  value       = aws_db_instance.this.id
}

output "db_security_group_id" {
  description = "ID of the security group attached to the RDS instance."
  value       = aws_security_group.db.id
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the master credentials."
  value       = aws_secretsmanager_secret.db_credentials.arn
}
