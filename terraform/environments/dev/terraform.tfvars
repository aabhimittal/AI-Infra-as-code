# =============================================================================
# Dev environment values - small/cheap instances, single NAT gateway,
# no Multi-AZ. Optimized for cost over resilience.
# =============================================================================

project     = "myapp"
region      = "us-east-1"
environment = "dev"

network = {
  vpc_cidr = "10.0.0.0/16"
  az_count = 2
}

kubernetes = {
  version            = "1.29"
  node_instance_type = "t3.medium"
  node_min           = 1
  node_max           = 3
  node_desired       = 2
}

database = {
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = "db.t3.medium"
  allocated_storage_gb = 20
  multi_az             = false
}

load_balancer = {
  type            = "application"
  internet_facing = true
}

# Single shared NAT gateway - cheaper, acceptable risk for dev.
single_nat_gateway = true

tags = {
  Project     = "myapp"
  Environment = "dev"
  ManagedBy   = "terraform"
  Owner       = "platform-team"
}
