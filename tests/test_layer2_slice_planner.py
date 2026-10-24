"""Tests for Layer 2: Tarjan SCC Condensation, DAG Wave Assignment, and Slice Bin-Packing."""

from pathlib import Path

from monorepo_triage.layer1_scanner import FileRecord, ScanSummary
from monorepo_triage.layer2_slice_planner import (
    build_modernization_plan,
    export_neo4j_cypher,
    plan_from_scan,
    render_agent_action_plan_markdown,
)


class TestTarjanSCCCondensation:
    def test_acyclic_dag_singletons(self) -> None:
        modules = {"app.main": 1000, "app.service": 2000, "app.db": 3000}
        edges: dict[str, set[str]] = {
            "app.main": {"app.service"},
            "app.service": {"app.db"},
            "app.db": set(),
        }

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert len(plan.condensation_nodes) == 3
        assert plan.cyclic_knot_count == 0
        assert all(not node.is_cyclic for node in plan.condensation_nodes)

        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert "app.db" in node_map
        assert "app.service" in node_map
        assert "app.main" in node_map

    def test_cyclic_knot_detection(self) -> None:
        modules = {
            "auth.service": 1200,
            "auth.session": 800,
            "user.model": 1500,
            "billing.core": 900,
        }
        edges: dict[str, set[str]] = {
            "auth.service": {"auth.session", "user.model"},
            "auth.session": {"auth.service", "user.model"},
            "user.model": set(),
            "billing.core": {"user.model"},
        }

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert plan.cyclic_knot_count == 1

        cyclic_node = next(n for n in plan.condensation_nodes if n.is_cyclic)
        assert set(cyclic_node.modules) == {"auth.service", "auth.session"}
        assert cyclic_node.total_tokens == 2000
        assert "user.model" in cyclic_node.depends_on_sccs

    def test_self_loop_marked_cyclic(self) -> None:
        modules = {"recursive.worker": 500}
        edges: dict[str, set[str]] = {"recursive.worker": {"recursive.worker"}}

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert plan.cyclic_knot_count == 1
        node = plan.condensation_nodes[0]
        assert node.is_cyclic is True
        assert node.modules == ("recursive.worker",)


class TestKahnBottomUpWaveAssignment:
    def test_bottom_up_wave_levels(self) -> None:
        modules = {
            "infra.db": 1000,
            "infra.telemetry": 1000,
            "core.cache": 1000,
            "core.auth": 1000,
            "service.api": 1000,
            "edge.gateway": 1000,
        }
        edges: dict[str, set[str]] = {
            "infra.db": set(),
            "infra.telemetry": set(),
            "core.cache": {"infra.db"},
            "core.auth": {"infra.db"},
            "service.api": {"core.auth", "core.cache"},
            "edge.gateway": {"service.api"},
        }

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        assert node_map["infra.db"].wave == 0
        assert node_map["infra.telemetry"].wave == 0
        assert node_map["core.cache"].wave == 1
        assert node_map["core.auth"].wave == 1
        assert node_map["service.api"].wave == 2
        assert node_map["edge.gateway"].wave == 3
        assert plan.max_wave_depth == 3


