"""Layer 2: Tarjan SCC Condensation, Bottom-Up Wave Assignment, and Token-Bounded Slice Planner."""

import json
import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from monorepo_triage.layer0_invariants import (
    validate_module_tokens,
    validate_token_budget,
)
from monorepo_triage.layer1_scanner import (
    _GO_STDLIB_TOP_DIRS,
    ScanSummary,
    _is_go_stdlib,
)

SliceStatus = Literal["READY", "OVERSIZED_COUPLED_KNOT", "OVERSIZED_SINGLE_MODULE"]


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
    token_budget: int = 16000


@dataclass(frozen=True)
class _RawSccItem:
    scc_id: str
    modules: tuple[str, ...]
    is_cyclic: bool
    total_tokens: int


class _MutableSliceBin:
    __slots__ = ("modules", "scc_ids", "slice_id", "status", "total_tokens", "wave")

    def __init__(
        self,
        slice_id: str,
        wave: int,
        scc_ids: list[str],
        modules: list[str],
        total_tokens: int,
        status: SliceStatus,
    ) -> None:
        self.slice_id = slice_id
        self.wave = wave
        self.scc_ids = scc_ids
        self.modules = modules
        self.total_tokens = total_tokens
        self.status = status


def _solve_tarjan_sccs(
    modules: dict[str, int],
    edges: dict[str, set[str]],
) -> list[tuple[str, ...]]:
    """Execute iterative, recursion-safe Tarjan SCC decomposition."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[tuple[str, ...]] = []

    for root_node in sorted(modules.keys()):
        if root_node in indices:
            continue
        call_stack = [(root_node, iter(sorted(edges.get(root_node, set()))))]
        indices[root_node] = index
        lowlink[root_node] = index
        index += 1
        stack.append(root_node)
        on_stack.add(root_node)

        while call_stack:
            u, neighbors = call_stack[-1]
            advanced = False
            for v in neighbors:
                if v not in modules:
                    continue
                if v not in indices:
                    indices[v] = index
                    lowlink[v] = index
                    index += 1
                    stack.append(v)
                    on_stack.add(v)
                    call_stack.append((v, iter(sorted(edges.get(v, set())))))
                    advanced = True
                    break
                elif v in on_stack:
                    lowlink[u] = min(lowlink[u], indices[v])
            if not advanced:
                call_stack.pop()
                if call_stack:
                    parent, _ = call_stack[-1]
                    lowlink[parent] = min(lowlink[parent], lowlink[u])
                if lowlink[u] == indices[u]:
                    scc: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        scc.append(w)
                        if w == u:
                            break
                    sccs.append(tuple(sorted(scc)))

    return sccs


def build_modernization_plan(
    modules: dict[str, int],
    edges: dict[str, set[str]] | dict[str, list[str]],
    token_budget: int = 16000,
) -> ModernizationPlan:
    """Build deterministic modernization plan from module weights and dependency edges."""
    valid_budget = validate_token_budget(token_budget)
    valid_modules = validate_module_tokens(modules)

    if not isinstance(edges, dict):
        raise TypeError(f"Expected dict for edges, got {type(edges).__name__}")

    # Sanitize and normalize edges to sets of valid modules
    clean_edges: dict[str, set[str]] = {}
    for mod in valid_modules:
        raw_deps = edges.get(mod, set())
        if isinstance(raw_deps, (str, bytes)) or not isinstance(raw_deps, Iterable):
            raise TypeError(
                f"Dependencies for {mod!r} must be an iterable of module IDs, got {type(raw_deps).__name__}"
            )
        clean_edges[mod] = {
            dep for dep in raw_deps if isinstance(dep, str) and dep in valid_modules
        }

    # 1. Tarjan SCC Condensation
    raw_sccs = _solve_tarjan_sccs(valid_modules, clean_edges)

    mod_to_scc: dict[str, str] = {}
    scc_meta: list[_RawSccItem] = []
    used_scc_ids: set[str] = set(valid_modules.keys())

    for scc_mods in raw_sccs:
        is_cyclic = len(scc_mods) > 1 or (
            len(scc_mods) == 1 and scc_mods[0] in clean_edges.get(scc_mods[0], set())
        )
        if len(scc_mods) == 1:
            scc_id = scc_mods[0]
        else:
            scc_id = "+".join(scc_mods)
            if scc_id in used_scc_ids:
                scc_id = f"cycle({'+'.join(scc_mods)})"
                suffix = 2
                while scc_id in used_scc_ids:
                    scc_id = f"cycle_{suffix}({'+'.join(scc_mods)})"
                    suffix += 1
            used_scc_ids.add(scc_id)
        total_tokens = sum(valid_modules[m] for m in scc_mods)
        for m in scc_mods:
            mod_to_scc[m] = scc_id
        scc_meta.append(
            _RawSccItem(
                scc_id=scc_id,
                modules=scc_mods,
                is_cyclic=is_cyclic,
                total_tokens=total_tokens,
            )
        )

    # 2. Dependency mapping between SCCs
    scc_deps: dict[str, tuple[str, ...]] = {}
    for item in scc_meta:
        deps: set[str] = set()
        for m in item.modules:
            for dep_mod in clean_edges.get(m, set()):
                dep_scc = mod_to_scc.get(dep_mod)
                if dep_scc and dep_scc != item.scc_id:
                    deps.add(dep_scc)
        scc_deps[item.scc_id] = tuple(sorted(deps))

    # 3. Iterative Bottom-Up Wave Assignment on Condensation DAG (Kahn 1962)
    wave_memo: dict[str, int] = {}
    for item in scc_meta:
        if item.scc_id in wave_memo:
            continue
        eval_stack: list[tuple[str, bool]] = [(item.scc_id, False)]
        while eval_stack:
            curr_id, processed = eval_stack.pop()
            if curr_id in wave_memo:
                continue
            curr_deps = scc_deps.get(curr_id, ())
            if not curr_deps:
                wave_memo[curr_id] = 0
            elif processed or all(d in wave_memo for d in curr_deps):
                wave_memo[curr_id] = 1 + max(wave_memo[d] for d in curr_deps)
            else:
                eval_stack.append((curr_id, True))
                for d in curr_deps:
                    if d not in wave_memo:
                        eval_stack.append((d, False))

    condensation_nodes: list[CondensationNode] = []
    for item in scc_meta:
        w = wave_memo[item.scc_id]
        condensation_nodes.append(
            CondensationNode(
                scc_id=item.scc_id,
                modules=item.modules,
                is_cyclic=item.is_cyclic,
                total_tokens=item.total_tokens,
                wave=w,
                depends_on_sccs=scc_deps[item.scc_id],
            )
        )

    condensation_nodes.sort(key=lambda n: (n.wave, -n.total_tokens, n.scc_id))

    # 4. Deterministic First-Fit Decreasing (FFD) Slice Packing per Wave
    waves: dict[int, list[CondensationNode]] = {}
    for node in condensation_nodes:
        waves.setdefault(node.wave, []).append(node)

    max_wave = max(waves.keys()) if waves else 0
    all_slices: list[ModernizationSlice] = []

    for w in range(max_wave + 1):
        wave_nodes = waves.get(w, [])
        if not wave_nodes:
            continue
        sorted_nodes = sorted(wave_nodes, key=lambda n: (-n.total_tokens, n.scc_id))
        min_wave_tokens = sorted_nodes[-1].total_tokens

        wave_bins: list[_MutableSliceBin] = []
        open_bins: list[_MutableSliceBin] = []

        for node in sorted_nodes:
            if node.total_tokens > valid_budget:
                slice_id = f"wave_{w}_slice_{len(wave_bins):02d}"
                status: SliceStatus = (
                    "OVERSIZED_COUPLED_KNOT"
                    if (node.is_cyclic or len(node.modules) > 1)
                    else "OVERSIZED_SINGLE_MODULE"
                )
                wave_bins.append(
                    _MutableSliceBin(
                        slice_id=slice_id,
                        wave=w,
                        scc_ids=[node.scc_id],
                        modules=list(node.modules),
                        total_tokens=node.total_tokens,
                        status=status,
                    )
                )
            else:
                placed = False
                for idx, b in enumerate(open_bins):
                    if b.total_tokens + node.total_tokens <= valid_budget:
                        b.scc_ids.append(node.scc_id)
                        b.modules.extend(node.modules)
                        b.total_tokens += node.total_tokens
                        if valid_budget - b.total_tokens < min_wave_tokens:
                            open_bins.pop(idx)
                        placed = True
                        break
                if not placed:
                    slice_id = f"wave_{w}_slice_{len(wave_bins):02d}"
                    new_bin = _MutableSliceBin(
                        slice_id=slice_id,
                        wave=w,
                        scc_ids=[node.scc_id],
                        modules=list(node.modules),
                        total_tokens=node.total_tokens,
                        status="READY",
                    )
                    wave_bins.append(new_bin)
                    if valid_budget - new_bin.total_tokens >= min_wave_tokens:
                        open_bins.append(new_bin)

        for b in wave_bins:
            all_slices.append(
                ModernizationSlice(
                    slice_id=b.slice_id,
                    wave=b.wave,
                    scc_ids=tuple(sorted(b.scc_ids)),
                    modules=tuple(sorted(b.modules)),
                    total_tokens=b.total_tokens,
                    status=b.status,
                )
            )

    total_active_tokens = sum(n.total_tokens for n in condensation_nodes)
    cyclic_knot_count = sum(1 for n in condensation_nodes if n.is_cyclic)

    return ModernizationPlan(
        condensation_nodes=tuple(condensation_nodes),
        slices=tuple(all_slices),
        cyclic_knot_count=cyclic_knot_count,
        max_wave_depth=max_wave,
        total_active_tokens=total_active_tokens,
        token_budget=valid_budget,
    )


SOURCE_ROOT_MARKERS: tuple[str, ...] = (
    "src.main.java.",
    "src.test.java.",
    "src.main.kotlin.",
    "src.",
    "lib.",
)


_CONTAINER_ROOT_DIRS: frozenset[str] = frozenset(
    {"services", "packages", "apps", "libs", "modules"}
)


def _shared_prefix_segments(mod_a: str, mod_b: str) -> int:
    """Count shared leading dot-delimited package segments between two module IDs."""
    parts_a = mod_a.split(".")
    parts_b = mod_b.split(".")
    shared = 0
    for pa, pb in zip(parts_a[:-1], parts_b[:-1]):
        if pa == pb:
            shared += 1
        else:
            break
    if shared == 1 and parts_a and parts_a[0] in _CONTAINER_ROOT_DIRS:
        return 0
    return shared


def _is_unintended_cross_service_alias(self_mod_id: str, cand: str, imp: str) -> bool:
    parts_a = self_mod_id.split(".")
    parts_b = cand.split(".")
    if (
        len(parts_a) >= 2
        and len(parts_b) >= 2
        and parts_a[0] == parts_b[0]
        and parts_a[0] in _CONTAINER_ROOT_DIRS
        and parts_a[1] != parts_b[1]
    ):
        imp_parts = set(imp.replace("/", ".").split("."))
        if parts_b[1] not in imp_parts:
            return True
    return False


def _filter_by_locality(
    self_mod_id: str,
    candidates: set[str],
    imp: str = "",
) -> set[str]:
    """Resolve ambiguous multi-service aliases to candidate(s) sharing closest package root, rejecting unintended cross-service collisions."""
    valid_cands = {
        cand
        for cand in candidates
        if not _is_unintended_cross_service_alias(self_mod_id, cand, imp)
    }
    if len(valid_cands) <= 1:
        return valid_cands
    scored = [(cand, _shared_prefix_segments(self_mod_id, cand)) for cand in valid_cands]
    max_shared = max(score for _, score in scored)
    if max_shared > 0:
        return {cand for cand, score in scored if score == max_shared}
    return valid_cands


def _resolve_import_targets(
    imp: str,
    self_mod_id: str,
    active_module_set: set[str],
    alias_to_targets: dict[str, set[str]],
    go_dir_to_modules: dict[str, set[str]],
    package_barrel_modules: set[str] | None = None,
    java_pkg_to_modules: dict[str, set[str]] | None = None,
) -> set[str]:
    """Resolve an import string to one or more known internal module_ids across polyglot layouts."""
    resolved: set[str] = set()
    barrels = package_barrel_modules or set()
    java_pkgs = java_pkg_to_modules or {}

    # 0. Reject Go standard library imports early
    if _is_go_stdlib(imp):
        return resolved

    # 1. Java wildcard package match (e.g. 'import com.acme.models.*')
    if imp in java_pkgs:
        for target_mod in java_pkgs[imp]:
            if target_mod != self_mod_id:
                resolved.add(target_mod)
        if resolved:
            return resolved

    # 2. Go package path suffix matching (e.g. 'github.com/acme/repo/pkg/db' -> 'pkg/db')
    if "/" in imp and not imp.startswith("."):
        slash_parts = imp.split("/")
        for i in range(len(slash_parts)):
            sub_dir = "/".join(slash_parts[i:])
            if sub_dir in go_dir_to_modules:
                dir_mods = go_dir_to_modules[sub_dir]
                if self_mod_id in dir_mods:
                    continue
                for target_mod in dir_mods:
                    resolved.add(target_mod)
                if resolved:
                    return resolved

    # 3. Direct module or alias match (including barrel index.ts and nested src/ layouts)
    if imp in active_module_set:
        if imp != self_mod_id and not (imp in barrels and self_mod_id.startswith(imp + ".")):
            resolved.add(imp)
        return resolved
    if imp in alias_to_targets:
        cands = {
            t
            for t in alias_to_targets[imp]
            if t != self_mod_id and not (t in barrels and self_mod_id.startswith(t + "."))
        }
        return _filter_by_locality(self_mod_id, cands, imp)

    # 4. Single-level symbol stripping (e.g. 'pkg.service.UserService' -> 'pkg.service')
    if "." in imp:
        parent_cand = imp.rsplit(".", 1)[0]
        if parent_cand in barrels and self_mod_id.startswith(parent_cand + "."):
            return resolved
        if parent_cand in active_module_set and parent_cand != self_mod_id:
            resolved.add(parent_cand)
            return resolved
        if parent_cand in alias_to_targets:
            cands = {
                t
                for t in alias_to_targets[parent_cand]
                if t != self_mod_id and not (t in barrels and self_mod_id.startswith(t + "."))
            }
            return _filter_by_locality(self_mod_id, cands, imp)

    return resolved


def _register_alias(
    alias: str,
    target_mod: str,
    active_module_set: set[str],
    alias_to_targets: dict[str, set[str]],
) -> None:
    if alias and alias not in active_module_set:
        alias_to_targets.setdefault(alias, set()).add(target_mod)
    if alias.endswith(".index"):
        barrel = alias[: -len(".index")]
        if barrel and barrel not in active_module_set:
            alias_to_targets.setdefault(barrel, set()).add(target_mod)


def plan_from_scan(
    scan_summary: ScanSummary,
    token_budget: int = 16000,
) -> ModernizationPlan:
    """Derive modernization plan directly from Layer 1 scan summary, conserving tokens across colliding module IDs."""
    active_files = [
        f for f in scan_summary.files if f.disposition == "ACTIVE_SOURCE" and f.module_id
    ]
    modules: dict[str, int] = {}
    for f in active_files:
        assert f.module_id is not None
        modules[f.module_id] = modules.get(f.module_id, 0) + f.estimated_tokens
    active_module_set = set(modules.keys())

    BARREL_NAMES = frozenset(
        {"__init__.py", "index.ts", "index.tsx", "index.js", "index.jsx"}
    )
    package_barrel_modules: set[str] = set()
    for f in active_files:
        assert f.module_id is not None
        fname = posixpath.basename(f.rel_path)
        if fname in BARREL_NAMES or f.rel_path.endswith(
            ("/__init__.py", "/index.ts", "/index.tsx", "/index.js", "/index.jsx")
        ):
            package_barrel_modules.add(f.module_id)
            if f.module_id.endswith(".index"):
                package_barrel_modules.add(f.module_id[: -len(".index")])

    alias_to_targets: dict[str, set[str]] = {}
    for mod_id in sorted(active_module_set):
        # TypeScript / JS barrel index resolution (src.auth.index -> src.auth)
        if mod_id.endswith(".index"):
            barrel_prefix = mod_id[: -len(".index")]
            _register_alias(barrel_prefix, mod_id, active_module_set, alias_to_targets)

        # Root and nested monorepo source-root prefixes
        for marker in SOURCE_ROOT_MARKERS:
            if mod_id.startswith(marker):
                stripped = mod_id[len(marker) :]
                _register_alias(stripped, mod_id, active_module_set, alias_to_targets)
            nested_marker = "." + marker
            if nested_marker in mod_id:
                idx = mod_id.find(nested_marker)
                stripped = mod_id[idx + len(nested_marker) :]
                _register_alias(stripped, mod_id, active_module_set, alias_to_targets)
                prefix_before = mod_id[:idx]
                pkg = prefix_before.rsplit(".", 1)[-1]
                if pkg and stripped:
                    _register_alias(f"{pkg}.{stripped}", mod_id, active_module_set, alias_to_targets)
                    if stripped == "index":
                        _register_alias(pkg, mod_id, active_module_set, alias_to_targets)

    go_dir_to_modules: dict[str, set[str]] = {}
    for f in active_files:
        if f.rel_path.endswith(".go") and f.module_id:
            rel_dir = f.rel_path.rsplit("/", 1)[0] if "/" in f.rel_path else "."
            go_dir_to_modules.setdefault(rel_dir, set()).add(f.module_id)
            if "/" in rel_dir:
                dir_segs = rel_dir.split("/")
                for i in range(1, len(dir_segs)):
                    sub_seg = "/".join(dir_segs[i:])
                    if (len(dir_segs) - i >= 2) or (sub_seg not in _GO_STDLIB_TOP_DIRS):
                        go_dir_to_modules.setdefault(sub_seg, set()).add(f.module_id)

    java_pkg_to_modules: dict[str, set[str]] = {}
    for f in active_files:
        if f.rel_path.endswith(".java") and f.module_id and "." in f.module_id:
            java_pkg = f.module_id.rsplit(".", 1)[0]
            java_pkg_to_modules.setdefault(java_pkg, set()).add(f.module_id)
            for marker in SOURCE_ROOT_MARKERS:
                nested_marker = "." + marker
                if nested_marker in java_pkg:
                    idx = java_pkg.find(nested_marker)
                    stripped_pkg = java_pkg[idx + len(nested_marker) :]
                    java_pkg_to_modules.setdefault(stripped_pkg, set()).add(f.module_id)
                elif java_pkg.startswith(marker):
                    stripped_pkg = java_pkg[len(marker) :]
                    java_pkg_to_modules.setdefault(stripped_pkg, set()).add(f.module_id)

    edges: dict[str, set[str]] = {mod_id: set() for mod_id in active_module_set}
    for f in active_files:
        assert f.module_id is not None
        deps = edges[f.module_id]
        for imp in f.imports:
            targets = _resolve_import_targets(
                imp,
                f.module_id,
                active_module_set,
                alias_to_targets,
                go_dir_to_modules,
                package_barrel_modules=package_barrel_modules,
                java_pkg_to_modules=java_pkg_to_modules,
            )
            deps.update(targets)

    return build_modernization_plan(modules, edges, token_budget=token_budget)


def export_neo4j_cypher(plan: ModernizationPlan) -> str:
    """Export the condensation DAG and wave schedule as deterministic Neo4j Cypher statements."""
    lines: list[str] = []
    for idx, node in enumerate(plan.condensation_nodes):
        var = f"s{idx}"
        scc_lit = json.dumps(node.scc_id)
        mods_lit = json.dumps(list(node.modules))
        cyc_lit = "true" if node.is_cyclic else "false"
        lines.append(
            f"MERGE ({var}:CondensationNode {{scc_id: {scc_lit}}}) "
            f"SET {var}.wave = {node.wave}, {var}.is_cyclic = {cyc_lit}, "
            f"{var}.total_tokens = {node.total_tokens}, {var}.modules = {mods_lit};"
        )
    for node in plan.condensation_nodes:
        src_lit = json.dumps(node.scc_id)
        for dep_id in node.depends_on_sccs:
            dst_lit = json.dumps(dep_id)
            lines.append(
                f"MATCH (a:CondensationNode {{scc_id: {src_lit}}}), "
                f"(b:CondensationNode {{scc_id: {dst_lit}}}) "
                f"MERGE (a)-[:DEPENDS_ON]->(b);"
            )
    return "\n".join(lines)


def render_agent_action_plan_markdown(
    scan_summary: ScanSummary,
    plan: ModernizationPlan,
    token_budget: int | None = None,
) -> str:
    """Render a human-in-the-loop Technical Specification and Agent Action Plan gate in Markdown."""
    budget = plan.token_budget if token_budget is None else token_budget
    valid_budget = validate_token_budget(budget)
    pruned_count = sum(1 for f in scan_summary.files if f.disposition == "PRUNED_BLOAT")
    quarantined_files = [
        f.rel_path for f in scan_summary.files if f.disposition == "QUARANTINED_DLP"
    ]
    active_count = sum(1 for f in scan_summary.files if f.disposition == "ACTIVE_SOURCE")
    waves_str = (
        f"{plan.max_wave_depth + 1} (Waves 0..{plan.max_wave_depth})"
        if plan.condensation_nodes
        else "0"
    )

    out: list[str] = [
        "# Pre-Execution Technical Specification & Agent Action Plan",
        "",
        "## 1. Repository Ingestion & Context Reduction Summary",
        f"- **Active Source Modules:** {active_count} files ({scan_summary.active_tokens:,} tokens)",
        f"- **Pruned Bloat Artifacts:** {pruned_count} files ({scan_summary.pruned_tokens:,} tokens)",
        f"- **Context Reduction Ratio:** {scan_summary.token_reduction_ratio * 100:.2f}%",
        f"- **DLP Quarantined Files:** {len(quarantined_files)} ({scan_summary.quarantined_tokens:,} tokens)",
        f"- **Recommended Directory Exclusions:** {', '.join(scan_summary.recommended_exclusions) or 'None'}",
        f"- **Circular Dependency Knots (Tarjan SCCs):** {plan.cyclic_knot_count}",
        f"- **Bottom-Up Modernization Waves:** {waves_str}",
        f"- **Per-Agent Slice Token Ceiling:** {valid_budget:,} tokens",
        "",
        "## 2. Wave-Ordered Parallel Agent Swarm Schedule",
    ]

    if quarantined_files:
        out.append("")
        out.append("### Pre-Flight Security Gate: Quarantined DLP Files")
        for q_path in quarantined_files:
            out.append(f"- `{q_path}` (blocked from agent context)")

    waves: dict[int, list[ModernizationSlice]] = {}
    for sl in plan.slices:
        waves.setdefault(sl.wave, []).append(sl)

    for w in sorted(waves.keys()):
        w_slices = waves[w]
        ready_agents = sum(1 for s in w_slices if s.status == "READY")
        blocked_knots = sum(1 for s in w_slices if s.status == "OVERSIZED_COUPLED_KNOT")
        out.append("")
        out.append(
            f"### Wave {w} (Max Parallel Agent Workers: {ready_agents} | "
            f"Human Seam-Carving Gates: {blocked_knots})"
        )
        for sl in w_slices:
            mods_str = ", ".join(f"`{m}`" for m in sl.modules)
            out.append(
                f"- **{sl.slice_id}** [{sl.status}] ({sl.total_tokens:,} / {valid_budget:,} tokens): {mods_str}"
            )

    return "\n".join(out)
