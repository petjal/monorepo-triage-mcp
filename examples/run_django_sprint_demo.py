#!/usr/bin/env python3
"""End-to-End Blitzy 80/20 Enterprise Sprint PoC Demo on a Legacy Django Subsystem.

What is Live Execution vs. Offline Deterministic Replay in this script:
  - Stage 1 & 2 (Live Engine): Seeds a 9-file miniature Django workspace (7 untyped Python
    modules, 1 vendored node_modules bundle, 1 PEM private key) and executes the real
    `monorepo-triage-mcp` scanner and Tarjan/Kahn wave planner.
  - Stage 2.5 (Live Counterfactual Proof): Runs the real `mypy --strict` compiler on Wave 2
    (`validators.py`) BEFORE Wave 0 (`ipv6.py`, `regex_helper.py`) is modernized, proving
    why out-of-order agent execution fails type-checking (`[no-untyped-call]`).
  - Stage 3 (Offline Wave Replay + Live `mypy --strict` Judge): Replays deterministic
    pre-computed wave patches (`OFFLINE_WAVE_REPLAY_PATCHES` — used so this demo runs 100%
    offline in <1s without external LLM API keys) in strict bottom-up order (`Wave 0..3`).
    At the end of each wave, an isolated Judge runs REAL `mypy --strict` (`mypy.api.run`)
    and AST signature verification on all modernized waves, then re-scans the repository
    to verify `cyclic_knot_count` dropped from 1 -> 0 across all 4 waves.
  - Stage 4 (20% Human Last-Mile Handoff): Emits the 3 items deferred for human engineers.
"""

from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mypy import api as mypy_api

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from monorepo_triage.layer1_scanner import scan_repository
from monorepo_triage.layer2_slice_planner import (
    export_neo4j_cypher,
    plan_from_scan,
    render_agent_action_plan_markdown,
)

