"""Tests for Layer 3: FastMCP Tool Registration and End-to-End Monorepo Triage Service."""

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from monorepo_triage.server import (
    mcp,
    plan_dependency_graph,
    triage_and_plan_repository,
)


class TestServerFastMCPRegistration:
    def test_mcp_instance_name(self) -> None:
        assert mcp.name == "monorepo-triage-mcp"

    def test_tools_registered_in_fastmcp(self) -> None:
        async def check() -> None:
            tools = await mcp.list_tools()
            tool_names = [t.name for t in tools]
            assert "triage_and_plan_repository" in tool_names
            assert "plan_dependency_graph" in tool_names

        asyncio.run(check())


class TestPlanDependencyGraphTool:
    def test_direct_graph_planning(self) -> None:
        tokens = {
            "core.db": 2000,
            "service.user": 3000,
            "api.gateway": 1500,
        }
        edges = {
            "api.gateway": ["service.user"],
            "service.user": ["core.db"],
            "core.db": [],
        }

        res = plan_dependency_graph(
            module_tokens=tokens,
            dependency_edges=edges,
            token_budget=16000,
        )

        assert "modernization_plan" in res
        plan = res["modernization_plan"]
        assert plan["total_active_tokens"] == 6500
        assert plan["max_wave_depth"] == 2
        assert len(plan["slices"]) >= 3

        nodes = {n["scc_id"]: n for n in plan["condensation_nodes"]}
        assert nodes["core.db"]["wave"] == 0
        assert nodes["service.user"]["wave"] == 1
        assert nodes["api.gateway"]["wave"] == 2

    def test_boundary_budget_rejection(self) -> None:
        with pytest.raises(ValueError, match="outside safe corridor"):
            plan_dependency_graph(
                module_tokens={"a": 100},
                dependency_edges={"a": []},
                token_budget=100,  # Below minimum 500
            )


class TestTriageAndPlanRepositoryTool:
    def test_end_to_end_repo_triage(self, tmp_path: Path) -> None:
        repo = tmp_path / "test_repo"
        repo.mkdir()

        (repo / "src").mkdir()
        (repo / "src" / "__init__.py").write_text("")
        (repo / "src" / "db.py").write_text("class Database: pass\n")
        (repo / "src" / "service.py").write_text("from .db import Database\n")

        (repo / "node_modules" / "lib").mkdir(parents=True)
        (repo / "node_modules" / "lib" / "index.js").write_text("module.exports = {};\n")

        aws_tok = "AKIA" + "1234567890ABCDEF"
        (repo / "secret.env").write_text(f"AWS_KEY={aws_tok}\n")

        res = triage_and_plan_repository(
            repo_path=str(repo),
            token_budget=16000,
            max_line_length=1000,
            entropy_threshold=5.2,
        )

        assert "scan_summary" in res
        assert "modernization_plan" in res
        assert "agent_action_plan_markdown" in res
        assert "neo4j_knowledge_graph_cypher" in res
        assert "MERGE (n:CondensationNode" in res["neo4j_knowledge_graph_cypher"]
        assert "Wave-Ordered Parallel Agent Swarm Schedule" in res["agent_action_plan_markdown"]

        scan = res["scan_summary"]
        plan = res["modernization_plan"]

        assert scan["quarantined_tokens"] > 0
        assert scan["pruned_tokens"] > 0
        assert scan["pruned_file_count"] == 1
        assert scan["active_tokens"] > 0
        assert "node_modules" in scan["recommended_exclusions"]
        # By default (include_pruned_files=False), PRUNED_BLOAT records are omitted from MCP JSON output
        assert all(f["disposition"] != "PRUNED_BLOAT" for f in scan["files"])

        assert plan["total_active_tokens"] > 0
        assert len(plan["slices"]) > 0

        # When include_pruned_files=True, PRUNED_BLOAT records are included
        res_full = triage_and_plan_repository(
            repo_path=str(repo),
            token_budget=16000,
            include_pruned_files=True,
        )
        assert any(f["disposition"] == "PRUNED_BLOAT" for f in res_full["scan_summary"]["files"])

    def test_invalid_repo_path_rejection(self) -> None:
        with pytest.raises(ValueError, match="Repository path does not exist"):
            triage_and_plan_repository(
                repo_path="/tmp/non_existent_path_xyz_123",
            )

    def test_fastmcp_call_tool_roundtrip(self) -> None:
        async def call() -> None:
            args: dict[str, Any] = {
                "module_tokens": {"leaf": 800, "root": 1200},
                "dependency_edges": {"root": ["leaf"], "leaf": []},
                "token_budget": 16000,
            }
            call_res = await mcp.call_tool("plan_dependency_graph", args)
            assert call_res.is_error is False
            assert call_res.structured_content is not None
            plan = call_res.structured_content["modernization_plan"]
            assert plan["total_active_tokens"] == 2000

        asyncio.run(call())

    def test_enterprise_sprint_demo_end_to_end(self) -> None:
        demo_path = Path(__file__).resolve().parent.parent / "examples" / "run_django_sprint_demo.py"
        spec = importlib.util.spec_from_file_location("run_django_sprint_demo", demo_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result: dict[str, Any] = module.run_enterprise_sprint_demo()
        assert result["stage1_preflight_summary"]["active_source_files"] == 7
        assert result["stage1_preflight_summary"]["cyclic_knots_detected_before"] == 1
        assert result["stage1_preflight_summary"]["total_waves"] == 4
        # Stage 2.5 counterfactual: out-of-order execution fails real mypy --strict
        assert result["stage2_5_out_of_order_counterfactual"]["mypy_strict_passed"] is False
        # Stage 3 bottom-up execution: all 4 waves pass real mypy --strict and cycle drops 1 -> 0
        s3 = result["stage3_autonomous_80_pct_execution"]
        assert s3["before_typed_functions"] == "0/11 (0%)"
        assert s3["after_typed_functions"] == "11/11 (100%)"
        assert s3["cyclic_knots_after_stage3"] == 0
        assert s3["waves_preserved_after_stage3"] == 4
        assert len(s3["waves_executed"]) == 4
        assert all(w["judge_mypy_strict_passed"] is True for w in s3["waves_executed"])
        assert len(result["stage4_human_20_pct_handoff"]) == 3

