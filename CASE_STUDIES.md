# Sample Pre-Flight Case Studies: Assessing External Repositories (`trpc/trpc` & `django/django`)

> **Reader Orientation (Tool vs. Target Codebases & Authorship):**
> * **How This Was Built:** I supplied the enterprise repository-triage ideas and verification gates from my 16 years diagnosing source code scanners at Black Duck (`bds_bom_Partition`), and used Google Gemini / Antigravity (`gemini-3.8-flash` builders + cold-context `gemini-4-argon` auditors) to write all of the code, tests, benchmarks, and reports.
> * **This document (`CASE_STUDIES.md`)** presents sample Day-1 pre-flight assessment reports generated **by** `monorepo-triage-mcp` when pointed at two external public codebases (`trpc/trpc` and `django/django`) to simulate scoping a large-scale autonomous AI modernization engagement.
> * **[`README.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/README.md)** explains the architecture and usage of the `monorepo-triage-mcp` server itself.
> * **[`VERIFICATION_LOG.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md)** documents the adversarial code audits, 85-test regression suite, and Linux cgroup performance profiling of **this repository's own Python source code**.

---

## 1. Executive Summary (Plain-English Brief for Project Sponsors & Engineering Leaders)

When an enterprise engagements team scopes a major software modernization project using autonomous AI coding agents, three repository pathologies routinely derail timelines and budgets if not caught on Day 1:

1. **Paying AI Agents to Read Dead Weight:** In most production repositories, 55% to 95% of files on disk are third-party vendor libraries (`node_modules/`, `vendor/`), localization dictionaries (`.po`/`.mo`), or generated build artifacts. Feeding raw directories into an LLM pipeline wastes compute budget and pollutes context windows.
2. **Parallel Agent Write Collisions:** Autonomous agents cannot refactor a codebase in random order. If Agent A modernizes a high-level API controller while Agent B simultaneously alters the database schema it depends on, integration tests fail. Work must be scheduled **bottom-up in sequential Waves (`Wave 0` foundation leaves first $\rightarrow$ `Wave 1..k` dependents)** so multiple agents can work in parallel *within* the same wave without stepping on each other.
3. **"Spaghetti Hairballs" (Circular Dependency Knots):** Legacy codebases frequently contain closed dependency loops where Module A imports Module B, Module B imports Module C, and Module C imports Module A. Because these files are mutually coupled, an AI agent cannot modernize one file's interface in isolation—the **entire circular knot** must fit inside a single coordinated context budget. If a circular knot exceeds that memory ceiling, autonomous agents will stall or hallucinate broken interfaces unless a human architect carves a clean interface seam first.

Below are the side-by-side findings produced by `monorepo-triage-mcp` in under 3 seconds when scanning a modern TypeScript monorepo (**`trpc/trpc`**) versus a 20-year-old enterprise Python monolith (**`django/django`**).

### Side-by-Side Pre-Flight Scorecard (`token_budget = 120,000`)

