# Verification & Adversarial Audit Log: `monorepo-triage-mcp`

**System:** Deterministic Legacy Repository Pre-Flight Inspector, Neo4j Graph Exporter & Topological Slice Planner (FastMCP)  
**Workflow:** Spec-Driven Working Prototype -> Cold-Context Adversarial Red-Teaming & Systems Telemetry -> Regression Test Hardening  
**Verification Baseline:** 85 passing unit tests (`pytest`), strict static typing (`mypy --strict`), zero lint violations (`ruff`)

> **Reader Orientation (Internal Code QA vs. External Case Studies):**
> * **This document (`VERIFICATION_LOG.md`)** records the adversarial code audits, 85-test regression suite, and systems performance profiling of **`monorepo-triage-mcp`'s own Python source code**.
> * For sample pre-flight assessment reports of **external repositories (`trpc/trpc` and `django/django`)** generated **by** this tool (written for project sponsors and engagement architects), see **[`CASE_STUDIES.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/CASE_STUDIES.md)**.

---

## 1. Why We Used "Prototype -> Adversarial Breaker -> Regression Tests" Instead of Pure Test-First TDD

Empirical software engineering research (e.g., Fucci et al., *IEEE Transactions on Software Engineering*, "A Dissection of the Test-Driven Development Process: Does It Really Matter to Test-First or to Test-Last?") has shown that strict test-first sequencing itself has no statistically significant impact on code quality compared to iterative test-last development; what drives quality is small, uniform increments and adversarial test coverage.

In AI-assisted software engineering, naive single-agent "TDD" has an even sharper failure mode: **when the same model writes the unit tests and the implementation in a single context, its tests share the exact same blindspots as its code.**

This repository demonstrates that failure mode empirically, and how to fix it:
1. **Stage 1 (Working Prototype & Synthetic "TDD" Commits):** I defined the 4-layer architecture and operational invariants from 16 years of diagnosing enterprise source code scanners (`bds_bom_Partition`). A fast code-synthesis model built the working prototype and 48 unit tests. As `git log` reflects, the initial builder committed Stage 1 as 8 alternating `test(layerX)` $\rightarrow$ `feat(layerX)` commits across 8 minutes (`fd91474`..`3946e55`). All 48 tests passed (`100% green`), `mypy --strict` passed, and `ruff` passed. Yet despite the ceremonial green "TDD" checkmarks, the codebase hid more than 20 severe architectural edge-case failures and systems bottlenecks.
2. **Stage 2 (Cold-Context Adversarial Breakers & Live Monorepo Telemetry):** Rather than trusting the 48 green happy-path tests, I ran five rounds of cold-context adversarial auditing (executing live Python breakage probes from isolated models with zero build-session context) and profiled the tool against `django/django` (7,085 files) and `trpc/trpc` (1,656 files native / 5,657 files with 4,000 synthetic test fixtures). That process exposed **28 core engine defects, metric inflations, and systems bottlenecks plus 5 simulation shortcuts in the runnable sprint demo**.
3. **Stage 3 (Real Regression TDD Around a Working Tool):** With a working nascent tool in hand and concrete failure probes identified, we wrote failing regression tests reproducing each bug before implementing the fixes, expanding the test suite from 48 to **85 passing unit tests**.

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

## 4. Round 3 Cold-Context Audit & Systems Telemetry Catches (8 Defects & Bottlenecks)

### Catch 12 (P0-A): Full Disk Reads & Shannon Entropy on Pruned `BLOAT_DIR_NAMES` Files (`layer1_scanner.py`)
* **The Defect:** Although `BLOAT_DIR_NAMES` (`node_modules`, `.git`, `vendor`) was checked first, lines 270–272 still executed `file_path.read_bytes()`, `.decode("utf-8")`, `estimate_source_tokens()`, and `shannon_entropy_bits_per_byte()` on every pruned file `<= 2 MB`, and `collect_files` invoked `Path.relative_to()` 24,636 times on a 7,114-file repo.
* **The Remediation:** Replaced `Path.iterdir()` + `Path.relative_to()` with `os.scandir()` passing `rel_prefix` strings and cached `DirEntry.stat(follow_symlinks=False)`. Files inside `BLOAT_DIR_NAMES` now compute `estimated_tokens = max(1, math.ceil(file_size / 3.5))` directly from `st_size` with **zero `open()`/`read()` syscalls** and `shannon_entropy=0.0`. On `trpc/trpc` (+4,000 `node_modules` files), kernel read syscalls dropped by **71.0%** (`11,373` $\rightarrow$ `3,300`), VFS bytes read dropped by **85.2%** (`48.30 MB` $\rightarrow$ `7.16 MB`), and wall-clock scan time dropped by **7.7x** (`2,137 ms` $\rightarrow$ `270 ms`).

### Catch 13 (P0-B): Catastrophic $O(L^3)$ Regex Backtracking (ReDoS) in `extract_ts_js_imports` (`layer1_scanner.py`)
* **The Defect:** The pattern `(?:import|export)\s+[\w$\s{},*]+\s+from` had three adjacent quantifiers matching whitespace (`\s`). When a 25 KB TypeScript file contained `export` followed by 600 indented comment lines (which comment stripping replaced with whitespace runs) and no `from`, Python's regex engine stalled for **7,140.39 ms**.
* **The Remediation:** Replaced the ambiguous `[\w$\s{},*]+` quantifier with a structured, zero-backtracking ES6/TS clause (`(?:\*\s+as\s+[\w$]+|[\w$]+(?:\s*,\s*(?:\*\s+as\s+[\w$]+|\{[^}]*\}))?|\{[^}]*\}|\*)`), dropping execution time on the 25 KB stress payload from **7,140.39 ms to 0.58 ms** (a **12,311x speedup**).

### Catch 14 (P0-C): $O(K^2 \log K)$ Repeated Tuple Re-Sorting Inside FFD Slice Packer & AST Expression Walking (`layer2_slice_planner.py`, `layer1_scanner.py`)
* **The Defect:** (1) Inside the FFD bin-packing loop, `tuple(sorted(s.modules + node.modules))` re-allocated and re-sorted the tuple on every insertion, taking **5,181.13 ms** for 20,000 leaf modules. (2) In `extract_python_imports`, `ast.walk(tree)` traversed 4.83 million expression nodes across `django/django`.
* **The Remediation:** (1) Replaced immutable tuple re-sorting inside the FFD loop with `_MutableSliceBin` list accumulation + capacity pruning (`valid_budget - b.total_tokens < min_wave_tokens`), sorting once per slice at the end of each wave (**5,181.13 ms $\rightarrow$ 97.44 ms**, a **53.2x speedup**). (2) Replaced `ast.walk(tree)` with statement-container traversal (`body`, `orelse`, `finalbody`, `handlers`, `cases`), skipping expression subtrees while extracting 100% identical AST imports (`11,980` across `django/django`).

### Catch 15 (P0-1): False Cross-Service Circular Dependency Knots in Multi-Package Monorepos (`layer2_slice_planner.py`)
* **The Defect:** `plan_from_scan` stripped `src.` into a global `alias_to_targets` map without considering package locality. When two independent microservices (`services/auth/src/{db,api}.py` and `services/billing/src/{db,api}.py`) used local imports (`import db` in `auth/src/api.py`, `import api` in `billing/src/db.py`), `_resolve_import_targets` linked both services together into a false circular dependency knot (`services.auth.src.api+services.billing.src.db`).
* **The Remediation:** Added `_filter_by_locality` in `_resolve_import_targets` to score candidate targets by shared leading package segments with `self_mod_id`, resolving ambiguous aliases strictly to the closest enclosing service/package root, and prevented Go files from importing their own package directory (`self_mod_id in go_dir_to_modules[sub_dir]`).

### Catch 16 (P0-2): False Python `__init__.py` Circular Knots on PEP 8 Absolute Imports (`layer1_scanner.py` & `layer2_slice_planner.py`)
* **The Defect:** While Round 2 fixed `from . import models` (`node.module is None`), a PEP 8 absolute import `from pkg import models` (`node.module == "pkg"`) inside `pkg/service.py` still emitted `"pkg"` (`base_mod`), forming a false `pkg+pkg.service` cycle whenever `pkg/__init__.py` re-exported from `pkg.service`. On `django/django`, this inflated the core `django` knot to 180 modules.
* **The Remediation:** Omitted `base_mod` in `extract_python_imports` whenever `base_parts` is an ancestor prefix of `parent_parts` (unless importing `*`), and guarded direct/alias resolution in `_resolve_import_targets` with `not self_mod_id.startswith(target_mod + ".")`.

### Catch 17 (P0-3): Backtick Template Literals, Comment Token Gluing, and String-Literal False Imports (`layer1_scanner.py`)
* **The Defect:** `_strip_c_style_comments` ignored backtick strings (`` `...` ``) and replaced `/*...*/` with `""` instead of `" "`. A backtick string containing `/*` (`` const g = `packages/*`; ``) swallowed all subsequent imports in the file; `im/*c*/port` glued into `import`; and `"import { Fake } from './fake'"` inside string literals in TS, Go, and Java was extracted as a real dependency.
* **The Remediation:** Replaced comments and backtick literals with whitespace (`"\n"` if multiline else `" "`), added single-pass string-literal shielding branches to `_TS_JS_IMPORT_RE` and `_GO_IMPORT_RE`, stripped string literals in `extract_java_imports`, and added Java wildcard `.*` support.

### Catch 18 (P0-4): TypeScript Word Boundaries, Spaced `require()`, `".."` Relative Imports, `@/` Aliases & Composed `.index` Barrels (`layer1_scanner.py` & `layer2_slice_planner.py`)
* **The Defect:** `extract_ts_js_imports` matched `my_require("./fake")` and `obj.import("./fake")`, missed `require( "./spaced" )` and `import { x } from ".."`, ignored `@/components/Button` slash paths, and `plan_from_scan` did not compose `src.` + `.index` stripping (failing to register `"auth"` for `src/auth/index.ts`).
* **The Remediation:** Enforced `(?<!\.)\b` word boundaries, permitted whitespace inside `require(...)` and `import(...)`, resolved `"."` and `".."` relative paths and `@/` / `~/` slash paths, and composed `SOURCE_ROOT_MARKERS` stripping with `.index` barrel stripping in `_register_alias`.

### Catch 19 (P1-1): Deep AST `RecursionError` Guard & `edges` String Iterable Validation (`layer1_scanner.py` & `layer2_slice_planner.py`)
* **The Defect:** `ast.parse()` raised an unhandled `RecursionError` on deeply chained expressions (`"1 + \\\n" * 4000`), and `build_modernization_plan` iterated character-by-character over `edges={"a": "mod_b"}` instead of raising `TypeError`.
* **The Remediation:** Caught `(SyntaxError, ValueError, RecursionError, MemoryError)` in `extract_python_imports` and rejected `str`/`bytes` or non-iterable values in `edges` with `TypeError`.

---

## 5. Round 4 Dual Cold-Context Audit of `examples/run_django_sprint_demo.py` (5 Catches)

Two independent cold-context reviewer models were spawned to verify that the runnable 80/20 enterprise sprint demo (`examples/run_django_sprint_demo.py` and `CASE_STUDIES.md` Section 4) contained zero misleading claims or theatrical shortcuts:

### Catch 20: Single-File AST Judge vs. Real `mypy --strict` & Unused `F401` Imports
* **The Defect:** The initial `run_django_sprint_demo.py` claimed to verify `mypy --strict` readiness using only single-file `ast.parse` signature inspection, and its simulated Django files contained decorative top-level imports (`F401` unused imports) that were never called at runtime. Because the AST check ran in single-file isolation, executing Wave 3 *before* Wave 0 still passed the fake judge, failing to prove why bottom-up wave ordering is necessary.
* **The Remediation:** Made every import across all 7 simulated Django files genuinely called at runtime (`0` `ruff` violations on the simulated files), replaced the single-file check with real `mypy.api.run(["--strict", "--explicit-package-bases", ...])` at every wave, and added **Stage 2.5 (Out-of-Order Counterfactual Proof)** demonstrating that running `mypy --strict` on Wave 2 (`validators.py`) *before* Wave 0/1 are modernized fails (`Found 14 errors in 5 files`).

### Catch 21: Non-Existent Django `DateTimeRangeField(timezone_aware=None)` Parameter
* **The Defect:** The initial demo used `DateTimeRangeField(timezone_aware=None)` for its 20% human policy gate, which is not a real parameter on `django.contrib.postgres.fields.ranges.DateTimeRangeField` (it subclasses `ContinuousRangeField` and takes `default_bounds="[)"`).
* **The Remediation:** Replaced with authentic `DateTimeRangeField(default_bounds="[)")` and framed the 20% human policy gate around degenerate `lower == upper` bounds under exclusive `default_bounds="[)"`.

### Catch 22: Post-Sprint Rescan Wave Collapse & Unbroken `TYPE_CHECKING` Cycle
* **The Defect:** In the initial Wave 1 patch, `functional.py` accidentally dropped `from django.utils import regex_helper` (collapsing the post-sprint graph from 4 waves to 3 waves) while keeping `from django.utils import deprecation` inside `if TYPE_CHECKING:` (which static AST import extraction still treats as a cycle).
* **The Remediation:** Preserved `from django.utils import regex_helper` in `functional.py` and decoupled `functional.unwrap_or_warn` from `deprecation.warn_legacy_arg`, verified via a post-sprint `scan_repository` + `plan_from_scan` rescan showing `cyclic_knot_count` dropping from `1 -> 0` while preserving all `4` waves (`0..3`).

### Catch 23: Brittle `scc_id` `"+"` Substring Check & Explicit Offline Replay Disclosure
* **The Defect:** `run_django_sprint_demo.py` checked `sl.scc_ids[0].find("+") != -1` instead of `CondensationNode.is_cyclic`, and `CASE_STUDIES.md` listed `84.96%` from an earlier 3-wave run.
* **The Remediation:** Queried `CondensationNode.is_cyclic` directly, renamed the patch dictionary to `OFFLINE_WAVE_REPLAY_PATCHES` with an explicit `execution_mode_disclosure` field, synchronized all metrics in `CASE_STUDIES.md` and `README.md`, and locked the entire end-to-end sprint demo into `tests/test_server.py::test_enterprise_sprint_demo_end_to_end`.

### Catch 24: Sprint Demo Counterfactual Scope (`--follow-imports=silent`), Runtime Behavior Decoupling & Dynamic AST Function Typing Tally
* **The Defect:** (1) In Stage 2.5 ("Found 14 errors in 5 files"), `mypy`'s default `--follow-imports=normal` reported 9 errors inside the 4 untyped imported files rather than isolating the 5 errors inside `validators.py` itself. (2) Wave 1 refactoring in Stage 3 rewrote `functional.unwrap_or_warn` to return `'UnwrappedFallback:...'` instead of `'RemovedInNextVersionWarning:...'`, silently altering runtime return values during a type-annotation sprint. (3) Stage 3 formatted the final typing tally as `f"{before_total_funcs}/{before_total_funcs} (100%)"`, hardcoding the denominator and assuming a 100% pass rate rather than dynamically summing verified post-Stage-3 AST function signatures.
* **The Remediation:** Configured `follow_imports="silent"` in `judge_run_mypy_strict` to report exactly 5 errors in 1 file; refactored `functional.py` to preserve identical runtime `'RemovedInNextVersionWarning:...'` strings while eliminating import coupling; and dynamically computed `after_typed_funcs` by summing actual AST verification counts (`11/11 (100%)`).

---

## 6. Round 5 Dual Cold-Context Whole-Repo Argon Audit (10 Defects & Invariant Violations Remediated)

A dual cold-context whole-repo audit using `gemini-4-argon` (`conversation://9c936504-d000-4f93-bccc-36f85c7e4644` auditing engine, DLP, and graph resolution; `conversation://e6e6122a-75ef-49e6-b5dc-98efefdeca44` auditing benchmarks, case studies, and documentation) executed live probes across the entire repository and fresh clones of `django/django` and `trpc/trpc`, identifying 10 concrete defects:

