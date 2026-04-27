from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console


@dataclass
class PairResult:
    name: str
    precision: float
    recall: float
    diff: dict[str, Any]
    valid: bool
    error: str = ""

    @property
    def f1(self) -> float:
        denom = self.precision + self.recall
        return (2 * self.precision * self.recall / denom) if denom > 0 else 0.0

    @property
    def passed(self) -> bool:
        return self.valid and not self.diff


@dataclass
class EvalReport:
    pairs: list[PairResult] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )

    @property
    def mean_precision(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(p.precision for p in self.pairs) / len(self.pairs)

    @property
    def mean_recall(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(p.recall for p in self.pairs) / len(self.pairs)

    @property
    def mean_f1(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(p.f1 for p in self.pairs) / len(self.pairs)

    @property
    def validation_rate(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(1 for p in self.pairs if p.valid) / len(self.pairs)

    @property
    def regression_free(self) -> bool:
        return all(p.passed for p in self.pairs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "mean_precision": self.mean_precision,
            "mean_recall": self.mean_recall,
            "mean_f1": self.mean_f1,
            "validation_rate": self.validation_rate,
            "regression_free": self.regression_free,
            "pairs": [
                {
                    "name": p.name,
                    "precision": p.precision,
                    "recall": p.recall,
                    "f1": p.f1,
                    "valid": p.valid,
                    "passed": p.passed,
                    "diff_keys": list(p.diff.keys()),
                    "error": p.error,
                }
                for p in self.pairs
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def print_summary(self, console: Console) -> None:
        from rich.table import Table

        table = Table(title=f"Eval Report — {self.timestamp[:19]}")
        table.add_column("Pair", style="cyan")
        table.add_column("Precision", justify="right")
        table.add_column("Recall", justify="right")
        table.add_column("F1", justify="right")
        table.add_column("Valid", justify="center")
        table.add_column("Diff", justify="center")

        for p in self.pairs:
            status = "[green]✓[/]" if p.passed else "[red]✗[/]"
            table.add_row(
                p.name,
                f"{p.precision:.2f}",
                f"{p.recall:.2f}",
                f"{p.f1:.2f}",
                "[green]yes[/]" if p.valid else "[red]no[/]",
                status,
            )

        console.print(table)
        console.print(
            f"Mean P={self.mean_precision:.2f}  "
            f"R={self.mean_recall:.2f}  "
            f"F1={self.mean_f1:.2f}  "
            f"Valid={self.validation_rate:.0%}"
        )
