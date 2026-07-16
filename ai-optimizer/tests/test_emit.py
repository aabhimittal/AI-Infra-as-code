"""Tests that the emitted artifacts contain the expected keys/values."""

import unittest

from aiopt import emit
from aiopt.spec import (
    DatabaseSpec,
    InfraSpec,
    KubernetesSpec,
    LoadBalancerSpec,
    NetworkSpec,
)


def _infra():
    return InfraSpec(
        project="myapp",
        region="us-east-1",
        environment="prod",
        network=NetworkSpec(vpc_cidr="10.0.0.0/16", az_count=3, single_nat_gateway=False),
        kubernetes=KubernetesSpec(node_instance_type="m5.large", node_desired=3,
                                  node_min=3, node_max=10),
        database=DatabaseSpec(instance_class="db.r6g.large",
                              allocated_storage_gb=200, multi_az=True),
        load_balancer=LoadBalancerSpec(internet_facing=True),
        tags={"managed-by": "ai-infra-as-code"},
    )


class TestEmit(unittest.TestCase):
    def test_tfvars_has_nested_blocks(self):
        out = emit.to_terraform_tfvars(_infra())
        # nested objects matching terraform/variables.tf
        self.assertIn("kubernetes = {", out)
        self.assertIn('node_instance_type = "m5.large"', out)
        self.assertIn("multi_az             = true", out)
        self.assertIn("az_count = 3", out)
        # single_nat_gateway is a top-level var, not nested in network
        self.assertIn("single_nat_gateway = false", out)
        # tag keys with hyphens must be quoted to be valid HCL
        self.assertIn('"managed-by" = "ai-infra-as-code"', out)

    def test_pulumi_config_structured(self):
        out = emit.to_pulumi_config(_infra(), stack="prod")
        self.assertIn("ai-infra-as-code:network:", out)
        self.assertIn("ai-infra-as-code:kubernetes:", out)
        self.assertIn("node_instance_type: m5.large", out)
        self.assertIn("aws:region: us-east-1", out)
        # single_nat_gateway is nested under network for Pulumi
        self.assertIn("single_nat_gateway: false", out)
        # version-like values stay quoted strings
        self.assertIn('version: "1.29"', out)

    def test_json_round_trips(self):
        import json
        out = emit.to_json(_infra())
        data = json.loads(out)
        self.assertEqual(data["kubernetes"]["node_instance_type"], "m5.large")


if __name__ == "__main__":
    unittest.main()