### Catch 25: Metric Inflation via Internal VCS & Tool Caches (`layer1_scanner.py`)
* **The Defect:** Internal VCS metadata (`.git`, `.hg`, `.svn`) and tool caches (`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`) were categorized as `BLOAT_DIR_NAMES` and processed through token estimation. In `django/django`, 3.85M pruned tokens (34.6%) came from `.git/objects/pack`, and running `pytest` or `mypy` mutated the repository's pruned token metrics.
* **The Remediation:** Separated `IGNORED_VCS_AND_CACHE_DIRS` from `BLOAT_DIR_NAMES`. Ignored directories are skipped immediately during directory recursion with zero disk read, zero stat, and zero metric pollution, ensuring 100% deterministic, immutable token counts.

### Catch 26: AST Statement Traversal Eliminating False 153-Module Wave 5 Knot (`layer1_scanner.py`)
* **The Defect:** `extract_python_imports` traversed inside `ast.FunctionDef` and `ast.AsyncFunctionDef` bodies and `if TYPE_CHECKING:` blocks by default. On `django/django`, this created a false 153-module / 628,301-token circular dependency knot at Wave 5 between `django.db.models`, `django.conf`, `django.apps`, and `django.urls`, even though Django's authors had already moved those imports inside methods to avoid module-load cycles.
* **The Remediation:** Added `include_deferred: bool = False` to `extract_python_imports`, skipping function definitions, async function definitions, and `if TYPE_CHECKING:` guards during module-load dependency extraction. This eliminated the entire false 153-module hairball on `django/django`, revealing exactly 3 real database backend knots in `oracle`, `sqlite3`, and `postgresql`.

