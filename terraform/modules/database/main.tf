# =============================================================================
# Database module: a PostgreSQL RDS instance deployed across the private
# subnets, reachable only from within the VPC, with a randomly generated
# master password stored in Secrets Manager (never hardcoded, never plumbed
# through plain outputs).
# =============================================================================

# This module directly uses the `random` provider to generate the master
# password, in addition to `aws`.
terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}

locals {
  name_prefix = "${var.project}-${var.environment}"
}

# -----------------------------------------------------------------------
# Subnet group - spans the private subnets so the instance has no public IP
# and no route to the internet gateway.
# -----------------------------------------------------------------------
resource "aws_db_subnet_group" "this" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${local.name_prefix}-db-subnet-group" })
}

# -----------------------------------------------------------------------
# Security group - only allow Postgres (5432) from within the VPC CIDR
# (i.e. the EKS nodes / application tier), nothing from the public internet.
# -----------------------------------------------------------------------
resource "aws_security_group" "db" {
  name_prefix = "${local.name_prefix}-db-"
  vpc_id      = var.vpc_id
  description = "Allow Postgres access from within the VPC only"

  ingress {
    description = "Postgres from within the VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${local.name_prefix}-db-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------
# Master password - generated randomly at apply time and never hardcoded.
# It only ever lands in Terraform state (as all resource attributes do) and
# in Secrets Manager; applications should read it from Secrets Manager at
# runtime rather than from Terraform outputs.
# -----------------------------------------------------------------------
resource "random_password" "master" {
  length  = 32
  special = true
  # RDS disallows '/', '@', '"', and ' ' in passwords - restrict to a safe set.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Store the master credentials in Secrets Manager so applications and
# operators retrieve them via IAM rather than reading Terraform state/output.
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${local.name_prefix}-db-credentials"
  description = "Master credentials for the ${local.name_prefix} RDS instance"

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id

  secret_string = jsonencode({
    username = var.db_username
    password = random_password.master.result
    engine   = var.engine
    dbname   = var.db_name
    port     = 5432
    host     = aws_db_instance.this.address
  })
}

# -----------------------------------------------------------------------
# RDS PostgreSQL instance
# -----------------------------------------------------------------------
resource "aws_db_instance" "this" {
  identifier     = "${local.name_prefix}-db"
  engine         = var.engine
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage_gb
  storage_type       = "gp3"
  storage_encrypted  = true # encrypt data at rest with the default KMS key

  db_name  = var.db_name
  username = var.db_username
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  multi_az                = var.multi_az

  # Automated backups: 7-day retention with a nightly backup window ahead
  # of the weekly maintenance window.
  backup_retention_period = 7
  backup_window             = "03:00-04:00"
  maintenance_window        = "mon:04:30-mon:05:30"

  # Protect prod from accidental deletion; keep dev/staging easy to tear down.
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name_prefix}-db-final" : null

  tags = merge(var.tags, { Name = "${local.name_prefix}-db" })
}