class TestDeterministicSliceBinPacking:
    def test_ffd_packing_within_wave(self) -> None:
        modules = {
            "mod.a": 4000,
            "mod.b": 3500,
            "mod.c": 3000,
            "mod.d": 2000,
        }
        edges: dict[str, set[str]] = {m: set() for m in modules}

        plan = build_modernization_plan(modules, edges, token_budget=10000)

        assert len(plan.slices) == 2
        assert all(s.wave == 0 for s in plan.slices)
        assert all(s.status == "READY" for s in plan.slices)

        s1 = next(s for s in plan.slices if "mod.a" in s.modules)
        assert "mod.b" in s1.modules
        assert "mod.d" in s1.modules
        assert s1.total_tokens == 9500

        s2 = next(s for s in plan.slices if "mod.c" in s.modules)
        assert s2.total_tokens == 3000

    def test_waves_never_mixed_in_same_slice(self) -> None:
        modules = {
            "leaf.mod": 500,
            "parent.mod": 500,
        }
        edges: dict[str, set[str]] = {
            "leaf.mod": set(),
            "parent.mod": {"leaf.mod"},
        }
        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert len(plan.slices) == 2
        assert {s.wave for s in plan.slices} == {0, 1}

    def test_oversized_coupled_knot_flagging(self) -> None:
        modules = {
            "monolith.heavy": 25000,
            "light.helper": 1000,
            "knot.a": 10000,
            "knot.b": 10000,
        }
        edges: dict[str, set[str]] = {
            "monolith.heavy": set(),
            "light.helper": set(),
            "knot.a": {"knot.b"},
            "knot.b": {"knot.a"},
        }

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        oversized_singles = [s for s in plan.slices if s.status == "OVERSIZED_SINGLE_MODULE"]
        assert len(oversized_singles) == 1
        assert oversized_singles[0].modules == ("monolith.heavy",)
        assert oversized_singles[0].total_tokens == 25000

        oversized_knots = [s for s in plan.slices if s.status == "OVERSIZED_COUPLED_KNOT"]
        assert len(oversized_knots) == 1
        assert set(oversized_knots[0].modules) == {"knot.a", "knot.b"}
        assert oversized_knots[0].total_tokens == 20000

        ready = [s for s in plan.slices if s.status == "READY"]
        assert len(ready) == 1
        assert ready[0].modules == ("light.helper",)


