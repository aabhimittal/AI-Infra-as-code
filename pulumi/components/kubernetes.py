"""EksComponent: a managed EKS cluster with a managed node group and IRSA.

Provisions:
  * IAM role for the EKS control plane (AmazonEKSClusterPolicy)
  * `aws.eks.Cluster` deployed into the private subnets of the VPC
  * IAM OIDC provider for the cluster, enabling IAM Roles for Service
    Accounts (IRSA)
  * IAM role for worker nodes (worker/CNI/ECR-read policies)
  * `aws.eks.NodeGroup` sized from kubernetes.node_min / node_max /
    node_desired, also placed in the private subnets
"""

import json
from typing import List, Optional

import pulumi
import pulumi_aws as aws

# AWS's IAM OIDC identity provider endpoints are all served behind the same
# well-known root CA (Amazon Root CA 1 / Starfield Services Root CA), so the
# SHA-1 thumbprint below is stable across every EKS cluster and region. This
# is the same constant widely used by the terraform-aws-modules/eks module,
# and avoids pulling in an extra `pulumi_tls` provider dependency just to
# recompute it at apply time.
_EKS_OIDC_ROOT_CA_THUMBPRINT = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"


class EksComponent(pulumi.ComponentResource):
    """A managed EKS cluster + managed node group inside private subnets."""

    cluster_name: pulumi.Output[str]
    cluster_endpoint: pulumi.Output[str]
    cluster_certificate_authority: pulumi.Output[str]
    oidc_provider_arn: pulumi.Output[str]

    def __init__(
        self,
        name: str,
        *,
        cluster_name: str,
        kubernetes_version: str,
        vpc_id: pulumi.Input[str],
        private_subnet_ids: pulumi.Input[List[str]],
        node_instance_type: str,
        node_min: int,
        node_max: int,
        node_desired: int,
        tags: Optional[dict] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("ai-infra:kubernetes:EksComponent", name, {}, opts)

        tags = tags or {}
        child_opts = pulumi.ResourceOptions(parent=self)

        # --- Control plane IAM role -----------------------------------------
        cluster_role = aws.iam.Role(
            f"{name}-cluster-role",
            assume_role_policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "eks.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
            tags=tags,
            opts=child_opts,
        )
        aws.iam.RolePolicyAttachment(
            f"{name}-cluster-policy",
            role=cluster_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            opts=child_opts,
        )

        # --- EKS control plane -------------------------------------------------
        cluster = aws.eks.Cluster(
            f"{name}-cluster",
            name=cluster_name,
            role_arn=cluster_role.arn,
            version=kubernetes_version,
            vpc_config=aws.eks.ClusterVpcConfigArgs(
                subnet_ids=private_subnet_ids,
                endpoint_private_access=True,
                endpoint_public_access=True,
            ),
            tags=tags,
            opts=pulumi.ResourceOptions(
                parent=self,
                # Ensure the policy is attached before the API attempts to
                # assume the role while bootstrapping the cluster.
                depends_on=[cluster_role],
            ),
        )

        # --- IAM OIDC provider (enables IRSA) -----------------------------------
        oidc_provider = aws.iam.OpenIdConnectProvider(
            f"{name}-oidc",
            url=cluster.identities[0].oidcs[0].issuer,
            client_id_lists=["sts.amazonaws.com"],
            thumbprint_lists=[_EKS_OIDC_ROOT_CA_THUMBPRINT],
            tags=tags,
            opts=child_opts,
        )

        # --- Worker node IAM role ------------------------------------------
        node_role = aws.iam.Role(
            f"{name}-node-role",
            assume_role_policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ec2.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
            tags=tags,
            opts=child_opts,
        )
        for policy_arn in (
            "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
        ):
            aws.iam.RolePolicyAttachment(
                f"{name}-node-policy-{policy_arn.rsplit('/', 1)[-1]}",
                role=node_role.name,
                policy_arn=policy_arn,
                opts=child_opts,
            )

        # --- Managed node group --------------------------------------------
        node_group = aws.eks.NodeGroup(
            f"{name}-node-group",
            cluster_name=cluster.name,
            node_role_arn=node_role.arn,
            subnet_ids=private_subnet_ids,
            instance_types=[node_instance_type],
            scaling_config=aws.eks.NodeGroupScalingConfigArgs(
                min_size=node_min,
                max_size=node_max,
                desired_size=node_desired,
            ),
            # Roll nodes out one at a time to avoid capacity dips during
            # updates; tune per environment if faster rollout is desired.
            update_config=aws.eks.NodeGroupUpdateConfigArgs(max_unavailable=1),
            tags=tags,
            opts=pulumi.ResourceOptions(
                parent=self,
                depends_on=[node_role],
            ),
        )

        # --- Component outputs -------------------------------------------------
        self.cluster_name = cluster.name
        self.cluster_endpoint = cluster.endpoint
        self.cluster_certificate_authority = cluster.certificate_authority.data
        self.oidc_provider_arn = oidc_provider.arn

        self.register_outputs(
            {
                "cluster_name": self.cluster_name,
                "cluster_endpoint": self.cluster_endpoint,
                "oidc_provider_arn": self.oidc_provider_arn,
            }
        )
