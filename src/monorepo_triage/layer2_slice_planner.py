"""Layer 2: Tarjan SCC Condensation, Bottom-Up Wave Assignment, and Token-Bounded Slice Planner."""

from dataclasses import dataclass
from typing import Literal

from monorepo_triage.layer1_scanner import ScanSummary

SliceStatus = Literal["READY", "OVERSIZED_COUPLED_KNOT"]


@dataclass(frozen=True)
class CondensationNode:
    scc_id: str
    modules: tuple[str, ...]
    is_cyclic: bool
    total_tokens: int
    wave: int
    depends_on_sccs: tuple[str, ...]


@dataclass(frozen=True)
class ModernizationSlice:
    slice_id: str
    wave: int
    scc_ids: tuple[str, ...]
    modules: tuple[str, ...]
    total_tokens: int
    status: SliceStatus


@dataclass(frozen=True)
class ModernizationPlan:
    condensation_nodes: tuple[CondensationNode, ...]
    slices: tuple[ModernizationSlice, ...]
    cyclic_knot_count: int
    max_wave_depth: int
    total_active_tokens: int


def build_modernization_plan(
    modules: dict[str, int],
    edges: dict[str, set[str]] | dict[str, list[str]],
    token_budget: int = 16000,
) -> ModernizationPlan:
    """Build deterministic modernization plan from module weights and dependency edges."""
    raise NotImplementedError("build_modernization_plan contract not implemented")


def plan_from_scan(
    scan_summary: ScanSummary,
    token_budget: int = 16000,
) -> ModernizationPlan:
    """Derive modernization plan directly from Layer 1 scan summary."""
    raise NotImplementedError("plan_from_scan contract not implemented")