# ---------------------------------------------------------------------------
# 1. Seed a 9-file legacy untyped Django subsystem (Before 80% Sprint Run)
#    Every import is genuinely called at runtime so ruff & mypy see real edges.
# ---------------------------------------------------------------------------
LEGACY_DJANGO_FILES: dict[str, str] = {
    # Wave 0: Leaf utility modules (untyped legacy Python)
    "django/utils/regex_helper.py": (
        "def _lazy_re_compile(regex, flags=0):\n"
        "    return f'{regex}:{flags}'\n"
    ),
    "django/utils/ipv6.py": (
        "def clean_ipv6_address(ip_str, unpack_ipv4=False):\n"
        "    prefix = 'v4:' if unpack_ipv4 else 'v6:'\n"
        "    return prefix + ip_str.strip().lower()\n"
    ),
    # Wave 1: Circular Dependency Knot (functional.py <-> deprecation.py, depending on Wave 0 regex_helper)
    "django/utils/functional.py": (
        "from django.utils import deprecation, regex_helper\n\n\n"
        "class LazyObject:\n"
        "    def __init__(self, wrapped=None):\n"
        "        self._wrapped = wrapped\n"
        "        self.compiled_tag = regex_helper._lazy_re_compile('lazy', 0)\n\n\n"
        "def unwrap_or_warn(obj):\n"
        "    if isinstance(obj, LazyObject) and obj._wrapped is not None:\n"
        "        return str(obj._wrapped)\n"
        "    return deprecation.warn_legacy_arg('empty_lazy_object')\n"
    ),
    "django/utils/deprecation.py": (
        "from django.utils import functional\n\n\n"
        "def warn_legacy_arg(name):\n"
        "    return f'RemovedInNextVersionWarning:{name}'\n\n\n"
        "class MiddlewareMixin:\n"
        "    def __init__(self, handler):\n"
        "        self.handler = functional.LazyObject(handler)\n"
    ),
    # Wave 2: Core Validators (depends on Wave 0 ipv6/regex_helper + Wave 1 functional)
    "django/core/validators.py": (
        "from django.utils import functional, ipv6, regex_helper\n\n\n"
        "class URLValidator:\n"
        "    def __init__(self, scheme='https'):\n"
        "        self.scheme = scheme\n"
        "        self.rule = regex_helper._lazy_re_compile(scheme, 1)\n\n"
        "    def validate_host(self, value):\n"
        "        cleaned = ipv6.clean_ipv6_address(value, False)\n"
        "        wrapped = functional.LazyObject(cleaned)\n"
        "        return functional.unwrap_or_warn(wrapped)\n"
    ),
    # Wave 3: Top-Level Postgres Fields (depends on Wave 1 + Wave 2)
    "django/contrib/postgres/fields/array.py": (
        "from django.core import validators\n"
        "from django.utils import functional\n\n\n"
        "class ArrayField:\n"
        "    def __init__(self, host_hint, size=1):\n"
        "        self.validator = validators.URLValidator('https')\n"
        "        self.normalized_host = self.validator.validate_host(host_hint)\n"
        "        self.lazy_state = functional.LazyObject(self.normalized_host)\n"
        "        self.size = size\n"
    ),
    "django/contrib/postgres/fields/ranges.py": (
        "from django.core import validators\n"
        "from django.utils import deprecation\n\n\n"
        "class DateTimeRangeField:\n"
        "    def __init__(self, default_bounds='[)'):\n"
        "        self.default_bounds = default_bounds\n"
        "        self.validator = validators.URLValidator('postgres')\n\n"
        "    def validate_bounds(self, lower, upper):\n"
        "        if lower == upper and self.default_bounds == '[)':\n"
        "            return deprecation.warn_legacy_arg('DegenerateRangeBounds')\n"
        "        return f'{self.default_bounds}:{self.validator.validate_host(lower)}..{upper}'\n"
    ),
    # Bloat & DLP Artifacts that must be filtered before AI agent ingestion
    "node_modules/admin-ui/bundle.js": ("export const v = 1;\n" * 400),
    "tests/postgres_tests/legacy_test_key.pem": (
        "-----BEGIN RSA "
        + "PRIVATE KEY-----\n"
        + "MIIEowIBAAKCAQEA0m59...\n"
        + "-----END RSA "
        + "PRIVATE KEY-----\n"
    ),
}