### Catch 27: Blanket `startswith` Breaking TypeScript Multi-Dot Files & Sibling Modules (`layer2_slice_planner.py`)
* **The Defect:** Catch 16 prevented parent package cycles by checking `not self_mod_id.startswith(cand + ".")`. However, applying this blanket check to regular files caused `router.test.ts` (`src.router.test`) importing `./router` (`src.router`) and `auth/helper.ts` (`src.auth.helper`) importing `../auth` (`src.auth`) to have their dependency edges erased, scheduling tests before the code they tested.
* **The Remediation:** Restricted the prefix guard strictly to package barrel modules (`cand in package_barrel_modules`, specifically `__init__.py` and `index.ts/tsx/js/jsx`), preserving legitimate dependency edges for non-barrel multi-dot files and sibling modules.

### Catch 28: Scoped TypeScript Workspace Imports (`@trpc/*`, `@scope/*`) (`layer1_scanner.py`, `layer2_slice_planner.py`)
* **The Defect:** `extract_ts_js_imports` stripped leading `@/` and `~/` but emitted scoped package imports like `@trpc/server` as `@trpc.server`. Meanwhile, Layer 2 stripped `.src.` by slicing after `.src.`, discarding the package directory and preventing 100% of cross-package `@trpc/*` imports from resolving in `trpc/trpc`.
* **The Remediation:** Emitted both scoped (`trpc.server`) and unscoped (`server`) module names for `@scope/package` imports, and registered workspace package aliases in Layer 2, correctly connecting cross-package entrypoints across 27 waves.

