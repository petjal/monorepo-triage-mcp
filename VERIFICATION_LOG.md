# Verification & Adversarial Audit Log: `monorepo-triage-mcp`

**System:** Deterministic Legacy Repository Pre-Flight Inspector, Neo4j Graph Exporter & Topological Slice Planner (FastMCP)  
**Workflow:** Spec-Driven Working Prototype -> Cold-Context Adversarial Red-Teaming -> Regression Test Hardening  
**Verification Baseline:** 65 passing unit tests (`pytest`), strict static typing (`mypy --strict`), zero lint violations (`ruff`)

---

## 1. Why We Used "Prototype -> Adversarial Breaker -> Regression Tests" Instead of Pure Test-First TDD

Empirical software engineering research (e.g., Fucci et al., *IEEE Transactions on Software Engineering*, "A Dissection of the Test-Driven Development Process: Does It Really Matter to Test-First or to Test-Last?") has shown that strict test-first sequencing itself has no statistically significant impact on code quality compared to iterative test-last development; what drives quality is small, uniform increments and adversarial test coverage.

In AI-assisted software engineering, naive single-agent "TDD" has an even sharper failure mode: **when the same model writes the unit tests and the implementation in a single context, its tests share the exact same blindspots as its code.**

This repository demonstrates that failure mode empirically, and how to fix it:
1. **Stage 1 (Working Prototype):** I defined the 4-layer architecture and operational invariants from 16 years of diagnosing enterprise source code scanners (`bds_bom_Partition`). A fast code-synthesis model built the working prototype and 48 unit tests. All 48 tests passed (`100% green`), `mypy --strict` passed, and `ruff` passed.
2. **Stage 2 (Cold-Context Adversarial Breaker):** Rather than trusting the 48 green happy-path tests, I ran two rounds of cold-context adversarial auditing (including 12 live Python breakage probes executed by an isolated model with zero build-session context). The breaker immediately broke the "100% green" prototype in **11 places**.
3. **Stage 3 (Real Regression TDD Around a Working Tool):** With a working nascent tool in hand and 11 concrete failure probes identified, we wrote failing regression tests reproducing each bug before implementing the fixes, bringing the final test suite to 65 tests.

---

## 2. Round 1 Audit Catches (5 Defects)

### Catch 1: Alphabetical Symlink Shadowing Starving Canonical Directories (`layer1_scanner.py`)
* **The Defect:** The initial scanner tracked visited directory inodes `(st_dev, st_ino)` in a global `visited_dir_inodes` set and recursed into intra-repository directory symlinks. When a directory symlink `a_link` pointed to a real directory `z_real_dir`, alphabetical traversal visited `a_link` first, recorded `z_real_dir`'s inode in `visited_dir_inodes`, and subsequently rejected the canonical physical directory `z_real_dir` as a "symlink loop" when traversal reached `z`.
* **The Remediation:** Modified `collect_files` to skip symlinks immediately while tracking `(st_dev, st_ino)` strictly along the active ancestor recursion chain (`active_dir_chain`), ensuring every physical directory is indexed once at its canonical path.

### Catch 2: Conservation-of-Tokens Violation on Colliding Module Identifiers (`layer2_slice_planner.py`)
* **The Defect:** In `plan_from_scan`, translating Layer 1 `FileRecord` items into the Layer 2 module map used a dictionary comprehension `{f.module_id: f.estimated_tokens}`. In repositories containing both a package initializer (`pkg/__init__.py` -> `module_id="pkg"`) and a sibling module (`pkg.py` -> `module_id="pkg"`), the second file silently overwrote the first file's token weight and dependency edges.
* **The Remediation:** Updated `plan_from_scan` to sum `estimated_tokens` and union dependency edge sets whenever multiple active source files resolve to the same logical `module_id`, enforcing `modernization_plan.total_active_tokens == scan_summary.active_tokens`.

### Catch 3: Binary & Oversized Blob Ingestion (`layer1_scanner.py`)
* **The Defect:** The initial scanner called `file_path.read_bytes()` unconditionally before checking file size or binary content, classifying compiled WebAssembly or binary blobs with `.js`/`.py` extensions as `ACTIVE_SOURCE` if line lengths were short.
* **The Remediation:** Added a `MAX_SOURCE_FILE_BYTES` (`2 MB`) stat check prior to reading and a `BINARY_SNIFF_BYTES` (`8 KB`) null-byte check (`b"\x00" in raw_bytes[:8192]`), classifying binary or oversized artifacts as `PRUNED_BLOAT` (`reason="binary_or_oversized_blob"`).