| Pre-Flight Dimension | Case Study A: `trpc/trpc` (Unseeded vs. +4,000 Synthetic `node_modules`) | Case Study B: `django/django` (20-Year Python Monolith) | Operational Meaning for Engagement Kickoff |
| :--- | :--- | :--- | :--- |
| **Scan & Planning Time** | **0.27 seconds** (`22.1 MB` peak RAM) | **3.01 seconds** (`56.4 MB` peak RAM) | Runs locally on a 1-vCPU, 128 MB RAM VM with zero network egress |
| **Total Files on Disk** | **1,656 files** (`2.15M` tokens) [Unseeded]<br>*5,657 files (`2.18M` tokens) [+4k synthetic]* | **7,085 files** (`12.91M` total tokens) *(excluding internal `.git/` packfile)* | Raw un-triaged footprint on disk |
| **Non-Source / Vendor Bloat Pruned** | **804 files pruned (`63.89%` token reduction)** [Unseeded]<br>*4,805 files pruned (`64.36%` token reduction) [+4k synthetic]* | **4,103 files pruned (`56.35%` token reduction)** | Eliminates `1.37M` (`trpc`) and `7.28M` (`django`) dead-weight tokens prior to ingestion |
| **Active Source Scope** | **852 TypeScript/JS modules** (`775,370` tokens)<br>*(condensed into 851 modules in DAG)* | **2,982 Python/JS modules** (`5,637,083` tokens)<br>*(condensed into 2,977 unique module IDs)* | True active engineering scope |
| **DLP Secrets Quarantined** | `0` files | `0` files (`4` doc symlinks skipped) | Safe for enclave ingestion |
| **Bottom-Up Execution Schedule** | **27 Waves (`Waves 0..26`)** (`21` slices @ 120k budget / `58` slices @ 16k budget) | **68 Waves (`Waves 0..67`)** (`59` slices @ 120k budget / `338` slices @ 16k budget) | Topological order for parallel agent swarm execution |
| **Circular Dependency Knots (SCCs)** | **3 knots** (max: `103` modules / `73,199` tokens) | **3 database backend knots** (max: `3` modules / `16,519` tokens) | Both repositories are 100% swarm-ready at `120,000` tokens |
| **Day-1 Engagement Disposition** | **GREEN LIGHT (`21/21` slices `READY`)** | **GREEN LIGHT (`59/59` slices `READY` @ 120k budget)** | True AST module-load traversal excludes function-local lazy imports |

---

## 2. Case Study A: `trpc/trpc` (Modern TypeScript Monorepo) — "Green Light: 100% Swarm-Ready"

### What the Tool Found
1. **Context Reduction & Vendor Isolation:**
   * In its native, unseeded state, `trpc/trpc` contains `1,656` files (`2,147,468` total tokens). `monorepo-triage-mcp` prunes `804` documentation and non-source files (`1,372,098` tokens, **`63.89%` context reduction**).
   * To stress-test vendor pruning, we also benchmarked `trpc/trpc` with `4,001` synthetically seeded fixture files placed in `packages/server/node_modules/synthetic_fixture`. The scanner pruned `4,805` files (`1,400,005` tokens, **`64.36%` context reduction**) in `0.27` seconds without reading vendored file contents.
   * Exactly `852` active TypeScript/JavaScript source modules (`775,370` tokens) remain for agent ingestion (condensing into `851` modules in the DAG due to two files sharing module identity).
2. **Manageable Circular Coupling:**
   * Tarjan Strongly Connected Components (SCC) condensation identified `725` condensation nodes across `851` modules, containing exactly **3 circular dependency knots**:
     * **Knot 1 (Wave 0):** `vitest.config+vitest.shared` — `2` test configuration modules totaling **`649` tokens**.
     * **Knot 2 (Wave 5):** `packages.server.src.observable.*` and `packages.server.src.unstable-core-do-not-import.*` — `24` mutually coupled reactive streaming and core modules totaling **`37,106` tokens**.
     * **Knot 3 (Wave 16):** Cross-package integration cycle between `packages.client.*`, `packages.next.*`, `packages.react-query.*`, and `packages.server.src.adapters.*` — `103` modules totaling **`73,199` tokens**.
   * Because even the largest knot (`73,199` tokens) is well beneath the `120,000`-token per-agent slice ceiling, **every knot can be ingested and refactored atomically by an agent worker (`status: READY`)**.
3. **Swarm Execution Schedule:**
   * All modules pack cleanly into **27 sequential waves (`Waves 0..26`)** across **21 `READY` slices** at `120,000` tokens (or 58 slices at `16,000` tokens), with **0 `OVERSIZED_COUPLED_KNOT` blockers**.

---

## 3. Case Study B: `django/django` (20-Year Enterprise Python Monolith) — "Green Light: True Architecture Exposed"