# ---------------------------------------------------------------------------
# 2. Offline Wave Replay Patches (Strict PEP 484 Types + Wave 1 Cycle Seam Carved)
#    In Wave 1, functional.py decouples its back-edge to deprecation.py, breaking
#    the circular dependency knot while keeping all 4 waves (0..3) intact.
# ---------------------------------------------------------------------------
OFFLINE_WAVE_REPLAY_PATCHES: dict[str, str] = {
    "django/utils/regex_helper.py": (
        "from __future__ import annotations\n\n\n"
        "def _lazy_re_compile(regex: str, flags: int = 0) -> str:\n"
        "    return f'{regex}:{flags}'\n"
    ),
    "django/utils/ipv6.py": (
        "from __future__ import annotations\n\n\n"
        "def clean_ipv6_address(ip_str: str, unpack_ipv4: bool = False) -> str:\n"
        "    prefix = 'v4:' if unpack_ipv4 else 'v6:'\n"
        "    return prefix + ip_str.strip().lower()\n"
    ),
    # Wave 1 Knot Decoupled: functional.py drops its back-edge to deprecation.py
    "django/utils/functional.py": (
        "from __future__ import annotations\n\n"
        "from django.utils import regex_helper\n\n\n"
        "class LazyObject:\n"
        "    def __init__(self, wrapped: str | None = None) -> None:\n"
        "        self._wrapped: str | None = wrapped\n"
        "        self.compiled_tag: str = regex_helper._lazy_re_compile('lazy', 0)\n\n\n"
        "def unwrap_or_warn(obj: LazyObject, fallback_label: str = 'empty_lazy_object') -> str:\n"
        "    if obj._wrapped is not None:\n"
        "        return obj._wrapped\n"
        "    return f'RemovedInNextVersionWarning:{fallback_label}'\n"
    ),
    "django/utils/deprecation.py": (
        "from __future__ import annotations\n\n"
        "from django.utils import functional\n\n\n"
        "def warn_legacy_arg(name: str) -> str:\n"
        "    return f'RemovedInNextVersionWarning:{name}'\n\n\n"
        "class MiddlewareMixin:\n"
        "    def __init__(self, handler: str) -> None:\n"
        "        self.handler: functional.LazyObject = functional.LazyObject(handler)\n"
    ),
    "django/core/validators.py": (
        "from __future__ import annotations\n\n"
        "from django.utils import functional, ipv6, regex_helper\n\n\n"
        "class URLValidator:\n"
        "    def __init__(self, scheme: str = 'https') -> None:\n"
        "        self.scheme: str = scheme\n"
        "        self.rule: str = regex_helper._lazy_re_compile(scheme, 1)\n\n"
        "    def validate_host(self, value: str) -> str:\n"
        "        cleaned = ipv6.clean_ipv6_address(value, False)\n"
        "        wrapped = functional.LazyObject(cleaned)\n"
        "        return functional.unwrap_or_warn(wrapped)\n"
    ),
    "django/contrib/postgres/fields/array.py": (
        "from __future__ import annotations\n\n"
        "from django.core import validators\n"
        "from django.utils import functional\n\n\n"
        "class ArrayField:\n"
        "    def __init__(self, host_hint: str, size: int = 1) -> None:\n"
        "        self.validator: validators.URLValidator = validators.URLValidator('https')\n"
        "        self.normalized_host: str = self.validator.validate_host(host_hint)\n"
        "        self.lazy_state: functional.LazyObject = functional.LazyObject(self.normalized_host)\n"
        "        self.size: int = size\n"
    ),
    "django/contrib/postgres/fields/ranges.py": (
        "from __future__ import annotations\n\n"
        "from django.core import validators\n"
        "from django.utils import deprecation\n\n\n"
        "class DateTimeRangeField:\n"
        "    def __init__(self, default_bounds: str = '[)') -> None:\n"
        "        self.default_bounds: str = default_bounds\n"
        "        self.validator: validators.URLValidator = validators.URLValidator('postgres')\n\n"
        "    def validate_bounds(self, lower: str, upper: str) -> str:\n"
        "        # [HUMAN-20%-GATE]: Confirm whether lower == upper under exclusive bounds '[)'\n"
        "        # should raise django.core.exceptions.ValidationError or return deprecation warning.\n"
        "        if lower == upper and self.default_bounds == '[)':\n"
        "            return deprecation.warn_legacy_arg('DegenerateRangeBounds')\n"
        "        return f'{self.default_bounds}:{self.validator.validate_host(lower)}..{upper}'\n"
    ),
}


def judge_verify_ast_annotations(source_text: str) -> tuple[bool, int, int]:
    """Check via AST that every function/method has full argument and return type annotations."""
    tree = ast.parse(source_text)
    total_funcs = 0
    fully_typed_funcs = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            total_funcs += 1
            non_self_args = [a for a in node.args.args if a.arg != "self"]
            has_all_arg_types = all(a.annotation is not None for a in non_self_args)
            has_return_type = node.returns is not None
            if has_all_arg_types and has_return_type:
                fully_typed_funcs += 1
    return (total_funcs > 0 and total_funcs == fully_typed_funcs), fully_typed_funcs, total_funcs


def judge_run_mypy_strict(
    root: Path,
    rel_paths: list[str],
    follow_imports: str = "normal",
) -> tuple[bool, str]:
    """Isolated Judge Agent: Execute real `mypy --strict` against the specified files."""
    old_mypypath = os.environ.get("MYPYPATH")
    os.environ["MYPYPATH"] = str(root)
    try:
        targets = [str(root / p) for p in rel_paths]
        args = [
            "--strict",
            "--explicit-package-bases",
            "--no-color-output",
            f"--follow-imports={follow_imports}",
            *targets,
        ]
        stdout, stderr, exit_code = mypy_api.run(args)
        summary = (stdout + stderr).strip().splitlines()[-1] if (stdout or stderr) else ""
        return exit_code == 0, summary
    finally:
        if old_mypypath is None:
            os.environ.pop("MYPYPATH", None)
        else:
            os.environ["MYPYPATH"] = old_mypypath