### Catch 29: Go Standard Library Cycle Prevention & Nested Monorepo Package Suffixes (`layer1_scanner.py`, `layer2_slice_planner.py`)
* **The Defect:** Single-segment Go import matching caused standard library packages like `import "net/http"` to resolve to a local `http/` directory, forming false circular dependency knots. Conversely, nested monorepo Go packages (`"github.com/acme/repo/services/auth/pkg/db"`) failed to resolve when repositories were structured with multi-tier service roots.
* **The Remediation:** Added `_GO_STDLIB_TOP_DIRS` to explicitly filter standard library imports from local resolution, and registered Go directory suffixes down to 2 segments (or 1 segment for non-stdlib names) in `go_dir_to_modules`.

### Catch 30: Polyglot Java Wildcard `.*` Resolution in Layer 2 (`layer2_slice_planner.py`)
* **The Defect:** While Layer 1 stripped `.*` from Java wildcard imports (`import com.acme.models.*;` -> `"com.acme.models"`), Layer 2 only indexed individual `.java` class files (`"com.acme.models.User"`), causing Java wildcard package imports to resolve to zero dependency edges.
* **The Remediation:** Maintained a `java_pkg_to_modules` mapping in `plan_from_scan` and resolved wildcard package imports to all constituent class files within the package directory.

