"""Layer 3: FastMCP Protocol Service for Deterministic Monorepo Triage and Slicing."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from monorepo_triage.layer0_invariants import (
    validate_entropy_threshold,
    validate_line_length_limit,
    validate_token_budget,
)
from monorepo_triage.layer1_scanner import scan_repository
from monorepo_triage.layer2_slice_planner import (
    build_modernization_plan,
    plan_from_scan,
)

mcp = FastMCP("monorepo-triage-mcp")


@mcp.tool()
def triage_and_plan_repository(
    repo_path: str,
    token_budget: int = 16000,
    max_line_length: int = 1000,
    entropy_threshold: float = 5.2,
) -> dict[str, Any]:
    """Scan and triage a repository, returning bloat analysis and wave-ordered modernization slices."""
    path = Path(repo_path)
    if not path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")
    if not path.is_dir():
        raise ValueError(f"Repository path must be a directory: {repo_path}")

    valid_budget = validate_token_budget(token_budget)
    valid_max_line = validate_line_length_limit(max_line_length)
    valid_entropy = validate_entropy_threshold(entropy_threshold)

    scan_summary = scan_repository(
        path,
        max_line_length=valid_max_line,
        entropy_threshold=valid_entropy,
    )
    plan = plan_from_scan(scan_summary, token_budget=valid_budget)

    return {
        "scan_summary": asdict(scan_summary),
        "modernization_plan": asdict(plan),
    }


@mcp.tool()
def plan_dependency_graph(
    module_tokens: dict[str, int],
    dependency_edges: dict[str, list[str]],
    token_budget: int = 16000,
) -> dict[str, Any]:
    """Calculate Tarjan SCCs, Kahn bottom-up waves, and token-bounded modernization slices directly from a graph."""
    valid_budget = validate_token_budget(token_budget)
    plan = build_modernization_plan(
        modules=module_tokens,
        edges=dependency_edges,
        token_budget=valid_budget,
    )
    return {
        "modernization_plan": asdict(plan),
    }


if __name__ == "__main__":
    mcp.run()
