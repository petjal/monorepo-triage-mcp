# Sample Pre-Flight Case Studies: Assessing External Repositories (`trpc/trpc` & `django/django`)

> **Reader Orientation (Tool vs. Target Codebases):**
> * **This document (`CASE_STUDIES.md`)** presents sample Day-1 pre-flight assessment reports generated **by** `monorepo-triage-mcp` when pointed at two external public codebases (`trpc/trpc` and `django/django`) to simulate scoping a large-scale autonomous AI modernization engagement.
> * **[`README.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/README.md)** explains the architecture and usage of the `monorepo-triage-mcp` server itself.
> * **[`VERIFICATION_LOG.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md)** documents the adversarial code audits, 74-test regression suite, and Linux cgroup performance profiling of **this repository's own Python source code**.

---

## 1. Executive Summary (Plain-English Brief for Project Sponsors & Engineering Leaders)

When an enterprise engagements team scopes a major software modernization project using autonomous AI coding agents, three repository pathologies routinely derail timelines and budgets if not caught on Day 1:

1. **Paying AI Agents to Read Dead Weight:** In most production repositories, 65% to 95% of files on disk are third-party vendor libraries (`node_modules/`, `vendor/`), localization dictionaries (`.po`/`.mo`), or generated build artifacts. Feeding raw directories into an LLM pipeline wastes compute budget and pollutes context windows.
2. **Parallel Agent Write Collisions:** Autonomous agents cannot refactor a codebase in random order. If Agent A modernizes a high-level API controller while Agent B simultaneously alters the database schema it depends on, integration tests fail. Work must be scheduled **bottom-up in sequential Waves (`Wave 0` foundation leaves first $\rightarrow$ `Wave 1..k` dependents)** so multiple agents can work in parallel *within* the same wave without stepping on each other.
3. **"Spaghetti Hairballs" (Circular Dependency Knots):** Legacy codebases frequently contain closed dependency loops where Module A imports Module B, Module B imports Module C, and Module C imports Module A. Because these files are mutually coupled, an AI agent cannot modernize one file's interface in isolation—the **entire circular knot** must fit inside a single coordinated context budget (configured here at **120,000 tokens** per agent slice). If a circular knot exceeds that memory ceiling, autonomous agents will stall or hallucinate broken interfaces unless a human architect carves a clean interface seam first.

Below are the side-by-side findings produced by `monorepo-triage-mcp` in under 3 seconds when scanning a modern TypeScript monorepo (**`trpc/trpc`**) versus a 20-year-old enterprise Python monolith (**`django/django`**).

### Side-by-Side Pre-Flight Scorecard (`token_budget = 120,000`)

| Pre-Flight Dimension | Case Study A: `trpc/trpc` (+ 4k `node_modules` files) | Case Study B: `django/django` (20-Year Python Monolith) | Operational Meaning for Engagement Kickoff |
| :--- | :--- | :--- | :--- |
| **Scan & Planning Time** | **0.28 seconds** (`22.1 MB` peak RAM) | **2.74 seconds** (`56.4 MB` peak RAM) | Runs locally on a 1-vCPU, 128 MB RAM VM with zero network egress |
| **Total Files on Disk** | 5,686 files (`14.47M` total tokens) | 7,114 files (`16.77M` total tokens) | Raw un-triaged footprint |
| **Non-Source / Vendor Bloat Pruned** | **4,834 files pruned (`94.6%` token reduction)** | **4,132 files pruned (`66.4%` token reduction)** | Eliminates `13.69M` (`trpc`) and `11.13M` (`django`) dead-weight tokens prior to ingestion |
| **Active Source Scope** | **852 TypeScript/JS modules** (`775,370` tokens) | **2,982 Python/JS modules** (`5,637,040` tokens) | True active engineering scope |
| **DLP Secrets Quarantined** | `0` files | `0` files (`4` doc symlinks skipped) | Safe for enclave ingestion |
| **Bottom-Up Execution Schedule** | **18 Waves** (`21` work slices) | **24 Waves** (`59` work slices) | Topological order for parallel agent swarm execution |
| **Circular Dependency Knots (SCCs)** | **3 small knots** (max: `24` modules / `37,106` tokens) | **16 knots** (`15` ready + **1 oversized `153`-module / `628,301`-token core knot**) | `trpc` is 100% auto-ready; `django` requires 1 human seam-carving gate at Wave 5 |
| **Day-1 Engagement Disposition** | **GREEN LIGHT (`21/21` slices `READY`)** | **YELLOW LIGHT (`58/59` slices `READY`, `1` `OVERSIZED_COUPLED_KNOT`)** | Pinpoints the exact Wave 5 architectural bottleneck before agent compute is spent |