### Catch 4: Recursive Wave Evaluator Paired with Iterative Tarjan Solver (`layer2_slice_planner.py`)
* **The Defect:** While `_solve_tarjan_sccs` was implemented iteratively to handle deep dependency graphs ($N > 1000$) without hitting Python's recursion limit, the subsequent `get_wave(scc_id)` helper used recursive function calls.
* **The Remediation:** Replaced recursive `get_wave` with an explicit iterative post-order evaluation stack (`eval_stack`), guaranteeing zero call-stack recursion on 1,200+ node chains.

### Catch 5: Negative & Zero Token Weight Handling in First-Fit Decreasing Packer (`layer0_invariants.py`)
* **The Defect:** `build_modernization_plan` validated `token_budget` but did not validate the token weights in `modules: dict[str, int]`. Passing a negative integer weight via `plan_dependency_graph` would reduce a slice's running token total during First-Fit Decreasing bin-packing, bypassing the budget cap.
* **The Remediation:** Added `validate_module_tokens` in Layer 0, rejecting `bool` types, empty module identifiers, and negative weights (`< 0`), while permitting `0`-token empty `__init__.py` files.

---

## 3. Round 2 Cold-Context Probe Catches (6 Defects Across 12 Live Probes)

### Catch 6: Nested Monorepo `recommended_exclusions` & Check Ordering (`layer1_scanner.py`)
* **The Defect:** On nested monorepo bloat paths such as `packages/web/node_modules/react/index.js`, `recommended_set.add(path_parts[0])` recommended excluding `"packages"` (the entire source tree) instead of `"packages/web/node_modules"`. Furthermore, checking binary null bytes and DLP regexes *before* `BLOAT_DIR_NAMES` caused dummy test keys inside `node_modules/` to trigger false `QUARANTINED_DLP` alerts and prevented binary-only bloat directories (`src/__pycache__`) from reaching `recommended_exclusions`.
* **The Remediation:** Moved the `BLOAT_DIR_NAMES` check to Step 1 of the file loop and recorded the exact relative path up to the first bloat directory component (`"/".join(path_parts[:bloat_idx + 1])`).

### Catch 7: Intra-Repository File Symlinks, Broken Symlinks & Unreadable Files (`layer1_scanner.py`)
* **The Defect:** While directory symlinks were skipped, intra-repo file symlinks (`src/alias.py -> src/real.py` or `src/sneaky.py -> ../node_modules/pkg/lib.py`) were followed as `ACTIVE_SOURCE`, double-counting tokens and bypassing bloat directory pruning. Broken symlinks vanished silently, and unreadable files (`chmod 000`) caught by `except PermissionError:` defaulted to `b""` and became 0-token `ACTIVE_SOURCE` modules.
* **The Remediation:** Quarantined all symlinks (directory, file, and broken) into `symlink_loops_skipped` after checking confinement via Layer 0 `resolve_confined_path`, and classified unreadable files as `PRUNED_BLOAT` (`reason="unreadable_file"`).

### Catch 8: Python Relative Imports at Root & False `__init__.py` Circular Dependency Knots (`layer1_scanner.py` & `layer2_slice_planner.py`)
* **The Defect:** (1) In `extract_python_imports`, relative imports with `node.module is None` that resolved to the repo root (`from . import utils` in `main.py` or `from .. import root_cfg` in `pkg/sub.py`) produced `base_mod == ""`, causing `if base_mod:` to drop all imported names. (2) Inside `pkg/service.py`, `from . import models` emitted both `"pkg"` (`pkg/__init__.py`) and `"pkg.models"`. When `pkg/__init__.py` re-exported `from .service import UserService`, Layer 2 falsely flagged `pkg+pkg.service` as a circular dependency knot.
* **The Remediation:** When `node.module is None`, emitted only the specific target submodules (`f"{base_mod}.{alias.name}" if base_mod else alias.name`) rather than `base_mod`, and prevented prefix-stripping fallback in `_resolve_import_targets` from linking a child submodule (`pkg.service`) back to its own parent package initializer (`pkg`) on unknown symbols.

