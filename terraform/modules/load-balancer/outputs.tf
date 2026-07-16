output "alb_dns_name" {
  description = "Public DNS name of the ALB."
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  description = "ARN of the ALB."
  value       = aws_lb.this.arn
}

output "alb_zone_id" {
  description = "Route53-compatible hosted zone ID of the ALB, for alias records."
  value       = aws_lb.this.zone_id
}

output "target_group_arn" {
  description = "ARN of the default target group."
  value       = aws_lb_target_group.default.arn
}

output "alb_security_group_id" {
  description = "ID of the security group attached to the ALB."
  value       = aws_security_group.alb.id
}
