"""Command-line interface for the optimizer.

Examples
--------
    # Human-readable plan for a workload described in YAML or JSON:
    python -m aiopt.cli optimize --workload examples/workload-prod.yaml

    # Also write the canonical spec + Terraform tfvars + Pulumi config:
    python -m aiopt.cli optimize -w examples/workload-prod.yaml \
        --emit-dir out --stack prod
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import emit
from .optimizer import Optimizer
from .spec import WorkloadSpec


def _load_workload(path: Path) -> WorkloadSpec:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:  # pragma: no cover
            sys.exit(
                "PyYAML is required to read YAML workloads. "
                "Install it (`pip install pyyaml`) or provide a .json file."
            )
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return WorkloadSpec.from_dict(data)


def _cmd_optimize(args: argparse.Namespace) -> int:
    workload = _load_workload(Path(args.workload))
    optimizer = Optimizer(
        generations=args.generations,
        population_size=args.population,
        seed=args.seed,
    )
    result = optimizer.optimize(workload)

    print(result.summary())
    print("\nCost breakdown (USD/mo):")
    for line, value in result.cost.to_dict().items():
        print(f"  {line:<20} {value:>10,.2f}")

    if args.emit_dir:
        out = Path(args.emit_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "infra.yaml").write_text(emit.to_yaml(result.infra))
        (out / "terraform.auto.tfvars").write_text(
            emit.to_terraform_tfvars(result.infra)
        )
        (out / f"Pulumi.{args.stack}.yaml").write_text(
            emit.to_pulumi_config(result.infra, stack=args.stack)
        )
        print(f"\nWrote infra.yaml, terraform.auto.tfvars, "
              f"Pulumi.{args.stack}.yaml to {out}/")

    # Non-zero exit if the plan cannot satisfy the workload — useful in CI.
    return 0 if result.feasible else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiopt", description="AI-based Infrastructure-as-Code optimizer"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    opt = sub.add_parser("optimize", help="optimize infra for a workload")
    opt.add_argument("-w", "--workload", required=True, help="workload YAML/JSON file")
    opt.add_argument("--emit-dir", help="directory to write tfvars/pulumi/yaml into")
    opt.add_argument("--stack", default="dev", help="Pulumi stack name (default: dev)")
    opt.add_argument("--generations", type=int, default=60)
    opt.add_argument("--population", type=int, default=40)
    opt.add_argument("--seed", type=int, default=42)
    opt.set_defaults(func=_cmd_optimize)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
