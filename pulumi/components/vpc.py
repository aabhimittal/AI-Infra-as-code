"""VpcComponent: the network foundation shared by EKS, RDS, and the ALB.

Creates a VPC with `az_count` public and `az_count` private subnets, an
Internet Gateway, NAT Gateway(s) (a single shared NAT for cost-sensitive
stacks such as dev, or one per AZ for high-availability stacks such as
prod), and the route tables that wire it all together.

Subnets are tagged per the AWS/EKS convention so that the Kubernetes AWS
cloud-controller and the AWS Load Balancer Controller can auto-discover
them:
  * public subnets:  kubernetes.io/role/elb = 1
  * private subnets: kubernetes.io/role/internal-elb = 1
  * both:            kubernetes.io/cluster/<cluster_name> = shared
"""

import ipaddress
from typing import List, Optional

import pulumi
import pulumi_aws as aws


def _subnet_cidrs(vpc_cidr: str, count: int) -> List[str]:
    """Carve `count` non-overlapping subnet CIDRs out of `vpc_cidr`.

    Chooses the smallest subnet prefix that comfortably yields at least
    `count` blocks (with headroom), which keeps subnets reasonably sized
    regardless of the parent VPC CIDR width.
    """
    network = ipaddress.ip_network(vpc_cidr)
    new_prefix = network.prefixlen + 1
    # Grow the prefix (shrink each subnet) until splitting the VPC CIDR at
    # that prefix yields at least `count` blocks.
    while new_prefix <= 28:
        num_subnets = 2 ** (new_prefix - network.prefixlen)
        if num_subnets >= count:
            break
        new_prefix += 1
    else:
        raise ValueError(f"vpc_cidr {vpc_cidr} is too small to carve {count} subnets")

    subnets = list(network.subnets(new_prefix=new_prefix))
    return [str(s) for s in subnets[:count]]