def run_enterprise_sprint_demo() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel_path, content in LEGACY_DJANGO_FILES.items():
            full_path = root / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Stage 1 & 2: Live Pre-Flight Triage & Wave Planning
        scan = scan_repository(root)
        plan = plan_from_scan(scan, token_budget=4000)
        action_plan_md = render_agent_action_plan_markdown(scan, plan, token_budget=4000)
        cypher = export_neo4j_cypher(plan)

        mod_to_rel_path = {
            f.module_id: f.rel_path
            for f in scan.files
            if f.disposition == "ACTIVE_SOURCE" and f.module_id
        }
        cyclic_scc_ids = {n.scc_id for n in plan.condensation_nodes if n.is_cyclic}

        before_typed_funcs = 0
        before_total_funcs = 0
        for f in scan.files:
            if f.disposition == "ACTIVE_SOURCE":
                _, typed_f, tot_f = judge_verify_ast_annotations((root / f.rel_path).read_text())
                before_typed_funcs += typed_f
                before_total_funcs += tot_f

        # Stage 2.5: Out-of-Order Counterfactual Proof
        # Prove that modernizing Wave 2 (validators.py) BEFORE Wave 0/1 fails real mypy --strict
        val_rel = "django/core/validators.py"
        original_val = (root / val_rel).read_text()
        (root / val_rel).write_text(OFFLINE_WAVE_REPLAY_PATCHES[val_rel])
        out_of_order_passed, out_of_order_msg = judge_run_mypy_strict(
            root, [val_rel], follow_imports="silent"
        )
        (root / val_rel).write_text(original_val)

        # Stage 3: Execute Bottom-Up Wave Replay (Wave 0 -> Wave 3) + Real mypy --strict Judge
        modernized_so_far: list[str] = []
        wave_execution_log: list[dict[str, Any]] = []
        for sl in plan.slices:
            judge_results: list[dict[str, Any]] = []
            for mod_id in sl.modules:
                rel_p = mod_to_rel_path[mod_id]
                patch = OFFLINE_WAVE_REPLAY_PATCHES[rel_p]
                (root / rel_p).write_text(patch)
                modernized_so_far.append(rel_p)
                ast_ok, typed_cnt, total_cnt = judge_verify_ast_annotations(patch)
                judge_results.append(
                    {
                        "file": rel_p,
                        "ast_annotations_complete": ast_ok,
                        "typed_functions": f"{typed_cnt}/{total_cnt}",
                    }
                )
            mypy_ok, mypy_summary = judge_run_mypy_strict(root, modernized_so_far)
            wave_execution_log.append(
                {
                    "wave": sl.wave,
                    "slice_id": sl.slice_id,
                    "contains_cyclic_knot": any(s in cyclic_scc_ids for s in sl.scc_ids),
                    "modules_modernized": list(sl.modules),
                    "judge_mypy_strict_passed": mypy_ok,
                    "judge_mypy_summary": mypy_summary,
                    "judge_file_checks": judge_results,
                }
            )

        # Post-Sprint Rescan: Verify Wave 1 cycle is now 0 and 4-wave DAG depth is preserved
        scan_after = scan_repository(root)
        plan_after = plan_from_scan(scan_after, token_budget=4000)

        # Stage 4: Build the 'Final 20%' Human Engineer Handoff Manifest
        quarantined = [f.rel_path for f in scan.files if f.disposition == "QUARANTINED_DLP"]
        human_20_percent_handoff = [
            {
                "category": "DOMAIN_BUSINESS_POLICY_DECISION",
                "target": "django/contrib/postgres/fields/ranges.py (DateTimeRangeField.validate_bounds)",
                "why_ai_deferred": (
                    "Wave 3 patch added strict PEP 484 type annotations while preserving legacy "
                    "deprecation warning when lower == upper under exclusive bounds default_bounds='[)'. "
                    "Human domain owner must confirm whether degenerate bounds should raise "
                    "django.core.exceptions.ValidationError or coerce to an empty range."
                ),
            },
            {
                "category": "SECURITY_DLP_REMEDIATION",
                "target": quarantined[0] if quarantined else "tests/postgres_tests/legacy_test_key.pem",
                "why_ai_deferred": (
                    "Quarantined by Layer 1 DLP gate before LLM ingestion. Human engineer must replace "
                    "hardcoded RSA private key fixture with an ephemeral runtime key generator."
                ),
            },
            {
                "category": "ARCHITECTURAL_SEAM_SIGN_OFF",
                "target": "django/utils/functional.py <-> django/utils/deprecation.py (Wave 1 Cyclic Knot)",
                "why_ai_deferred": (
                    "Wave 1 patch decoupled functional.unwrap_or_warn from deprecation.warn_legacy_arg by inlining "
                    "the RemovedInNextVersionWarning format string, reducing cyclic_knot_count from 1 -> 0 while "
                    "preserving 100% identical runtime string output. Senior engineer should confirm whether "
                    "to extract this warning string to a shared leaf constants module."
                ),
            },
        ]

        after_typed_funcs = sum(
            int(item["typed_functions"].split("/")[0])
            for entry in wave_execution_log
            for item in entry["judge_file_checks"]
        )
        after_total_funcs = sum(
            int(item["typed_functions"].split("/")[1])
            for entry in wave_execution_log
            for item in entry["judge_file_checks"]
        )
        after_pct = (
            round((after_typed_funcs / after_total_funcs) * 100, 1)
            if after_total_funcs > 0
            else 0.0
        )

        return {
            "sprint_title": "Sprint 42: Django Legacy Utils & Postgres Fields Strict Type Modernization",
            "execution_mode_disclosure": (
                "Stages 1, 2, 2.5, and the post-sprint rescan execute live monorepo-triage-mcp "
                "and real mypy --strict. Stage 3 replays deterministic offline patches "
                "(OFFLINE_WAVE_REPLAY_PATCHES) in computed wave order so the demo runs without API keys."
            ),
            "stage1_preflight_summary": {
                "active_source_files": len(mod_to_rel_path),
                "active_tokens": scan.active_tokens,
                "pruned_bloat_tokens": scan.pruned_tokens,
                "quarantined_dlp_tokens": scan.quarantined_tokens,
                "token_reduction_pct": round(scan.token_reduction_ratio * 100, 2),
                "quarantined_dlp_files": quarantined,
                "cyclic_knots_detected_before": plan.cyclic_knot_count,
                "total_waves": plan.max_wave_depth + 1,
            },
            "stage2_action_plan_markdown": action_plan_md,
            "stage2_neo4j_cypher_lines": len(cypher.splitlines()),
            "stage2_5_out_of_order_counterfactual": {
                "target": "Wave 2 (django/core/validators.py) tested BEFORE Wave 0/1 modernized",
                "mypy_strict_passed": out_of_order_passed,
                "mypy_output": out_of_order_msg,
            },
            "stage3_autonomous_80_pct_execution": {
                "before_typed_functions": f"{before_typed_funcs}/{before_total_funcs} (0%)",
                "after_typed_functions": f"{after_typed_funcs}/{after_total_funcs} ({int(after_pct)}%)",
                "cyclic_knots_after_stage3": plan_after.cyclic_knot_count,
                "waves_preserved_after_stage3": plan_after.max_wave_depth + 1,
                "waves_executed": wave_execution_log,
            },
            "stage4_human_20_pct_handoff": human_20_percent_handoff,
        }


if __name__ == "__main__":
    result = run_enterprise_sprint_demo()
    print(json.dumps(result, indent=2))
