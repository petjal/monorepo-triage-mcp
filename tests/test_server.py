"""Tests for Layer 3: FastMCP Tool Registration and End-to-End Monorepo Triage Service."""

import asyncio
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

        (repo / "secret.env").write_text("AWS_KEY=AKIA1234567890ABCDEF\n")

        res = triage_and_plan_repository(
            repo_path=str(repo),
            token_budget=16000,
            max_line_length=1000,
            entropy_threshold=5.2,
        )

        assert "scan_summary" in res
        assert "modernization_plan" in res

        scan = res["scan_summary"]
        plan = res["modernization_plan"]

        assert scan["quarantined_tokens"] > 0
        assert scan["pruned_tokens"] > 0
        assert scan["active_tokens"] > 0
        assert "node_modules" in scan["recommended_exclusions"]

        assert plan["total_active_tokens"] > 0
        assert len(plan["slices"]) > 0

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
