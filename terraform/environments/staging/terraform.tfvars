# =============================================================================
# Staging environment values - mid-sized instances, single NAT gateway,
# no Multi-AZ. Mirrors prod topology at a smaller scale for pre-prod testing.
# =============================================================================

project     = "myapp"
region      = "us-east-1"
environment = "staging"

network = {
  vpc_cidr = "10.1.0.0/16"
  az_count = 2
}

kubernetes = {
  version            = "1.29"
  node_instance_type = "m5.large"
  node_min           = 2
  node_max           = 4
  node_desired       = 2
}

database = {
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = "db.r6g.large"
  allocated_storage_gb = 50
  multi_az             = false
}

load_balancer = {
  type            = "application"
  internet_facing = true
}

# Single shared NAT gateway - staging doesn't need per-AZ resilience.
single_nat_gateway = true

tags = {
  Project     = "myapp"
  Environment = "staging"
  ManagedBy   = "terraform"
  Owner       = "platform-team"
}
