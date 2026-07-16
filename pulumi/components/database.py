"""DatabaseComponent: an encrypted, backed-up RDS Postgres instance.

Provisions:
  * `aws.rds.SubnetGroup` spanning the VPC's private subnets
  * a security group that only allows Postgres (5432) traffic from inside
    the VPC CIDR
  * a random master password (`pulumi_random.RandomPassword`) that is never
    written to Pulumi state/config in plaintext by the caller and is
    persisted only in AWS Secrets Manager
  * `aws.rds.Instance` (engine="postgres") with storage encryption, backups,
    and optional Multi-AZ enabled per the infra spec
"""

import json
from typing import List, Optional

import pulumi
import pulumi_aws as aws
import pulumi_random as random


class DatabaseComponent(pulumi.ComponentResource):
    """RDS Postgres instance, private-subnet only, with a Secrets-Manager-backed password."""

    db_endpoint: pulumi.Output[str]
    db_instance_id: pulumi.Output[str]
    secret_arn: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        *,
        vpc_id: pulumi.Input[str],
        vpc_cidr: pulumi.Input[str],
        private_subnet_ids: pulumi.Input[List[str]],
        engine_version: str,
        instance_class: str,
        allocated_storage_gb: int,
        multi_az: bool,
        db_name: str = "appdb",
        master_username: str = "dbadmin",
        tags: Optional[dict] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("ai-infra:database:DatabaseComponent", name, {}, opts)

        tags = tags or {}
        child_opts = pulumi.ResourceOptions(parent=self)

        # --- DB subnet group (private subnets only) -----------------------------
        subnet_group = aws.rds.SubnetGroup(
            f"{name}-db-subnet-group",
            subnet_ids=private_subnet_ids,
            tags={**tags, "Name": f"{name}-db-subnet-group"},
            opts=child_opts,
        )

        # --- Security group: Postgres from inside the VPC only -----------------
        db_sg = aws.ec2.SecurityGroup(
            f"{name}-db-sg",
            vpc_id=vpc_id,
            description="Allow Postgres traffic from within the VPC only",
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=5432,
                    to_port=5432,
                    cidr_blocks=[vpc_cidr],
                    description="Postgres from VPC CIDR",
                )
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
            tags={**tags, "Name": f"{name}-db-sg"},
            opts=child_opts,
        )

        # --- Master password: generated, never hardcoded ------------------------
        # RandomPassword's result is stored in Pulumi state (which should itself
        # be encrypted at rest via a Pulumi secrets provider); the authoritative,
        # rotatable copy for application/runtime use lives in Secrets Manager.
        master_password = random.RandomPassword(
            f"{name}-db-password",
            length=32,
            special=True,
            # RDS disallows '/', '@', '"', and ' ' in passwords.
            override_special="!#$%^&*()-_=+[]{}<>:?",
            opts=child_opts,
        )

        secret = aws.secretsmanager.Secret(
            f"{name}-db-secret",
            name=f"{name}-db-credentials",
            description=f"RDS Postgres master credentials for {name}",
            tags=tags,
            opts=child_opts,
        )

        # --- RDS instance ---------------------------------------------------
        db_instance = aws.rds.Instance(
            f"{name}-db",
            engine="postgres",
            engine_version=engine_version,
            instance_class=instance_class,
            allocated_storage=allocated_storage_gb,
            storage_encrypted=True,
            db_name=db_name,
            username=master_username,
            password=master_password.result,
            db_subnet_group_name=subnet_group.name,
            vpc_security_group_ids=[db_sg.id],
            multi_az=multi_az,
            backup_retention_period=7,
            backup_window="03:00-04:00",
            maintenance_window="mon:04:30-mon:05:30",
            skip_final_snapshot=False,
            final_snapshot_identifier=f"{name}-db-final-snapshot",
            deletion_protection=True,
            copy_tags_to_snapshot=True,
            tags={**tags, "Name": f"{name}-db"},
            opts=child_opts,
        )

        # Persist the live endpoint/credentials as a single JSON secret version,
        # so consumers can fetch everything they need with one Secrets Manager
        # GetSecretValue call.
        secret_version = aws.secretsmanager.SecretVersion(
            f"{name}-db-secret-version",
            secret_id=secret.id,
            secret_string=pulumi.Output.json_dumps(
                {
                    "username": master_username,
                    "password": master_password.result,
                    "engine": "postgres",
                    "host": db_instance.address,
                    "port": db_instance.port,
                    "dbname": db_name,
                }
            ),
            opts=pulumi.ResourceOptions(parent=self, depends_on=[db_instance]),
        )

        # --- Component outputs -------------------------------------------------
        self.db_endpoint = db_instance.endpoint
        self.db_instance_id = db_instance.id
        self.secret_arn = secret.arn

        self.register_outputs(
            {
                "db_endpoint": self.db_endpoint,
                "db_instance_id": self.db_instance_id,
                "secret_arn": self.secret_arn,
            }
        )