### Catch 31: Microservice Container Root Locality Isolation (`layer2_slice_planner.py`)
* **The Defect:** When multiple microservices resided under a shared container root (`services/auth/src/db.py`, `services/billing/src/db.py`), `_shared_prefix_segments` returned 1 for the shared `"services"` component, allowing ambiguous local imports (`import db`) to bridge across service boundaries and create false cross-service circular knots.
* **The Remediation:** Set `_shared_prefix_segments` to 0 when the only shared segment is a container directory (`services`, `packages`, `apps`, `libs`, `modules`), and added `_is_unintended_cross_service_alias` to reject candidates in sibling services unless explicitly referenced.

### Catch 32: Lexical Comment & String Literal Regex Hardening (`layer1_scanner.py`)
* **The Defect:** TS template literals with nested interpolations (`` `a ${x.join("`")}` ``), JS regexes containing quotes (`const r = /foo"bar/;`), and TSX apostrophes (`<div>Don't</div>`) caused lexical comment stripping to cross line boundaries and swallow subsequent `import`/`export` statements. Furthermore, single-line aliased and blank Go imports were skipped.
* **The Remediation:** Restricted TS/JS and Go import string branches to non-newline character sets (`[^'\\\r\n]`, `[^"\\\r\n]`), cleanly isolated C-style comment stripping from string scanning, and added single-line aliased/blank Go import patterns.

### Catch 33: Granular Oversized Slice Classification (`layer2_slice_planner.py`)
* **The Defect:** When a module exceeded `token_budget`, `build_modernization_plan` stamped `status="OVERSIZED_COUPLED_KNOT"` even when the node was a single acyclic module (`is_cyclic=False` and `len(modules) == 1`).
* **The Remediation:** Extended `SliceStatus` to distinguish `OVERSIZED_COUPLED_KNOT` (multi-module cyclic knots exceeding budget) from `OVERSIZED_SINGLE_MODULE` (single acyclic files exceeding budget), providing distinct diagnostic signaling for swarm planners.

### Catch 34: Layer 0 Invariant Wiring & Neo4j Cypher Unique Node Identifiers (`layer1_scanner.py`, `layer2_slice_planner.py`, `server.py`)
* **The Defect:** `estimate_source_tokens` and `resolve_confined_path` in Layer 0 were bypassed or silenced in Layer 1; `export_neo4j_cypher` reused variable name `n` across all nodes (invalid Cypher in strict graph engines); and `plan_dependency_graph` in `server.py` omitted Cypher output.
* **The Remediation:** Wired `estimate_source_tokens` and `resolve_confined_path` across all decoded file paths; parameterized Neo4j Cypher export with unique variables (`s0`, `s1`, ...); and included `neo4j_knowledge_graph_cypher` in `server.py` tool responses.

---

## 7. Layer-by-Layer Verification Architecture

```text
+-----------------------------------------------------------------------------------+
| LAYER 3: FastMCP Protocol Service (server.py)                                     |
| JSON-RPC Tool Exposure | Compact Bloat Filtering | Action Plan & Neo4j Exporters  |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| LAYER 2: Graph Condensation & Wave Planner (layer2_slice_planner.py)              |
| Iterative Tarjan SCCs | Locality-Aware Resolver  | Kahn Waves | Fast FFD Packer   |
+-----------------------------------------+-----------------------------------------+
                                          |
+-----------------------------------------v-----------------------------------------+
| LAYER 1: Deterministic Repo Scanner & AST Extractor (layer1_scanner.py)           |
| Zero-Read Bloat Pruner| Symlink Quarantine | DLP Gate | Statement-AST & Lexical   |
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
| **Layer 0 (`layer0_invariants.py`)** | Rejects `bool`, `NaN`/`Inf`, path traversal (`..`/external symlinks), and negative module weights | `tests/test_layer0_invariants.py` (22 tests) | 100% pass |
| **Layer 1 (`layer1_scanner.py`)** | Zero-read bloat pruning (`packages/web/node_modules`); ignores VCS metadata & tool caches without metric inflation; skips all symlinks; prunes binary/unreadable/generated/minified files; quarantines PEM/AWS/GH secrets; statement-level AST & hardened lexical import extraction | `tests/test_layer1_scanner.py` (29 tests) | 100% pass |
| **Layer 2 (`layer2_slice_planner.py`)** | Iterative Tarjan SCCs + iterative wave assignment on 1,200-node deep chains; locality-aware polyglot resolution across Python `__init__.py`, TypeScript `index.ts` & scoped `@scope/*` packages, Go package dirs & stdlib filtering, Java wildcard `.*`, and microservice `src/` roots; fast FFD slice packing; exports Neo4j Cypher & Markdown Action Plan | `tests/test_layer2_slice_planner.py` (26 tests) | 100% pass |
| **Layer 3 (`server.py` & `examples/`)** | End-to-end MCP tool registration, `pruned_file_count`, Neo4j Cypher, Action Plan output, and runnable 80/20 Django Sprint Demo with live `mypy --strict` Judge | `tests/test_server.py` (8 tests) | 100% pass |
