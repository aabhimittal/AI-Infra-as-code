# =============================================================================
# Load balancer module: an application load balancer (ALB) in the public
# subnets fronting the EKS workloads, with a default target group and an
# HTTP listener. In production, add an HTTPS listener (ACM cert) and have it
# forward to this same target group / redirect HTTP -> HTTPS.
# =============================================================================

locals {
  name_prefix = "${var.project}-${var.environment}"
}

# -----------------------------------------------------------------------
# Security group - open to the world on 80/443 since this is the public
# edge of the stack; anything more restrictive belongs at the WAF / target
# group level.
# -----------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name_prefix = "${local.name_prefix}-alb-"
  vpc_id      = var.vpc_id
  description = "Allow HTTP/HTTPS ingress to the ALB"

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name_prefix}-alb-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------
# Application load balancer
# -----------------------------------------------------------------------
resource "aws_lb" "this" {
  name               = "${local.name_prefix}-alb"
  internal           = !var.internet_facing
  load_balancer_type = var.lb_type
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  # Guard prod ALBs against accidental deletion.
  enable_deletion_protection = var.environment == "prod"

  tags = merge(var.tags, { Name = "${local.name_prefix}-alb" })
}

# Default target group. Uses "ip" targets, which is the target type expected
# by the AWS Load Balancer Controller when running on EKS (pods are
# registered directly rather than via instance/ASG registration).
resource "aws_lb_target_group" "default" {
  name        = "${local.name_prefix}-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/healthz"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }

  tags = var.tags
}

# HTTP listener forwarding to the default target group. Add a second HTTPS
# (443) listener with an ACM certificate once a domain/cert is available.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default.arn
  }
}
