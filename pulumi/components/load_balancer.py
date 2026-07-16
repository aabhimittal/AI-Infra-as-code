"""LoadBalancerComponent: an Application Load Balancer fronting the cluster.

Provisions:
  * a security group allowing inbound HTTP (80) and HTTPS (443)
  * an `aws.lb.LoadBalancer` (type "application") in the public subnets,
    internet-facing or internal per the infra spec
  * a target group (IP target type, suitable for routing to Kubernetes
    pod/service IPs registered by the AWS Load Balancer Controller)
  * an HTTP (port 80) listener forwarding to that target group

Note: this component intentionally ships only the HTTP listener by default.
A production deployment would typically add an HTTPS listener backed by an
ACM certificate and either redirect 80 -> 443 or terminate TLS here; wiring
in a certificate ARN is left to the caller/environment-specific config.
"""

from typing import List, Optional

import pulumi
import pulumi_aws as aws


class LoadBalancerComponent(pulumi.ComponentResource):
    """Application Load Balancer + target group + HTTP listener."""

    alb_dns_name: pulumi.Output[str]
    alb_arn: pulumi.Output[str]
    target_group_arn: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        *,
        vpc_id: pulumi.Input[str],
        public_subnet_ids: pulumi.Input[List[str]],
        internet_facing: bool,
        tags: Optional[dict] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("ai-infra:loadbalancer:LoadBalancerComponent", name, {}, opts)

        tags = tags or {}
        child_opts = pulumi.ResourceOptions(parent=self)

        # --- Security group: HTTP/HTTPS from the internet -----------------------
        alb_sg = aws.ec2.SecurityGroup(
            f"{name}-alb-sg",
            vpc_id=vpc_id,
            description="Allow inbound HTTP/HTTPS to the ALB",
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=80,
                    to_port=80,
                    cidr_blocks=["0.0.0.0/0"],
                    description="HTTP",
                ),
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=443,
                    to_port=443,
                    cidr_blocks=["0.0.0.0/0"],
                    description="HTTPS",
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                    description="Allow all outbound",
                )
            ],
            tags={**tags, "Name": f"{name}-alb-sg"},
            opts=child_opts,
        )

        # --- Application Load Balancer ------------------------------------------
        alb = aws.lb.LoadBalancer(
            f"{name}-alb",
            load_balancer_type="application",
            internal=not internet_facing,
            security_groups=[alb_sg.id],
            subnets=public_subnet_ids,
            enable_deletion_protection=False,
            tags={**tags, "Name": f"{name}-alb"},
            opts=child_opts,
        )

        # --- Target group (IP targets, for Kubernetes pod/service routing) -----
        target_group = aws.lb.TargetGroup(
            f"{name}-tg",
            port=80,
            protocol="HTTP",
            vpc_id=vpc_id,
            target_type="ip",
            health_check=aws.lb.TargetGroupHealthCheckArgs(
                path="/",
                protocol="HTTP",
                healthy_threshold=3,
                unhealthy_threshold=3,
                interval=30,
                timeout=5,
                matcher="200-399",
            ),
            tags={**tags, "Name": f"{name}-tg"},
            opts=child_opts,
        )

        # --- HTTP listener --------------------------------------------------
        listener = aws.lb.Listener(
            f"{name}-http-listener",
            load_balancer_arn=alb.arn,
            port=80,
            protocol="HTTP",
            default_actions=[
                aws.lb.ListenerDefaultActionArgs(
                    type="forward",
                    target_group_arn=target_group.arn,
                )
            ],
            opts=child_opts,
        )

        # --- Component outputs -------------------------------------------------
        self.alb_dns_name = alb.dns_name
        self.alb_arn = alb.arn
        self.target_group_arn = target_group.arn

        self.register_outputs(
            {
                "alb_dns_name": self.alb_dns_name,
                "alb_arn": self.alb_arn,
                "target_group_arn": self.target_group_arn,
            }
        )
