"""End-to-end and unit tests for the optimizer (stdlib unittest, no deps)."""

import unittest

from aiopt.capacity_model import check, is_feasible
from aiopt.cost_model import monthly_cost
from aiopt.optimizer import Optimizer
from aiopt.recommender import KNNRecommender, HistoryRecord
from aiopt.genetic import Genome
from aiopt.spec import (
    DatabaseSpec,
    InfraSpec,
    KubernetesSpec,
    NetworkSpec,
    WorkloadSpec,
)


def _tiny_infra(**over):
    base = dict(
        project="t",
        kubernetes=KubernetesSpec(node_instance_type="t3.medium", node_desired=1,
                                  node_min=1, node_max=4),
        database=DatabaseSpec(instance_class="db.t3.medium", allocated_storage_gb=20),
        network=NetworkSpec(az_count=2, single_nat_gateway=True),
    )
    base.update(over)
    return InfraSpec(**base)


class TestCostModel(unittest.TestCase):
    def test_cost_is_positive_and_monotone_in_nodes(self):
        small = _tiny_infra(kubernetes=KubernetesSpec(
            node_instance_type="m5.large", node_desired=2, node_min=2, node_max=6))
        big = _tiny_infra(kubernetes=KubernetesSpec(
            node_instance_type="m5.large", node_desired=5, node_min=2, node_max=6))
        self.assertGreater(monthly_cost(small), 0)
        self.assertGreater(monthly_cost(big), monthly_cost(small))

    def test_multi_az_costs_more(self):
        single = _tiny_infra(database=DatabaseSpec(
            instance_class="db.r6g.large", allocated_storage_gb=100, multi_az=False))
        multi = _tiny_infra(database=DatabaseSpec(
            instance_class="db.r6g.large", allocated_storage_gb=100, multi_az=True))
        self.assertGreater(monthly_cost(multi), monthly_cost(single))


class TestCapacityModel(unittest.TestCase):
    def test_undersized_cluster_is_infeasible(self):
        w = WorkloadSpec(project="t", peak_rps=5000, replicas=50)
        infra = _tiny_infra()
        self.assertFalse(is_feasible(infra, w))
        self.assertTrue(any(v.check == "compute_throughput" for v in check(infra, w)))

    def test_prod_requires_multi_az(self):
        w = WorkloadSpec(project="t", environment="prod", peak_rps=10, replicas=1)
        infra = _tiny_infra(database=DatabaseSpec(
            instance_class="db.t3.medium", allocated_storage_gb=500, multi_az=False))
        checks = {v.check for v in check(infra, w)}
        self.assertIn("ha_database", checks)


class TestRecommender(unittest.TestCase):
    def test_knn_returns_nearest_configs(self):
        records = [
            HistoryRecord(WorkloadSpec(project="a", peak_rps=10, replicas=1),
                          Genome("t3.medium", 2, "db.t3.medium", 20)),
            HistoryRecord(WorkloadSpec(project="b", peak_rps=2000, replicas=30),
                          Genome("m5.2xlarge", 5, "db.r6g.2xlarge", 800)),
        ]
        rec = KNNRecommender(records, k=1)
        seeds = rec.recommend(WorkloadSpec(project="c", peak_rps=15, replicas=2))
        self.assertEqual(seeds[0].node_instance_type, "t3.medium")


class TestOptimizerEndToEnd(unittest.TestCase):
    def test_dev_workload_is_feasible_and_cheap(self):
        w = WorkloadSpec(project="myapp", environment="dev", peak_rps=60,
                         replicas=3, db_connections=40, data_size_gb=15)
        result = Optimizer(recommender=None, generations=40).optimize(w)
        self.assertTrue(result.feasible, result.violations)
        self.assertFalse(result.infra.database.multi_az)

    def test_prod_workload_enforces_ha(self):
        w = WorkloadSpec(project="myapp", environment="prod", peak_rps=900,
                         replicas=10, db_connections=250, data_size_gb=180,
                         data_growth_gb_yr=120)
        result = Optimizer(recommender=None, generations=60).optimize(w)
        self.assertTrue(result.feasible, result.violations)
        self.assertTrue(result.infra.database.multi_az)
        self.assertEqual(result.infra.network.az_count, 3)
        self.assertGreaterEqual(result.infra.kubernetes.node_desired, 3)

    def test_result_is_deterministic_with_seed(self):
        w = WorkloadSpec(project="myapp", environment="staging", peak_rps=300,
                         replicas=6, db_connections=120, data_size_gb=80)
        a = Optimizer(recommender=None, seed=7, generations=30).optimize(w)
        b = Optimizer(recommender=None, seed=7, generations=30).optimize(w)
        self.assertEqual(a.infra.to_dict(), b.infra.to_dict())


if __name__ == "__main__":
    unittest.main()