class VpcComponent(pulumi.ComponentResource):
    """A VPC with public/private subnets across `az_count` availability zones."""

    vpc_id: pulumi.Output[str]
    vpc_cidr: pulumi.Output[str]
    public_subnet_ids: pulumi.Output[List[str]]
    private_subnet_ids: pulumi.Output[List[str]]

    def __init__(
        self,
        name: str,
        *,
        vpc_cidr: str,
        az_count: int,
        single_nat_gateway: bool,
        cluster_name: str,
        tags: Optional[dict] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("ai-infra:network:VpcComponent", name, {}, opts)

        tags = tags or {}
        child_opts = pulumi.ResourceOptions(parent=self)

        # --- Availability zones ------------------------------------------------
        # `parent=self` lets the invoke inherit the region-specific AWS
        # provider registered on this component (see __main__.py), so the
        # AZ list always matches spec.region even if the ambient
        # AWS_REGION/profile differs.
        azs = aws.get_availability_zones(
            state="available", opts=pulumi.InvokeOptions(parent=self)
        )
        selected_azs = azs.names[:az_count]

        # --- VPC -----------------------------------------------------------------
        vpc = aws.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=vpc_cidr,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            tags={**tags, "Name": f"{name}-vpc"},
            opts=child_opts,
        )

        igw = aws.ec2.InternetGateway(
            f"{name}-igw",
            vpc_id=vpc.id,
            tags={**tags, "Name": f"{name}-igw"},
            opts=child_opts,
        )

        # --- Subnet CIDR allocation ------------------------------------------
        # First half of the carved blocks -> public, second half -> private.
        all_cidrs = _subnet_cidrs(vpc_cidr, az_count * 2)
        public_cidrs = all_cidrs[:az_count]
        private_cidrs = all_cidrs[az_count:]

        public_subnets: List[aws.ec2.Subnet] = []
        private_subnets: List[aws.ec2.Subnet] = []

        for i, az in enumerate(selected_azs):
            public_subnet = aws.ec2.Subnet(
                f"{name}-public-{i}",
                vpc_id=vpc.id,
                cidr_block=public_cidrs[i],
                availability_zone=az,
                map_public_ip_on_launch=True,
                tags={
                    **tags,
                    "Name": f"{name}-public-{i}",
                    "kubernetes.io/role/elb": "1",
                    f"kubernetes.io/cluster/{cluster_name}": "shared",
                },
                opts=child_opts,
            )
            public_subnets.append(public_subnet)

            private_subnet = aws.ec2.Subnet(
                f"{name}-private-{i}",
                vpc_id=vpc.id,
                cidr_block=private_cidrs[i],
                availability_zone=az,
                map_public_ip_on_launch=False,
                tags={
                    **tags,
                    "Name": f"{name}-private-{i}",
                    "kubernetes.io/role/internal-elb": "1",
                    f"kubernetes.io/cluster/{cluster_name}": "shared",
                },
                opts=child_opts,
            )
            private_subnets.append(private_subnet)

        # --- Public routing (single route table, shared by all public subnets) --
        public_rt = aws.ec2.RouteTable(
            f"{name}-public-rt",
            vpc_id=vpc.id,
            routes=[
                aws.ec2.RouteTableRouteArgs(
                    cidr_block="0.0.0.0/0",
                    gateway_id=igw.id,
                )
            ],
            tags={**tags, "Name": f"{name}-public-rt"},
            opts=child_opts,
        )
        for i, subnet in enumerate(public_subnets):
            aws.ec2.RouteTableAssociation(
                f"{name}-public-rta-{i}",
                subnet_id=subnet.id,
                route_table_id=public_rt.id,
                opts=child_opts,
            )

        # --- NAT gateway(s) --------------------------------------------------
        # Dev/staging: a single NAT gateway shared by every private subnet to
        # minimize cost. Prod: one NAT gateway per AZ for high availability
        # (a lost AZ shouldn't cut off outbound access for the others).
        nat_count = 1 if single_nat_gateway else az_count
        nat_gateways: List[aws.ec2.NatGateway] = []
        for i in range(nat_count):
            eip = aws.ec2.Eip(
                f"{name}-nat-eip-{i}",
                domain="vpc",
                tags={**tags, "Name": f"{name}-nat-eip-{i}"},
                opts=child_opts,
            )
            nat_gw = aws.ec2.NatGateway(
                f"{name}-nat-{i}",
                allocation_id=eip.id,
                subnet_id=public_subnets[i].id,
                tags={**tags, "Name": f"{name}-nat-{i}"},
                # NAT gateways must be created after the IGW is attached/routable.
                opts=pulumi.ResourceOptions(parent=self, depends_on=[igw]),
            )
            nat_gateways.append(nat_gw)

        # --- Private routing (one route table per private subnet, pointing at
        # the NAT gateway in the same AZ, or the single shared NAT) -----------
        for i, subnet in enumerate(private_subnets):
            nat_gw = nat_gateways[i] if not single_nat_gateway else nat_gateways[0]
            private_rt = aws.ec2.RouteTable(
                f"{name}-private-rt-{i}",
                vpc_id=vpc.id,
                routes=[
                    aws.ec2.RouteTableRouteArgs(
                        cidr_block="0.0.0.0/0",
                        nat_gateway_id=nat_gw.id,
                    )
                ],
                tags={**tags, "Name": f"{name}-private-rt-{i}"},
                opts=child_opts,
            )
            aws.ec2.RouteTableAssociation(
                f"{name}-private-rta-{i}",
                subnet_id=subnet.id,
                route_table_id=private_rt.id,
                opts=child_opts,
            )

        # --- Component outputs -------------------------------------------------
        self.vpc_id = vpc.id
        self.vpc_cidr = vpc.cidr_block
        self.public_subnet_ids = pulumi.Output.all(*[s.id for s in public_subnets])
        self.private_subnet_ids = pulumi.Output.all(*[s.id for s in private_subnets])

        self.register_outputs(
            {
                "vpc_id": self.vpc_id,
                "vpc_cidr": self.vpc_cidr,
                "public_subnet_ids": self.public_subnet_ids,
                "private_subnet_ids": self.private_subnet_ids,
            }
        )
