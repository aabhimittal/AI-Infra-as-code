"""Genetic algorithm that searches the infra config space for the cheapest
*feasible* :class:`InfraSpec`.

Why a genetic algorithm? The search space (node type × node count × DB class ×
storage) is discrete, non-convex, and constrained — feasibility is a step
function, cost is roughly monotone but not separable across genes. Exhaustive
search is possible for today's small catalog, but a GA scales as the catalog and
the number of tunable dimensions grow, and it naturally accepts *seed* genomes
from the k-NN recommender for a warm start.

Fitness (higher is better):
    feasible   ->  -monthly_cost
    infeasible ->  -monthly_cost - PENALTY * total_constraint_severity

so the population is driven first toward feasibility, then toward low cost.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable, List, Optional

from . import catalog, capacity_model, cost_model
from .spec import (
    DatabaseSpec,
    InfraSpec,
    KubernetesSpec,
    NetworkSpec,
    WorkloadSpec,
)

INFEASIBLE_PENALTY = 5000.0


@dataclass
class Genome:
    """The tunable genes. Environment-driven fields (AZ count, multi-AZ, NAT)
    are fixed by policy before the search and carried on the template, so the GA
    only explores the dimensions that trade cost against capacity."""

    node_instance_type: str
    node_desired: int
    db_instance_class: str
    allocated_storage_gb: int


@dataclass
class Individual:
    genome: Genome
    fitness: float
    infra: InfraSpec


class GeneticOptimizer:
    def __init__(
        self,
        workload: WorkloadSpec,
        template: InfraSpec,
        *,
        population_size: int = 40,
        generations: int = 60,
        mutation_rate: float = 0.2,
        elitism: int = 2,
        tournament_k: int = 3,
        seed: Optional[int] = 42,
        storage_choices: Optional[List[int]] = None,
    ) -> None:
        """``template`` supplies the fixed (policy) fields; the GA overwrites
        only the four genes above onto copies of it."""
        self.workload = workload
        self.template = template
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elitism = elitism
        self.tournament_k = tournament_k
        self.rng = random.Random(seed)

        self.node_types = [c.name for c in catalog.COMPUTE_TYPES]
        self.db_types = [d.name for d in catalog.DATABASE_TYPES]
        self.node_min = template.kubernetes.node_min
        self.node_max = template.kubernetes.node_max
        self.storage_choices = storage_choices or [20, 50, 100, 200, 400, 800]

    # --- genome <-> infra ------------------------------------------------- #
    def _to_infra(self, g: Genome) -> InfraSpec:
        t = self.template
        return replace(
            t,
            kubernetes=replace(
                t.kubernetes,
                node_instance_type=g.node_instance_type,
                node_desired=g.node_desired,
            ),
            database=replace(
                t.database,
                instance_class=g.db_instance_class,
                allocated_storage_gb=g.allocated_storage_gb,
            ),
        )

    def _fitness(self, g: Genome) -> Individual:
        infra = self._to_infra(g)
        cost = cost_model.monthly_cost(infra)
        severity = capacity_model.total_severity(infra, self.workload)
        fitness = -cost - (INFEASIBLE_PENALTY * severity if severity > 0 else 0.0)
        return Individual(genome=g, fitness=fitness, infra=infra)

    # --- genetic operators ------------------------------------------------ #
    def _random_genome(self) -> Genome:
        return Genome(
            node_instance_type=self.rng.choice(self.node_types),
            node_desired=self.rng.randint(self.node_min, self.node_max),
            db_instance_class=self.rng.choice(self.db_types),
            allocated_storage_gb=self.rng.choice(self.storage_choices),
        )

    def _mutate(self, g: Genome) -> Genome:
        g = replace(g)
        if self.rng.random() < self.mutation_rate:
            g.node_instance_type = self.rng.choice(self.node_types)
        if self.rng.random() < self.mutation_rate:
            g.node_desired = self.rng.randint(self.node_min, self.node_max)
        if self.rng.random() < self.mutation_rate:
            g.db_instance_class = self.rng.choice(self.db_types)
        if self.rng.random() < self.mutation_rate:
            g.allocated_storage_gb = self.rng.choice(self.storage_choices)
        return g

    def _crossover(self, a: Genome, b: Genome) -> Genome:
        return Genome(
            node_instance_type=self.rng.choice([a.node_instance_type, b.node_instance_type]),
            node_desired=self.rng.choice([a.node_desired, b.node_desired]),
            db_instance_class=self.rng.choice([a.db_instance_class, b.db_instance_class]),
            allocated_storage_gb=self.rng.choice([a.allocated_storage_gb, b.allocated_storage_gb]),
        )

    def _tournament(self, pop: List[Individual]) -> Individual:
        contenders = self.rng.sample(pop, min(self.tournament_k, len(pop)))
        return max(contenders, key=lambda i: i.fitness)

    def _clamp_seed(self, g: Genome) -> Genome:
        """Coerce a recommender-supplied seed genome into the valid domain."""
        return Genome(
            node_instance_type=g.node_instance_type
            if g.node_instance_type in catalog.COMPUTE_BY_NAME
            else self.rng.choice(self.node_types),
            node_desired=min(max(g.node_desired, self.node_min), self.node_max),
            db_instance_class=g.db_instance_class
            if g.db_instance_class in catalog.DATABASE_BY_NAME
            else self.rng.choice(self.db_types),
            allocated_storage_gb=max(g.allocated_storage_gb, 20),
        )

    # --- driver ----------------------------------------------------------- #
    def run(
        self,
        seeds: Optional[List[Genome]] = None,
        on_generation: Optional[Callable[[int, Individual], None]] = None,
    ) -> Individual:
        # Seed the initial population with recommender suggestions (warm start),
        # then fill the rest at random for exploration.
        genomes: List[Genome] = [self._clamp_seed(s) for s in (seeds or [])]
        while len(genomes) < self.population_size:
            genomes.append(self._random_genome())

        population = [self._fitness(g) for g in genomes]
        population.sort(key=lambda i: i.fitness, reverse=True)
        best = population[0]

        for gen in range(self.generations):
            # Elitism: carry the best few forward unchanged.
            next_pop: List[Individual] = population[: self.elitism]
            while len(next_pop) < self.population_size:
                parent_a = self._tournament(population)
                parent_b = self._tournament(population)
                child = self._mutate(self._crossover(parent_a.genome, parent_b.genome))
                next_pop.append(self._fitness(child))

            population = sorted(next_pop, key=lambda i: i.fitness, reverse=True)
            if population[0].fitness > best.fitness:
                best = population[0]
            if on_generation:
                on_generation(gen, best)

        return best
