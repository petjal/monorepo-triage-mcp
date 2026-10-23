"""Tests for Layer 2: Tarjan SCC Condensation, DAG Wave Assignment, and Slice Bin-Packing."""

from monorepo_triage.layer1_scanner import FileRecord, ScanSummary
from monorepo_triage.layer2_slice_planner import (
    build_modernization_plan,
    plan_from_scan,
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
        }
        edges: dict[str, set[str]] = {
            "monolith.heavy": set(),
            "light.helper": set(),
        }

        plan = build_modernization_plan(modules, edges, token_budget=16000)
        oversized = [s for s in plan.slices if s.status == "OVERSIZED_COUPLED_KNOT"]
        assert len(oversized) == 1
        assert oversized[0].modules == ("monolith.heavy",)
        assert oversized[0].total_tokens == 25000

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