### What the Tool Found
1. **56.35% Bloat Pruning & Symlink Trap Defusal:**
   * Out of `7,085` files (`12,913,711` total tokens), the scanner pruned `4,103` non-source artifacts (`7,276,628` tokens—primarily `.po`/`.mo` human-language localization files, documentation text, and binary assets) and automatically skipped `4` documentation symlink aliases (`docs/_theme/djangodocs-epub/static/docicons-*.png`). Note that VCS packfiles (`.git/objects/pack`) and local caches (`.mypy_cache`, `__pycache__`) are completely ignored at the file-walk level to guarantee 100% deterministic, uninflated metrics.
   * The active modernization scope is `2,982` modules (`5,637,083` tokens), condensed into `2,977` unique module IDs across **68 bottom-up waves (`Waves 0..67`)**.
2. **Elimination of the False 153-Module Wave 5 Knot:**
   * Earlier naive AST scanners that traversed inside `def` and `async def` function bodies falsely reported a "153-module / 628,301-token circular dependency hairball" at Wave 5 between `django.db.models`, `django.conf`, `django.apps`, and `django.urls`.
   * In reality, Django's core authors already solved module-load circularity years ago by **lazy-loading those dependencies inside function bodies** (e.g. inside `Model.clean()`, `get_models()`, etc.). When Layer 1 correctly analyzes module-load dependencies (excluding function-local imports and `if TYPE_CHECKING:` guards), **the 153-module monster knot completely vanishes**.
   * The live repository contains **only 3 genuine circular knots**, all small, self-contained database backend pairings at Wave 46:
     * **Knot 1 (Wave 46):** `django.db.backends.oracle.{base, operations, utils}` — `3` modules, **`16,519` tokens** (`READY` under `120,000` budget).
     * **Knot 2 (Wave 46):** `django.db.backends.sqlite3.{base, features, operations}` — `3` modules, **`11,010` tokens** (`READY`).
     * **Knot 3 (Wave 46):** `django.db.backends.postgresql.{base, introspection}` — `2` modules, **`10,433` tokens** (`READY`).
   * All three knots fit comfortably inside standard agent context budgets, confirming that Django's actual architecture is **100% swarm-ready** across 68 bottom-up waves.

### How a Forward Deployed Engineer Uses This Finding at Project Kickoff

The pre-flight report prescribes a concrete **Bottom-Up Swarm Execution Plan**:
1. **Phase 1 — Foundational Leaf Swarm (`Waves 0..45`):**
   * Dispatch parallel agent workers immediately across utility libraries, serialization engines, and independent sub-frameworks (`django.utils`, `django.core`, `django.template`), which execute with zero upstream circular blockers.
2. **Phase 2 — Isolated Database Backend Modernization (`Wave 46`):**
   * Modernize the three database backend knots (`oracle`, `sqlite3`, `postgresql`) as three independent atomic slices (`< 17,000` tokens each), without risking cross-backend regression.
3. **Phase 3 — Top-Level Contrib Apps Rollout (`Waves 47..67`):**
   * Roll out modernization across high-level applications (`django.contrib.admin`, `django.contrib.auth`, `django.contrib.postgres`, and test suites) with fully verified, typed foundations beneath them.

---

## 4. Runnable End-to-End "80/20" Enterprise Sprint PoC (`examples/run_django_sprint_demo.py`)

