# =============================================================================
# VPC module: creates a VPC spanning `az_count` availability zones, with one
# public and one private subnet per AZ, an internet gateway for public
# egress, and NAT gateway(s) for private subnet egress (either a single
# shared NAT gateway or one per AZ, controlled by `single_nat_gateway`).
# =============================================================================

# Discover the AZs available in the target region so we don't hardcode names.
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project}-${var.environment}"

  # Take exactly az_count AZs, in a stable (alphabetical) order.
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # How many NAT gateways/EIPs to provision.
  nat_gateway_count = var.single_nat_gateway ? 1 : var.az_count
}

# -----------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true # required for EKS/RDS private DNS resolution
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-igw"
  })
}

# -----------------------------------------------------------------------
# Subnets
# -----------------------------------------------------------------------

# Public subnets - one /24 per AZ, carved from the low end of the VPC CIDR.
# Tagged so the AWS Load Balancer Controller can auto-discover them for
# internet-facing ALBs/NLBs (kubernetes.io/role/elb=1).
resource "aws_subnet" "public" {
  count = var.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name                                        = "${local.name_prefix}-public-${local.azs[count.index]}"
    "kubernetes.io/role/elb"                    = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  })
}

# Private subnets - one /24 per AZ, offset by +100 to avoid overlapping the
# public subnet CIDR range. Tagged for internal (private) ELB discovery and
# used to host EKS worker nodes and the RDS instance.
resource "aws_subnet" "private" {
  count = var.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = local.azs[count.index]

  tags = merge(var.tags, {
    Name                                        = "${local.name_prefix}-private-${local.azs[count.index]}"
    "kubernetes.io/role/internal-elb"           = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  })
}

# -----------------------------------------------------------------------
# NAT gateways (egress for private subnets)
# -----------------------------------------------------------------------

# One Elastic IP per NAT gateway.
resource "aws_eip" "nat" {
  count = local.nat_gateway_count

  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-nat-eip-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

# NAT gateways live in the public subnets; each private route table below
# points at one of these (either all sharing index 0, or 1:1 with its AZ).
resource "aws_nat_gateway" "this" {
  count = local.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-nat-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

# -----------------------------------------------------------------------
# Route tables
# -----------------------------------------------------------------------

# Single public route table shared by all public subnets, routing 0.0.0.0/0
# to the internet gateway.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = var.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table per AZ. When single_nat_gateway = true, every
# table's default route points at the one shared NAT gateway; when false,
# each AZ's table points at its own NAT gateway, keeping traffic (and
# failure domains) AZ-local.
resource "aws_route_table" "private" {
  count = var.az_count

  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-private-rt-${local.azs[count.index]}"
  })
}

resource "aws_route" "private_nat" {
  count = var.az_count

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = var.single_nat_gateway ? aws_nat_gateway.this[0].id : aws_nat_gateway.this[count.index].id
}

resource "aws_route_table_association" "private" {
  count = var.az_count

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