### Catch 9: Polyglot Monorepo Resolution Across Go, TypeScript `index.ts` Barrels, and Nested `src/` Layouts (`layer2_slice_planner.py`)
* **The Defect:** (1) Go imports (`"github.com/acme/myrepo/pkg/router"`) reference package directories rather than file stems (`pkg.router.router`), so 0% of Go edges connected. (2) TypeScript barrel imports (`import { x } from './auth'`) produced `src.auth`, failing to match `src/auth/index.ts` (`src.auth.index`), and `export { x } from './service'` re-exports were ignored. (3) Nested monorepo source roots (`packages/core/src/core/api.py` and `billing/src/main/java/com/acme/Billing.java`) failed root-only `startswith("src.")` matching.
* **The Remediation:** Added Go directory-suffix to package-files mapping (`go_dir_to_modules`), TypeScript `.index` barrel aliasing and `export ... from` extraction, C-style `//` and `/* */` comment stripping (preserving string literals), `\bimport\b` word-boundary enforcement, and nested `.src.` / `.src.main.java.` marker resolution.

### Catch 10: `scc_id` Delimiter Collision on Module Names Containing `+` (`layer2_slice_planner.py`)
* **The Defect:** Multi-node SCCs were assigned `scc_id = "+".join(scc_mods)`. In a graph containing a cycle `a <-> b` (`scc_id = "a+b"`) alongside a singleton module named `"a+b"`, both condensation nodes received `scc_id = "a+b"`, overwriting `scc_deps` and `wave_memo`.
* **The Remediation:** Tracked `used_scc_ids` initialized with all singleton module names and disambiguated colliding multi-node SCC identifiers as `cycle(a+b)`.

### Catch 11: Compact MCP Payload Mode (`server.py`)
* **The Defect:** `triage_and_plan_repository` serialized every `PRUNED_BLOAT` `FileRecord` into `scan_summary.files`, returning 150+ `.git/` and cache records even on a small repository.
* **The Remediation:** Added `pruned_file_count` to `scan_summary` and defaulted `include_pruned_files: bool = False` in `triage_and_plan_repository` so `scan_summary.files` returns only `ACTIVE_SOURCE` and `QUARANTINED_DLP` records unless full bloat file listing is explicitly requested.

---

## 4. Layer-by-Layer Verification Architecture

```text
+-----------------------------------------------------------------------------------+
| LAYER 3: FastMCP Protocol Service (server.py)                                     |
| JSON-RPC Tool Exposure | Compact Bloat Filtering | Action Plan & Neo4j Exporters  |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| LAYER 2: Graph Condensation & Wave Planner (layer2_slice_planner.py)              |
| Iterative Tarjan SCCs | Polyglot Monorepo Resolver | Kahn Waves | FFD Bin Packer  |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| LAYER 1: Deterministic Repo Scanner & AST Extractor (layer1_scanner.py)           |
| Bloat-First Pruning | Symlink Quarantine | DLP Gate | Comment-Free AST/Lexical    |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| LAYER 0: Boundary Corridors & Invariants (layer0_invariants.py)                   |
| Strict Bool/Int/Float Guards | Path Confinement | Shannon Entropy | Token Bounds  |
+-----------------------------------------------------------------------------------+
```

### Verification Matrix

| Layer / Module | Key Invariant | Test Suite | Verification Result |
| :--- | :--- | :--- | :--- |
| **Layer 0 (`layer0_invariants.py`)** | Rejects `bool`, `NaN`/`Inf`, path traversal (`..`/external symlinks), and negative module weights | `tests/test_layer0_invariants.py` | 100% pass |
| **Layer 1 (`layer1_scanner.py`)** | Bloat-first directory pruning (`packages/web/node_modules`); skips all symlinks; prunes binary/unreadable/generated/minified files; quarantines PEM/AWS/GH secrets; strips `//` and `/* */` comments | `tests/test_layer1_scanner.py` | 100% pass |
| **Layer 2 (`layer2_slice_planner.py`)** | Iterative Tarjan SCCs + iterative wave assignment on 1,200-node deep chains; resolves Python `__init__.py`, TypeScript `index.ts`, Go package dirs, and nested monorepo `src/` roots; exports Neo4j Cypher & Markdown Action Plan | `tests/test_layer2_slice_planner.py` | 100% pass |
| **Layer 3 (`server.py`)** | End-to-end MCP tool registration, `pruned_file_count`, Neo4j Cypher, and Action Plan output | `tests/test_server.py` | 100% pass |
