"""k-Nearest-Neighbors recommender that learns from past deployments.

The optimizer does not start its search cold. Given a library of historical
``(workload -> chosen infra)`` records, this recommender finds the workloads
most similar to the new one and returns their infra choices as *seed genomes*
for the genetic algorithm. This is the "learns from data" component: as the
history file grows with real deployments, recommendations improve, and the GA
converges faster because it starts near known-good configurations.

Distance is Euclidean over min-max-normalized workload features, so no external
ML dependency is required; the same interface can be backed by a trained model
later without changing callers.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .genetic import Genome
from .spec import WorkloadSpec

# Workload features used for similarity (log-scaled where they span orders of
# magnitude so a 10x traffic difference is treated proportionally).
_FEATURES = [
    "peak_rps",
    "replicas",
    "avg_pod_mem_mib",
    "db_connections",
    "data_size_gb",
]


def _feature_vector(w: WorkloadSpec) -> List[float]:
    return [
        math.log1p(w.peak_rps),
        math.log1p(w.replicas),
        math.log1p(w.avg_pod_mem_mib),
        math.log1p(w.db_connections),
        math.log1p(w.data_size_gb),
    ]


@dataclass
class HistoryRecord:
    workload: WorkloadSpec
    genome: Genome


class KNNRecommender:
    def __init__(self, records: List[HistoryRecord], k: int = 3) -> None:
        self.records = records
        self.k = k
        self._ranges = self._compute_ranges()

    # --- loading ---------------------------------------------------------- #
    @classmethod
    def from_file(cls, path: str | Path, k: int = 3) -> "KNNRecommender":
        data = json.loads(Path(path).read_text())
        records = [
            HistoryRecord(
                workload=WorkloadSpec.from_dict(item["workload"]),
                genome=Genome(**item["infra"]),
            )
            for item in data
        ]
        return cls(records, k=k)

    # --- normalization ---------------------------------------------------- #
    def _compute_ranges(self) -> List[tuple]:
        if not self.records:
            return [(0.0, 1.0)] * len(_FEATURES)
        vectors = [_feature_vector(r.workload) for r in self.records]
        ranges = []
        for i in range(len(_FEATURES)):
            col = [v[i] for v in vectors]
            lo, hi = min(col), max(col)
            ranges.append((lo, hi if hi > lo else lo + 1.0))
        return ranges

    def _normalize(self, vec: List[float]) -> List[float]:
        return [
            (vec[i] - lo) / (hi - lo)
            for i, (lo, hi) in enumerate(self._ranges)
        ]

    def _distance(self, a: List[float], b: List[float]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    # --- recommendation --------------------------------------------------- #
    def recommend(self, workload: WorkloadSpec) -> List[Genome]:
        """Return up to ``k`` seed genomes from the most similar past workloads."""
        if not self.records:
            return []
        target = self._normalize(_feature_vector(workload))
        scored = [
            (self._distance(target, self._normalize(_feature_vector(r.workload))), r)
            for r in self.records
        ]
        scored.sort(key=lambda t: t[0])
        return [r.genome for _, r in scored[: self.k]]

    def is_empty(self) -> bool:
        return len(self.records) == 0


def load_default_history(k: int = 3) -> Optional[KNNRecommender]:
    """Load the bundled ``data/history.json`` if present."""
    path = Path(__file__).resolve().parent.parent / "data" / "history.json"
    if path.exists():
        return KNNRecommender.from_file(path, k=k)
    return None