class TestPlanFromScanIntegration:
    def test_plan_derived_from_scan_summary(self) -> None:
        files = (
            FileRecord(
                rel_path="src/infra/db.py",
                module_id="src.infra.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=1500,
                shannon_entropy=4.2,
                max_line_length=80,
                imports=(),
            ),
            FileRecord(
                rel_path="src/service/api.py",
                module_id="src.service.api",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=2500,
                shannon_entropy=4.3,
                max_line_length=90,
                imports=("src.infra.db", "external_lib"),
            ),
            FileRecord(
                rel_path="node_modules/foo/index.js",
                module_id=None,
                disposition="PRUNED_BLOAT",
                reason="vendored_or_build_dir",
                estimated_tokens=5000,
                shannon_entropy=5.0,
                max_line_length=100,
                imports=(),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=4000,
            pruned_tokens=5000,
            quarantined_tokens=0,
            token_reduction_ratio=0.5556,
            symlink_loops_skipped=(),
            recommended_exclusions=("node_modules",),
        )

        plan = plan_from_scan(scan, token_budget=16000)
        assert plan.total_active_tokens == 4000
        assert len(plan.condensation_nodes) == 2

        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert "src.infra.db" in node_map
        assert "src.service.api" in node_map
        assert node_map["src.infra.db"].wave == 0
        assert node_map["src.service.api"].wave == 1
        assert "src.infra.db" in node_map["src.service.api"].depends_on_sccs


class TestAuditRemediationLayer2:
    def test_deep_1200_node_chain_does_not_hit_recursion_error(self) -> None:
        """Catch 1: Wave evaluation on a 1,200-node linear dependency chain must be iterative."""
        depth = 1200
        modules = {f"mod_{i:04d}": 100 for i in range(depth)}
        edges: dict[str, set[str]] = {
            f"mod_{i:04d}": ({f"mod_{i - 1:04d}"} if i > 0 else set())
            for i in range(depth)
        }
        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert plan.max_wave_depth == depth - 1
        assert plan.total_active_tokens == depth * 100

    def test_colliding_module_ids_preserve_token_and_edge_conservation(self) -> None:
        """Catch 2: Colliding module_ids (e.g., pkg/__init__.py + pkg.py) must aggregate tokens and edges."""
        files = (
            FileRecord(
                rel_path="pkg/__init__.py",
                module_id="pkg",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("pkg.alpha",),
            ),
            FileRecord(
                rel_path="pkg.py",
                module_id="pkg",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=600,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("pkg.beta",),
            ),
            FileRecord(
                rel_path="pkg/alpha.py",
                module_id="pkg.alpha",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=(),
            ),
            FileRecord(
                rel_path="pkg/beta.py",
                module_id="pkg.beta",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=(),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=1800,
            pruned_tokens=0,
            quarantined_tokens=0,
            token_reduction_ratio=0.0,
            symlink_loops_skipped=(),
            recommended_exclusions=(),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        assert plan.total_active_tokens == scan.active_tokens == 1800
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["pkg"].total_tokens == 1000
        assert set(node_map["pkg"].depends_on_sccs) == {"pkg.alpha", "pkg.beta"}

    def test_negative_or_boolean_module_token_weights_rejected(self) -> None:
        """Catch 5: Negative or boolean module token weights must be rejected before FFD packing."""
        import pytest

        empty_edges: dict[str, set[str]] = {"mod.a": set()}
        with pytest.raises(ValueError, match="non-negative"):
            build_modernization_plan({"mod.a": -500}, empty_edges, token_budget=16000)

        with pytest.raises(TypeError, match="integer"):
            build_modernization_plan({"mod.a": True}, empty_edges, token_budget=16000)


class TestAuditRound2Layer2:
    def test_src_layout_and_multi_package_monorepo_resolution(self) -> None:
        """Bug 5 (Probe 9): Root src/, nested packages/*/src/, and Maven */src/main/java/ resolve cleanly."""
        files = (
            FileRecord(
                rel_path="packages/core/src/core/db.py",
                module_id="packages.core.src.core.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="packages/core/src/core/api.py",
                module_id="packages.core.src.core.api",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=600,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("core.db", "core.db.query"),
            ),
            FileRecord(
                rel_path="billing/src/main/java/com/acme/Repo.java",
                module_id="billing.src.main.java.com.acme.Repo",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=70,
                imports=(),
            ),
            FileRecord(
                rel_path="billing/src/main/java/com/acme/Billing.java",
                module_id="billing.src.main.java.com.acme.Billing",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=700,
                shannon_entropy=4.1,
                max_line_length=75,
                imports=("com.acme.Repo",),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=2200,
            pruned_tokens=0,
            quarantined_tokens=0,
            token_reduction_ratio=0.0,
            symlink_loops_skipped=(),
            recommended_exclusions=(),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["packages.core.src.core.db"].wave == 0
        assert node_map["packages.core.src.core.api"].wave == 1
        assert node_map["billing.src.main.java.com.acme.Repo"].wave == 0
        assert node_map["billing.src.main.java.com.acme.Billing"].wave == 1

    def test_python_init_reexports_do_not_create_false_cycles(self) -> None:
        """Bug 4 (Probe 6 & 7): Standard Python package __init__.py re-exports must not trigger false cycles."""
        files = (
            FileRecord(
                rel_path="pkg/__init__.py",
                module_id="pkg",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=100,
                shannon_entropy=3.8,
                max_line_length=50,
                imports=("pkg.service", "pkg.service.UserService"),
            ),
            FileRecord(
                rel_path="pkg/service.py",
                module_id="pkg.service",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("pkg.models", "pkg.models.User", "pkg.unknown_const"),
            ),
            FileRecord(
                rel_path="pkg/models.py",
                module_id="pkg.models",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=900,
            pruned_tokens=0,
            quarantined_tokens=0,
            token_reduction_ratio=0.0,
            symlink_loops_skipped=(),
            recommended_exclusions=(),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        assert plan.cyclic_knot_count == 0
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["pkg.models"].wave == 0
        assert node_map["pkg.service"].wave == 1
        assert node_map["pkg"].wave == 2

    def test_typescript_index_barrel_and_reexport_wave_resolution(self) -> None:
        """Bug 5 (Probe 3): TypeScript index.ts barrel imports (./auth -> src.auth.index) resolve waves."""
        files = (
            FileRecord(
                rel_path="src/auth/service.ts",
                module_id="src.auth.service",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="src/auth/index.ts",
                module_id="src.auth.index",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=200,
                shannon_entropy=3.9,
                max_line_length=50,
                imports=("./service", "src.auth.service"),
            ),
            FileRecord(
                rel_path="src/app.ts",
                module_id="src.app",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("./auth", "src.auth"),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=1100,
            pruned_tokens=0,
            quarantined_tokens=0,
            token_reduction_ratio=0.0,
            symlink_loops_skipped=(),
            recommended_exclusions=(),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["src.auth.service"].wave == 0
        assert node_map["src.auth.index"].wave == 1
        assert node_map["src.app"].wave == 2

    def test_go_module_prefix_and_package_directory_wave_resolution(self) -> None:
        """Bug 5 (Probe 2): Go package directory imports ('myrepo/pkg/router') resolve to pkg/router/*.go."""
        files = (
            FileRecord(
                rel_path="pkg/db/conn.go",
                module_id="pkg.db.conn",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("database/sql",),
            ),
            FileRecord(
                rel_path="pkg/router/router.go",
                module_id="pkg.router.router",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("github.com/acme/myrepo/pkg/db", "github.com.acme.myrepo.pkg.db"),
            ),
            FileRecord(
                rel_path="cmd/server/main.go",
                module_id="cmd.server.main",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("github.com/acme/myrepo/pkg/router", "github.com.acme.myrepo.pkg.router"),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=1200,
            pruned_tokens=0,
            quarantined_tokens=0,
            token_reduction_ratio=0.0,
            symlink_loops_skipped=(),
            recommended_exclusions=(),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["pkg.db.conn"].wave == 0
        assert node_map["pkg.router.router"].wave == 1
        assert node_map["cmd.server.main"].wave == 2

    def test_scc_id_no_collision_when_module_name_contains_plus(self) -> None:
        """Bug 6 (Probe 8): A module containing '+' must never collide with a multi-node SCC ID."""
        modules = {"a": 500, "b": 500, "a+b": 500}
        edges: dict[str, set[str]] = {
            "a": {"b"},
            "b": {"a"},
            "a+b": {"a"},
        }
        plan = build_modernization_plan(modules, edges, token_budget=16000)
        assert len(plan.condensation_nodes) == 2
        assert len({n.scc_id for n in plan.condensation_nodes}) == 2
        assert plan.cyclic_knot_count == 1
        assert plan.max_wave_depth == 1
        single_node = next(n for n in plan.condensation_nodes if not n.is_cyclic)
        assert single_node.modules == ("a+b",)
        assert single_node.wave == 1

    def test_neo4j_cypher_export_and_agent_action_plan_markdown(self) -> None:
        """Verify Neo4j Cypher knowledge graph export and Markdown Agent Action Plan gate."""
        files = (
            FileRecord(
                rel_path="src/db.py",
                module_id="src.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=800,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="src/api.py",
                module_id="src.api",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=1200,
                shannon_entropy=4.1,
                max_line_length=70,
                imports=("db",),
            ),
        )
        scan = ScanSummary(
            root_path="/tmp/fake_repo",
            files=files,
            active_tokens=2000,
            pruned_tokens=5000,
            quarantined_tokens=0,
            token_reduction_ratio=0.7143,
            symlink_loops_skipped=(),
            recommended_exclusions=("node_modules",),
        )
        plan = plan_from_scan(scan, token_budget=16000)
        cypher = export_neo4j_cypher(plan)
        assert ':CondensationNode {scc_id: "src.db"}' in cypher
        assert 'MERGE (a)-[:DEPENDS_ON]->(b);' in cypher

        md = render_agent_action_plan_markdown(scan, plan, token_budget=16000)
        assert "# Pre-Execution Technical Specification & Agent Action Plan" in md
        assert "### Wave 0 (Max Parallel Agent Workers: 1" in md
        assert "### Wave 1 (Max Parallel Agent Workers: 1" in md


class TestAuditRound3Layer2:
    def test_multi_service_monorepo_locality_prevents_false_cross_service_knot(self) -> None:
        """P0-1: Independent microservices sharing module names (db.py, api.py) must resolve locally without false cycles."""
        files = (
            FileRecord(
                rel_path="services/auth/src/db.py",
                module_id="services.auth.src.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=100,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=(),
            ),
            FileRecord(
                rel_path="services/auth/src/api.py",
                module_id="services.auth.src.api",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=100,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=("db",),
            ),
            FileRecord(
                rel_path="services/billing/src/db.py",
                module_id="services.billing.src.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=100,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=("api",),
            ),
            FileRecord(
                rel_path="services/billing/src/api.py",
                module_id="services.billing.src.api",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=100,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=(),
            ),
        )
        scan = ScanSummary("/tmp/r", files, 400, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        assert plan.cyclic_knot_count == 0
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["services.auth.src.db"].wave == 0
        assert node_map["services.auth.src.api"].wave == 1
        assert node_map["services.billing.src.api"].wave == 0
        assert node_map["services.billing.src.db"].wave == 1

    def test_pep8_absolute_import_with_package_init_reexport_stays_acyclic(
        self, tmp_path: Path
    ) -> None:
        """P0-2: 'from pkg import models' inside pkg/service.py must not form a cycle with pkg/__init__.py."""
        from monorepo_triage.layer1_scanner import scan_repository

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from pkg.service import UserService\n")
        (pkg / "models.py").write_text("class User: pass\n")
        (pkg / "service.py").write_text("from pkg import models\nclass UserService: pass\n")

        scan = scan_repository(tmp_path)
        plan = plan_from_scan(scan, token_budget=16000)
        assert plan.cyclic_knot_count == 0
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["pkg.models"].wave == 0
        assert node_map["pkg.service"].wave == 1
        assert node_map["pkg"].wave == 2

    def test_composed_src_and_index_barrel_alias_resolution(self) -> None:
        """P0-4: 'src/auth/index.ts' must register composed alias 'auth' for baseUrl/alias imports."""
        files = (
            FileRecord(
                rel_path="src/auth/index.ts",
                module_id="src.auth.index",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=200,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=(),
            ),
            FileRecord(
                rel_path="src/pages/home.tsx",
                module_id="src.pages.home",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=50,
                imports=("auth",),
            ),
        )
        scan = ScanSummary("/tmp/r", files, 500, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}
        assert node_map["src.auth.index"].wave == 0
        assert node_map["src.pages.home"].wave == 1

    def test_edges_string_type_rejected_and_empty_plan_markdown(self) -> None:
        """P1-1: Passing a string instead of a collection of module IDs in edges must raise TypeError."""
        import pytest

        with pytest.raises(TypeError, match="iterable of module IDs"):
            build_modernization_plan({"a": 100, "m": 100}, {"a": "mod_b"})  # type: ignore[arg-type]

        empty_scan = ScanSummary("/tmp/empty", (), 0, 0, 0, 0.0, (), ())
        empty_plan = plan_from_scan(empty_scan, token_budget=16000)
        md = render_agent_action_plan_markdown(empty_scan, empty_plan, token_budget=16000)
        assert "- **Bottom-Up Modernization Waves:** 0\n" in md


class TestAuditRound4Layer2:
    def test_regular_files_preserve_edges_router_test_and_directory_sibling(self) -> None:
        """Finding 4: Multi-dot filenames (*.test.ts) and directory-siblings (../auth) must not have edges deleted."""
        files = (
            FileRecord(
                rel_path="src/router.ts",
                module_id="src.router",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="src/router.test.ts",
                module_id="src.router.test",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("./router", "src.router"),
            ),
            FileRecord(
                rel_path="src/auth.ts",
                module_id="src.auth",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="src/auth/helper.ts",
                module_id="src.auth.helper",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=200,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("../auth", "src.auth"),
            ),
        )
        scan = ScanSummary("/tmp/r", files, 1400, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        # Router test must be Wave 1 depending on router Wave 0
        assert node_map["src.router"].wave == 0
        assert node_map["src.router.test"].wave == 1
        assert "src.router" in node_map["src.router.test"].depends_on_sccs

        # Auth helper must be Wave 1 depending on auth Wave 0
        assert node_map["src.auth"].wave == 0
        assert node_map["src.auth.helper"].wave == 1
        assert "src.auth" in node_map["src.auth.helper"].depends_on_sccs

    def test_typescript_workspace_scoped_imports(self) -> None:
        """Finding 4: Scoped workspace package imports (@trpc/server) resolve to packages/server/src/index.ts."""
        files = (
            FileRecord(
                rel_path="packages/server/src/index.ts",
                module_id="packages.server.src.index",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=1000,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="packages/client/src/index.ts",
                module_id="packages.client.src.index",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=800,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("@trpc/server", "server"),
            ),
        )
        scan = ScanSummary("/tmp/trpc", files, 1800, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        assert node_map["packages.server.src.index"].wave == 0
        assert node_map["packages.client.src.index"].wave == 1
        assert "packages.server.src.index" in node_map["packages.client.src.index"].depends_on_sccs

    def test_go_stdlib_ignored_and_nested_monorepo_suffixes(self) -> None:
        """Finding 4: Go stdlib 'net/http' is ignored, while nested monorepo 'github.com/acme/auth/pkg/db' resolves."""
        files = (
            FileRecord(
                rel_path="http/handler.go",
                module_id="http.handler",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="services/auth/pkg/db/client.go",
                module_id="services.auth.pkg.db.client",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("net/http",),
            ),
            FileRecord(
                rel_path="services/auth/cmd/main.go",
                module_id="services.auth.cmd.main",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=300,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("github.com/acme/auth/pkg/db",),
            ),
        )
        scan = ScanSummary("/tmp/go", files, 1200, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        # db client importing 'net/http' must NOT depend on local 'http.handler'
        assert "http.handler" not in node_map["services.auth.pkg.db.client"].depends_on_sccs
        assert node_map["services.auth.pkg.db.client"].wave == 0

        # main importing 'github.com/acme/auth/pkg/db' must resolve to services.auth.pkg.db.client
        assert "services.auth.pkg.db.client" in node_map["services.auth.cmd.main"].depends_on_sccs
        assert node_map["services.auth.cmd.main"].wave == 1

    def test_java_wildcard_layer2_resolution(self) -> None:
        """Finding 4: Java wildcard 'import com.acme.models.*' links to internal class files in Layer 2."""
        files = (
            FileRecord(
                rel_path="billing/src/main/java/com/acme/models/User.java",
                module_id="billing.src.main.java.com.acme.models.User",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="billing/src/main/java/com/acme/models/Order.java",
                module_id="billing.src.main.java.com.acme.models.Order",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=400,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="billing/src/main/java/com/acme/service/UserService.java",
                module_id="billing.src.main.java.com.acme.service.UserService",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=600,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("com.acme.models",),
            ),
        )
        scan = ScanSummary("/tmp/java", files, 1400, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        user_svc = node_map["billing.src.main.java.com.acme.service.UserService"]
        assert "billing.src.main.java.com.acme.models.User" in user_svc.depends_on_sccs
        assert "billing.src.main.java.com.acme.models.Order" in user_svc.depends_on_sccs
        assert user_svc.wave == 1

    def test_filter_by_locality_container_roots_prevents_cross_service_knot(self) -> None:
        """Finding 4: Microservices under services/ must not match un-scoped aliases in sibling services."""
        files = (
            FileRecord(
                rel_path="services/billing/src/db.py",
                module_id="services.billing.src.db",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=(),
            ),
            FileRecord(
                rel_path="services/auth/src/worker.py",
                module_id="services.auth.src.worker",
                disposition="ACTIVE_SOURCE",
                reason="supported_source_language",
                estimated_tokens=500,
                shannon_entropy=4.0,
                max_line_length=60,
                imports=("db",),
            ),
        )
        scan = ScanSummary("/tmp/services", files, 1000, 0, 0, 0.0, (), ())
        plan = plan_from_scan(scan, token_budget=16000)
        node_map = {n.scc_id: n for n in plan.condensation_nodes}

        # auth worker importing generic 'db' must NOT link to billing db
        assert "services.billing.src.db" not in node_map["services.auth.src.worker"].depends_on_sccs
        assert node_map["services.auth.src.worker"].wave == 0
        assert node_map["services.billing.src.db"].wave == 0




