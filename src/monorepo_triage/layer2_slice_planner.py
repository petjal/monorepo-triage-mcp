"""Layer 2: Tarjan SCC Condensation, Bottom-Up Wave Assignment, and Token-Bounded Slice Planner."""

import json
from dataclasses import dataclass
from typing import Literal

from monorepo_triage.layer0_invariants import (
    validate_module_tokens,
    validate_token_budget,
)
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


@dataclass(frozen=True)
class _RawSccItem:
    scc_id: str
    modules: tuple[str, ...]
    is_cyclic: bool
    total_tokens: int


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

    # Sanitize and normalize edges to sets of valid modules
    clean_edges: dict[str, set[str]] = {}
    for mod in valid_modules:
        raw_deps = edges.get(mod, set())
        clean_edges[mod] = {dep for dep in raw_deps if dep in valid_modules}

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
    # Tarjan emits SCCs in reverse topological order (leaves first), and we also
    # guard with an explicit iterative post-order stack so arbitrary ordering never recurses.
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
        # Order SCCs by (-total_tokens, scc_id)
        sorted_nodes = sorted(wave_nodes, key=lambda n: (-n.total_tokens, n.scc_id))

        wave_slices: list[ModernizationSlice] = []

        for node in sorted_nodes:
            if node.total_tokens > valid_budget:
                slice_id = f"wave_{w}_slice_{len(wave_slices):02d}"
                wave_slices.append(
                    ModernizationSlice(
                        slice_id=slice_id,
                        wave=w,
                        scc_ids=(node.scc_id,),
                        modules=node.modules,
                        total_tokens=node.total_tokens,
                        status="OVERSIZED_COUPLED_KNOT",
                    )
                )
            else:
                placed = False
                for idx, s in enumerate(wave_slices):
                    if s.status == "READY" and (s.total_tokens + node.total_tokens <= valid_budget):
                        new_scc_ids = tuple(sorted(s.scc_ids + (node.scc_id,)))
                        new_modules = tuple(sorted(s.modules + node.modules))
                        new_tokens = s.total_tokens + node.total_tokens
                        wave_slices[idx] = ModernizationSlice(
                            slice_id=s.slice_id,
                            wave=w,
                            scc_ids=new_scc_ids,
                            modules=new_modules,
                            total_tokens=new_tokens,
                            status="READY",
                        )
                        placed = True
                        break
                if not placed:
                    slice_id = f"wave_{w}_slice_{len(wave_slices):02d}"
                    wave_slices.append(
                        ModernizationSlice(
                            slice_id=slice_id,
                            wave=w,
                            scc_ids=(node.scc_id,),
                            modules=node.modules,
                            total_tokens=node.total_tokens,
                            status="READY",
                        )
                    )

        all_slices.extend(wave_slices)

    total_active_tokens = sum(n.total_tokens for n in condensation_nodes)
    cyclic_knot_count = sum(1 for n in condensation_nodes if n.is_cyclic)

    return ModernizationPlan(
        condensation_nodes=tuple(condensation_nodes),
        slices=tuple(all_slices),
        cyclic_knot_count=cyclic_knot_count,
        max_wave_depth=max_wave,
        total_active_tokens=total_active_tokens,
    )


SOURCE_ROOT_MARKERS: tuple[str, ...] = (
    "src.main.java.",
    "src.test.java.",
    "src.main.kotlin.",
    "src.",
    "lib.",
)