---

## 2. Case Study A: `trpc/trpc` (Modern TypeScript Monorepo) — "Green Light: 100% Swarm-Ready"

### What the Tool Found
1. **Immediate 94.6% Context Reduction:**
   * Out of `5,686` files (`14,469,463` total tokens), `monorepo-triage-mcp` pruned `4,834` vendored (`packages/server/node_modules`) and non-source files (`13,694,093` tokens) directly from filesystem metadata without reading vendored file contents.
   * Only `852` active TypeScript/JavaScript source modules (`775,370` tokens) remain for agent ingestion.
2. **Manageable Circular Coupling:**
   * Tarjan Strongly Connected Components (SCC) condensation identified `807` DAG nodes across `852` modules, containing only **3 circular dependency knots**:
     * **Knot 1 (Wave 5):** `packages.server.src.observable.*` — `24` mutually coupled reactive streaming modules totaling **`37,106` tokens**.
     * **Knot 2 (Wave 7):** `packages.react-query.src.internals.*` — `21` mutually coupled client state modules totaling **`31,069` tokens**.
     * **Knot 3 (Wave 0):** `vitest.config+vitest.shared` — `2` test configuration modules totaling **`649` tokens**.
   * Because even the largest knot (`37,106` tokens) is less than one-third of the `120,000`-token per-agent slice ceiling, **every single knot can be ingested and refactored atomically by a single agent worker (`status: READY`)**.
3. **Swarm Execution Schedule:**
   * All `852` modules pack cleanly into **18 sequential waves (`Waves 0..17`)** across **21 `READY` slices**, with **0 `OVERSIZED_COUPLED_KNOT` blockers**.

---

## 3. Case Study B: `django/django` (20-Year Enterprise Python Monolith) — "Yellow Light: Wave 5 Core Hairball Detected"

### What the Tool Found
1. **66.4% Bloat Pruning & Symlink Trap Defusal:**
   * Out of `7,114` files (`16,767,223` total tokens), the scanner pruned `4,132` non-source artifacts (`11,130,183` tokens—primarily `.po`/`.mo` human-language localization files, documentation text, and binary assets) and automatically skipped `4` documentation symlink aliases (`docs/_theme/djangodocs-epub/static/docicons-*.png`).
   * The active modernization scope is `2,982` modules (`5,637,040` tokens), condensed into `2,781` DAG nodes across **24 bottom-up waves (`Waves 0..23`)** and **59 work slices**.
2. **15 Manageable Subsystem Cycles vs. 1 Monster Core Knot:**
   * Out of **16 circular dependency knots** detected across Django, **15 fit comfortably inside a single agent's `120,000`-token context window (`status: READY`)**:
     * `django.contrib.admin.*` (Wave 11): `13` modules, **`97,737` tokens** (`READY`).
     * `django.test.*` (Wave 14): `4` modules, **`45,842` tokens** (`READY`).
     * `django.contrib.gis.gdal.*` (Wave 13): `14` modules, **`29,014` tokens** (`READY`).
     * `django.utils.{deprecation,functional,inspect,regex_helper,version}` (Wave 1): `5` modules, **`16,742` tokens** (`READY`).
     * `django.contrib.postgres.*` (Wave 9): `7` modules, **`13,397` tokens** (`READY`).
   * **The Critical Blocker (`wave_5_slice_00` — `OVERSIZED_COUPLED_KNOT`):**
     * At **Wave 5**, the tool exposes a massive circular dependency knot spanning **153 core modules** (`django.apps`, `django.conf`, `django.core`, `django.db`, `django.db.models`, `django.dispatch`, `django.forms`, `django.http`, `django.template`, `django.urls`, `django.views`) totaling **`628,301` tokens**—more than **5.2x larger** than the `120,000`-token per-agent slice budget.

### How a Forward Deployed Engineer Uses This Finding at Project Kickoff

