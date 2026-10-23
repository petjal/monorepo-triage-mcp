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
    export_neo4j_cypher,
    plan_from_scan,
    render_agent_action_plan_markdown,
)

mcp = FastMCP("monorepo-triage-mcp")


@mcp.tool()
def triage_and_plan_repository(
    repo_path: str,
    token_budget: int = 16000,
    max_line_length: int = 1000,
    entropy_threshold: float = 5.2,
    include_pruned_files: bool = False,
) -> dict[str, Any]:
    """Scan and triage a repository, returning bloat analysis, wave-ordered slices, Neo4j Cypher, and an Agent Action Plan."""
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
    action_plan_md = render_agent_action_plan_markdown(
        scan_summary, plan, token_budget=valid_budget
    )
    neo4j_cypher = export_neo4j_cypher(plan)

    scan_dict = asdict(scan_summary)
    pruned_count = sum(1 for f in scan_summary.files if f.disposition == "PRUNED_BLOAT")
    scan_dict["pruned_file_count"] = pruned_count
    if not include_pruned_files:
        scan_dict["files"] = [
            f for f in scan_dict["files"] if f["disposition"] != "PRUNED_BLOAT"
        ]

    return {
        "scan_summary": scan_dict,
        "modernization_plan": asdict(plan),
        "agent_action_plan_markdown": action_plan_md,
        "neo4j_knowledge_graph_cypher": neo4j_cypher,
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
