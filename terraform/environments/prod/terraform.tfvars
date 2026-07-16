# =============================================================================
# Prod environment values - larger instances, per-AZ NAT gateways, Multi-AZ
# database. Optimized for resilience and availability over cost.
# =============================================================================

project     = "myapp"
region      = "us-east-1"
environment = "prod"

network = {
  vpc_cidr = "10.2.0.0/16"
  az_count = 3
}

kubernetes = {
  version             = "1.29"
  node_instance_type  = "m5.xlarge"
  node_min            = 3
  node_max            = 8
  node_desired        = 3
}

database = {
  engine                = "postgres"
  engine_version        = "15"
  instance_class        = "db.r6g.xlarge"
  allocated_storage_gb  = 100
  multi_az              = true
}

load_balancer = {
  type            = "application"
  internet_facing = true
}

# One NAT gateway per AZ - keeps egress traffic AZ-local and survives a
# single AZ's NAT gateway failing.
single_nat_gateway = false

tags = {
  Project     = "myapp"
  Environment = "prod"
  ManagedBy   = "terraform"
  Owner       = "platform-team"
}