Without this 2.7-second pre-flight scan, an autonomous modernization pipeline would complete Waves 0–4 and then stall at Wave 5 as agents attempt to refactor subsets of the 153-module core knot without visibility into the remaining 500,000+ tokens of circular dependents.

Instead, the pre-flight report prescribes a concrete **3-Phase Execution Plan**:
1. **Phase 1 — Immediate Autonomous Swarm Execution (`Waves 0..4`):**
   * Dispatch parallel agent workers immediately on the foundational leaf and utility modules (`Waves 0..4`), which have zero upstream circular blockers.
2. **Phase 2 — Human-in-the-Loop Seam-Carving Gate (`Wave 5`, `wave_5_slice_00`):**
   * Assign a senior architect to decouple 2–3 high-fanout bridge modules inside the 153-module knot (specifically lazy-loading `django.conf.settings`, `django.apps.registry`, and `django.urls` imports from `django.db.models` and `django.forms`) so the `628,301`-token SCC fractures into independent sub-packages under `120,000` tokens each.
3. **Phase 3 — Full Parallel Rollout (`Waves 6..23`):**
   * Once the Wave 5 seam is carved, release the parallel agent swarm across the remaining 18 waves (`django.contrib.postgres`, `django.contrib.admin`, `django.contrib.gis`, and the test suite), where all 15 remaining subsystem knots are already verified `READY` (`< 100,000` tokens each).

---

## 4. Runnable End-to-End "80/20" Enterprise Sprint PoC (`examples/run_django_sprint_demo.py`)

To demonstrate how the pre-flight scan connects to an actual **80% Autonomous / 20% Human** enterprise sprint, this repository includes a self-contained runnable simulation ([`examples/run_django_sprint_demo.py`](https://github.com/petjal/monorepo-triage-mcp/blob/master/examples/run_django_sprint_demo.py)):

```bash
PYTHONPATH=src python3 examples/run_django_sprint_demo.py
```

### The Simulated Sprint Scenario ("Sprint 42: Strict Type Modernization")
A customer wants to modernize a legacy untyped Django subsystem (`django.utils` $\rightarrow$ `django.core.validators` $\rightarrow$ `django.contrib.postgres.fields`) to 100% PEP 484 type annotations so their CI pipeline can enforce `mypy --strict`:

1. **Stage 1 & 2 — Pre-Flight Triage & Wave Blueprint (`monorepo-triage-mcp`):**
   * Prunes `84.96%` of dead-weight tokens (`node_modules/admin-ui/bundle.js`).
   * Quarantines a legacy RSA private key (`tests/postgres_tests/legacy_test_key.pem`) via the Layer 1 DLP gate before any code reaches an LLM.
   * Detects the circular dependency knot between `django.utils.functional` and `django.utils.deprecation` at **Wave 1** and schedules a 4-wave bottom-up execution plan (`Wave 0` leaf utilities $\rightarrow$ `Wave 1` coupled knot $\rightarrow$ `Wave 2` core validators $\rightarrow$ `Wave 3` Postgres fields).
2. **Stage 3 — The Autonomous "80%" Wave Swarm + Isolated Judge Pass:**
   * Executes Wave 0 through Wave 3 in strict bottom-up order. At Wave 1, the autonomous worker carves a `from __future__ import annotations` + `if TYPE_CHECKING:` seam to break the circular type dependency between `functional.py` and `deprecation.py`.
   * At the end of each wave, an isolated AST Judge verifies that 100% of functions and methods (`10/10`) carry complete parameter and return type annotations before unlocking the next wave.
3. **Stage 4 — The "Final 20%" Human Engineer Last-Mile Handoff:**
   * Rather than guessing on ambiguous business logic or touching quarantined secrets, the pipeline outputs a structured 3-item handoff manifest for the customer's human engineers:
     * **Domain Policy Decision (`django/contrib/postgres/fields/ranges.py`):** Confirm whether `DateTimeRangeField(timezone_aware=None)` should raise `ValidationError` when `USE_TZ=False`.
     * **DLP Secret Rotation (`tests/postgres_tests/legacy_test_key.pem`):** Replace the quarantined static RSA private key with an ephemeral runtime test fixture.
     * **Architectural Seam Sign-Off (`functional.py <-> deprecation.py`):** Verify no external plugins rely on implicit runtime re-export attributes across the refactored Wave 1 knot.