To demonstrate how the pre-flight scan connects to an **80% Autonomous / 20% Human** enterprise sprint without requiring external LLM API keys, this repository includes a self-contained runnable script ([`examples/run_django_sprint_demo.py`](https://github.com/petjal/monorepo-triage-mcp/blob/master/examples/run_django_sprint_demo.py)):

```bash
PYTHONPATH=src python3 examples/run_django_sprint_demo.py
```

> **Live Engine vs. Offline Wave Replay Disclosure:** Stages 1, 2, 2.5, the per-wave `mypy --strict` Judge, and the post-sprint graph rescan all execute live (`monorepo-triage-mcp` + `mypy.api.run`). Stage 3 replays deterministic pre-computed wave patches (`OFFLINE_WAVE_REPLAY_PATCHES`) in the computed bottom-up wave order so any reviewer can run the script offline in ~1 second with zero API keys.

### The Simulated Sprint Scenario ("Sprint 42: Strict Type Modernization")
A customer wants to modernize a 7-module legacy untyped Django subsystem (`django.utils` $\rightarrow$ `django.core.validators` $\rightarrow$ `django.contrib.postgres.fields`) to 100% PEP 484 type annotations so their CI pipeline can enforce `mypy --strict`:

1. **Stage 1 & 2 — Live Pre-Flight Triage & Wave Blueprint (`monorepo-triage-mcp`):**
   * Prunes `79.28%` of non-source tokens (`2,286` pruned bloat tokens in `node_modules/admin-ui/bundle.js` + `25` quarantined DLP tokens vs. `604` active Python tokens across 7 modules).
   * Quarantines a legacy RSA private key (`tests/postgres_tests/legacy_test_key.pem`) via the Layer 1 DLP gate before any code reaches an agent context window.
   * Detects the circular dependency knot between `django.utils.functional` and `django.utils.deprecation` at **Wave 1** (`CondensationNode.is_cyclic == True`) and schedules a 4-wave bottom-up execution plan (`Wave 0` leaf utilities $\rightarrow$ `Wave 1` coupled knot $\rightarrow$ `Wave 2` core validators $\rightarrow$ `Wave 3` Postgres fields).
2. **Stage 2.5 — Live Out-of-Order Counterfactual Proof (`mypy --strict` Failure):**
   * Before running bottom-up waves, the script applies the modernized Wave 2 patch (`django/core/validators.py`) *out of order* (while Wave 0 and Wave 1 remain untyped) and invokes real `mypy --strict` with `--follow-imports=silent`.
   * **Physical Result:** `mypy --strict` fails (`Found 5 errors in 1 file (checked 1 source file)`), proving why top-down or random-order agent execution breaks strict type-checking across dependent modules.
3. **Stage 3 — Bottom-Up Wave Replay + Real `mypy --strict` Judge + Post-Sprint Rescan:**
   * Replays Wave 0 through Wave 3 in strict bottom-up order. At Wave 1, `functional.unwrap_or_warn` decouples its back-edge to `deprecation.warn_legacy_arg` while preserving 100% identical runtime return value (`'RemovedInNextVersionWarning:...'`), breaking the circular dependency knot while preserving the 4-wave hierarchy (`Waves 0..3`).
   * At the end of each wave, the isolated Judge runs both AST signature verification (`11/11` functions/methods typed) and real `mypy --strict` (`Success: no issues found in 2/4/5/7 source files`) before unlocking the next wave.
   * Re-running `scan_repository` + `plan_from_scan` on the modernized workspace confirms `cyclic_knot_count` dropped from `1` $\rightarrow$ `0` across all `4` preserved waves.
4. **Stage 4 — The "Final 20%" Human Engineer Last-Mile Handoff:**
   * Rather than guessing on ambiguous business logic or touching quarantined secrets, the pipeline outputs a structured 3-item handoff manifest for the customer's human engineers:
     * **Domain Policy Decision (`django/contrib/postgres/fields/ranges.py`):** Confirm whether `DateTimeRangeField.validate_bounds` under exclusive `default_bounds='[)'` should raise `django.core.exceptions.ValidationError` or coerce to an empty range when `lower == upper`.
     * **DLP Secret Rotation (`tests/postgres_tests/legacy_test_key.pem`):** Replace the quarantined static RSA private key with an ephemeral runtime test fixture.
     * **Architectural Seam Sign-Off (`functional.py <-> deprecation.py`):** Confirm whether to extract the legacy `RemovedInNextVersionWarning` string format into a shared leaf constants module after decoupling `functional.unwrap_or_warn`.
