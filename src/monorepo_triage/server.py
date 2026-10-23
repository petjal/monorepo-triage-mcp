"""Layer 3: FastMCP Protocol Service for Deterministic Monorepo Triage and Slicing."""

from typing import Any

from fastmcp import FastMCP

mcp = FastMCP("monorepo-triage-mcp")


@mcp.tool()
def triage_and_plan_repository(
    repo_path: str,
    token_budget: int = 16000,
    max_line_length: int = 1000,
    entropy_threshold: float = 5.2,
) -> dict[str, Any]:
    """Scan and triage a repository, returning bloat analysis and wave-ordered modernization slices."""
    raise NotImplementedError("triage_and_plan_repository contract not implemented")


@mcp.tool()
def plan_dependency_graph(
    module_tokens: dict[str, int],
    dependency_edges: dict[str, list[str]],
    token_budget: int = 16000,
) -> dict[str, Any]:
    """Calculate Tarjan SCCs, Kahn bottom-up waves, and token-bounded modernization slices directly from a graph."""
    raise NotImplementedError("plan_dependency_graph contract not implemented")


if __name__ == "__main__":
    mcp.run()