def _resolve_import_targets(
    imp: str,
    self_mod_id: str,
    active_module_set: set[str],
    alias_to_targets: dict[str, set[str]],
    go_dir_to_modules: dict[str, set[str]],
) -> set[str]:
    """Resolve an import string to one or more known internal module_ids across polyglot layouts."""
    resolved: set[str] = set()

    # 1. Go package path suffix matching (e.g. 'github.com/acme/repo/pkg/db' -> 'pkg/db')
    if "/" in imp and not imp.startswith("."):
        slash_parts = imp.split("/")
        for i in range(len(slash_parts)):
            sub_dir = "/".join(slash_parts[i:])
            if sub_dir in go_dir_to_modules:
                for target_mod in go_dir_to_modules[sub_dir]:
                    if target_mod != self_mod_id:
                        resolved.add(target_mod)
                if resolved:
                    return resolved

    # 2. Direct module or alias match (including barrel index.ts and nested src/ layouts)
    if imp in active_module_set:
        if imp != self_mod_id:
            resolved.add(imp)
        return resolved
    if imp in alias_to_targets:
        for target_mod in alias_to_targets[imp]:
            if target_mod != self_mod_id:
                resolved.add(target_mod)
        return resolved

    # 3. Single-level symbol stripping (e.g. 'pkg.service.UserService' -> 'pkg.service')
    if "." in imp:
        parent_cand = imp.rsplit(".", 1)[0]
        # Avoid false child -> parent __init__.py cycles when a submodule imports an unknown symbol
        # from its own parent package namespace (e.g. pkg.service importing pkg.UNKNOWN_CONST).
        if self_mod_id.startswith(parent_cand + "."):
            return resolved
        if parent_cand in active_module_set and parent_cand != self_mod_id:
            resolved.add(parent_cand)
            return resolved
        if parent_cand in alias_to_targets:
            for target_mod in alias_to_targets[parent_cand]:
                if target_mod != self_mod_id and not self_mod_id.startswith(target_mod + "."):
                    resolved.add(target_mod)
            return resolved

    return resolved


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

    alias_to_targets: dict[str, set[str]] = {}
    for mod_id in sorted(active_module_set):
        # TypeScript / JS barrel index resolution (src.auth.index -> src.auth)
        if mod_id.endswith(".index"):
            barrel_prefix = mod_id[: -len(".index")]
            if barrel_prefix and barrel_prefix not in active_module_set:
                alias_to_targets.setdefault(barrel_prefix, set()).add(mod_id)

        # Root and nested monorepo source-root prefixes (src., packages.core.src., billing.src.main.java.)
        for marker in SOURCE_ROOT_MARKERS:
            if mod_id.startswith(marker):
                stripped = mod_id[len(marker) :]
                if stripped and stripped not in active_module_set:
                    alias_to_targets.setdefault(stripped, set()).add(mod_id)
            nested_marker = "." + marker
            if nested_marker in mod_id:
                idx = mod_id.find(nested_marker)
                stripped = mod_id[idx + len(nested_marker) :]
                if stripped and stripped not in active_module_set:
                    alias_to_targets.setdefault(stripped, set()).add(mod_id)

    go_dir_to_modules: dict[str, set[str]] = {}
    for f in active_files:
        if f.rel_path.endswith(".go") and f.module_id:
            rel_dir = f.rel_path.rsplit("/", 1)[0] if "/" in f.rel_path else "."
            go_dir_to_modules.setdefault(rel_dir, set()).add(f.module_id)

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
            )
            deps.update(targets)

    return build_modernization_plan(modules, edges, token_budget=token_budget)


def export_neo4j_cypher(plan: ModernizationPlan) -> str:
    """Export the condensation DAG and wave schedule as deterministic Neo4j Cypher statements."""
    lines: list[str] = []
    for node in plan.condensation_nodes:
        scc_lit = json.dumps(node.scc_id)
        mods_lit = json.dumps(list(node.modules))
        cyc_lit = "true" if node.is_cyclic else "false"
        lines.append(
            f"MERGE (n:CondensationNode {{scc_id: {scc_lit}}}) "
            f"SET n.wave = {node.wave}, n.is_cyclic = {cyc_lit}, "
            f"n.total_tokens = {node.total_tokens}, n.modules = {mods_lit};"
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
    token_budget: int = 16000,
) -> str:
    """Render a human-in-the-loop Technical Specification and Agent Action Plan gate in Markdown."""
    valid_budget = validate_token_budget(token_budget)
    pruned_count = sum(1 for f in scan_summary.files if f.disposition == "PRUNED_BLOAT")
    quarantined_files = [
        f.rel_path for f in scan_summary.files if f.disposition == "QUARANTINED_DLP"
    ]
    active_count = sum(1 for f in scan_summary.files if f.disposition == "ACTIVE_SOURCE")

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
        f"- **Bottom-Up Modernization Waves:** {plan.max_wave_depth + 1 if plan.condensation_nodes else 0} (Waves 0..{plan.max_wave_depth})",
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

