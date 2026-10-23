# monorepo-triage-mcp

A deterministic legacy codebase pre-flight inspector, bloat pruner, Neo4j knowledge-graph exporter, and topological work-slice planner for autonomous coding agents, exposed as a Model Context Protocol (MCP) server (`triage_and_plan_repository` and `plan_dependency_graph`).

This is a portfolio demonstration illustrating field-deployed repository triage, knowledge-graph extraction, and deterministic context partitioning.

> **Repository Document Map (Tool vs. External Case Studies vs. Internal QA):**
> 1. **[`README.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/README.md) (This Document — The Tool):** Architecture, algorithms, and usage of the `monorepo-triage-mcp` server.
> 2. **[`CASE_STUDIES.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/CASE_STUDIES.md) (Assessing External Codebases *With* the Tool):** Plain-English executive brief and technical pre-flight findings generated **by** `monorepo-triage-mcp` when scanning **`trpc/trpc`** (Green Light: 100% Swarm-Ready) and **`django/django`** (Yellow Light: 153-Module / 628K-Token Core Hairball at Wave 5) in preparation for a large-scale AI modernization project.
> 3. **[`VERIFICATION_LOG.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md) (Auditing *Our Own* Source Code):** Multi-round cold-context adversarial red-teaming, 19 defect remediations, 74-test regression suite, and Linux cgroup telemetry of `monorepo-triage-mcp`'s own Python codebase.

## Background

When pointing an automated scanner or an autonomous coding agent at a large enterprise repository, the pipeline rarely fails on language syntax. It fails on **repository pathology**:

1. **Path Explosion & Non-Source Bloat:** Vendored third-party directories (`node_modules/`, `vendor/`, `third_party/`), protobuf/code-gen outputs (`@generated`, `DO NOT EDIT`), minified single-line bundles, binary artifacts disguised with source extensions, and symlink aliases cause multi-hour timeouts or exhaust LLM context windows on dead weight.
2. **Circular Dependency Knots:** If `auth.service` imports `auth.session` and `auth.session` imports `auth.service`, an autonomous agent cannot modernize one module's interface in isolation without breaking type-checking in the other. Cyclic knots must be detected and scheduled as atomic work units.
3. **Unordered Refactoring & Swarm Collisions:** Modernizing high-level orchestration modules before their leaf dependencies forces repeated rework. Work slices must be scheduled bottom-up (`Wave 0` leaf modules first, followed by `Wave 1..k` dependents) so an agent swarm can execute all `READY` slices within the same wave concurrently without write-conflict collisions.
4. **Zero-Trust Enclave Leakage:** Hardcoded PEM private keys, cloud credentials, and personal access tokens buried in legacy test fixtures must be quarantined before source context leaves a customer environment.

This tool implements the pre-flight inspection and partitioning workflow developed over 16 years of diagnosing enterprise source code scanners and partitioning large codebases (`bds_bom_Partition`).

## Scope & Architecture

* **Corridors (enforced in Layer 0):**
  * Token budget per slice: `500` to `2,000,000` tokens.
  * Maximum line length before minified-bundle pruning: `120` to `10,000` characters (default `1,000`).
  * Shannon byte-entropy threshold: `3.0` to `8.0` bits/byte (default `5.2` bits/byte when paired with lines `> 250` chars).
  * Maximum single source file size: `2 MB` (files exceeding `2 MB` or containing null bytes `\x00` in the first `8 KB` are pruned as binary/oversized blobs).
* **Outputs (`triage_and_plan_repository`):**
  * **Pre-Flight Scan Summary:** Per-file disposition (`ACTIVE_SOURCE`, `PRUNED_BLOAT`, `QUARANTINED_DLP`), `pruned_file_count` (omitting `PRUNED_BLOAT` records from the MCP JSON array by default via `include_pruned_files=False` to protect the calling agent's context window), estimated token counts, token reduction ratio, skipped symlinks, and nested directory exclusion paths (e.g. `packages/web/node_modules`).
  * **Modernization Plan:** Strongly Connected Components (SCCs), bottom-up wave numbers (`0..k`), and token-bounded agent work slices (`READY` vs `OVERSIZED_COUPLED_KNOT`).
  * **Human-in-the-Loop Agent Action Plan (`agent_action_plan_markdown`):** Reviewable Markdown specification detailing context reduction metrics, DLP quarantine gates, and per-wave **Max Parallel Agent Workers** for concurrent swarm execution.
  * **Neo4j Knowledge Graph Cypher (`neo4j_knowledge_graph_cypher`):** Deterministic `MERGE` statements exporting `(:CondensationNode)` vertices and `[:DEPENDS_ON]` edges into a graph database.

## Algorithms & Sources

| Subsystem | Model / Algorithm | Reference / Source |
| :--- | :--- | :--- |
| **Byte Entropy** | Shannon entropy $H(X) = -\sum p_i \log_2 p_i \in [0, 8]$ | Shannon (1948), *Bell Syst. Tech. J.* |
| **Token Estimation** | Conservative UTF-8 byte ceiling $\max(1, \lceil \text{bytes} / 3.5 \rceil)$ | Empirical BPE code tokenization bound |
| **Cycle Condensation** | Iterative Strongly Connected Components ($O(\|V\| + \|E\|)$) | Tarjan (1972), *SIAM J. Comput.* 1(2) |
| **Wave Scheduling** | Iterative bottom-up DAG level assignment ($\text{wave}(u) = 1 + \max \text{wave}(v)$) | Kahn (1962), *Commun. ACM* 5(11) |
| **Slice Packing** | Per-wave First-Fit Decreasing (FFD) bin packing by `(-tokens, scc_id)` | Johnson (1973), *J. Comput. Syst. Sci.* |

## Real-World Public Monorepo Benchmarks & Full-Stack Telemetry

To verify efficiency on modest customer VMs, the full pipeline (`scan_repository` $\rightarrow$ `plan_from_scan` $\rightarrow$ `render_agent_action_plan_markdown` $\rightarrow$ `export_neo4j_cypher`) was benchmarked inside a kernel-enforced **1-vCPU, 128 MB RAM, 0-Swap Linux cgroup v2 scope** (`systemd-run --user --scope -p MemoryMax=128M -p MemorySwapMax=0 -p CPUQuota=100%`) against two complex public repositories:
1. **`django/django`** (7,114 files, 86 MB on disk: 2,982 active modules / 5.64M active tokens, 4,132 pruned files / 11.13M pruned tokens, 16 circular dependency knots across 24 modernization waves, 4 documentation symlink loops skipped).
2. **`trpc/trpc` + 4,000 `node_modules` files** (5,686 files, 56 MB on disk: 852 active TypeScript modules / 775K active tokens, 4,834 pruned files / 13.69M pruned tokens, 3 circular dependency knots across 18 modernization waves).

| Target / Metric | Before Systems Optimization (`c97de85`) | After Systems Optimization (1-vCPU / 128 MB cgroup) | Improvement |
| :--- | :--- | :--- | :--- |
| **`trpc/trpc` (+4k `node_modules`) Total Time** | `2,149.14 ms` | **`282.62 ms`** | **7.6x faster** |
| **`trpc/trpc` Kernel Read Syscalls (`/proc/self/io syscr`)** | `11,373` syscalls (`48.30 MB` VFS read) | **`3,300` syscalls (`7.16 MB` VFS read)** | **71.0% fewer syscalls / 85.2% less I/O** |
| **`trpc/trpc` Peak Resident Memory (`VmHWM`)** | `30.43 MB` | **`22.14 MB`** (`0` network egress) | **27.2% lower peak RAM** |
| **`django/django` (7,114 files) Total Time** | `5,705.29 ms` | **`2,517.95 ms`** (`2,742.70 ms` in 128 MB cgroup) | **2.3x faster** (`9.3x` non-AST speedup) |
| **`django/django` Peak Resident Memory (`VmHWM`)** | `58.93 MB` | **`56.37 MB`** (`0` network egress) | Fits comfortably in 128 MB RAM |
| **TS `export` + 600 Indented Comments (25 KB)** | `7,140.39 ms` ($O(L^3)$ regex backtracking) | **`0.58 ms`** (linear single-pass regex) | **12,311x faster** |
| **20,000-Module FFD Slice Packing** | `5,181.13 ms` ($O(K^2 \log K)$ tuple re-sort) | **`97.44 ms`** (mutable bin + capacity pruning) | **53.2x faster** |

## Self-Hosting Example

Running `triage_and_plan_repository` on this repository itself (`token_budget=6000`):

```json
{
  "active_files_returned": 10,
  "pruned_file_count": 254,
  "quarantined_tokens": 0,
  "max_wave_depth": 4,
  "waves": {
    "src.monorepo_triage": 0,
    "src.monorepo_triage.layer0_invariants": 0,
    "src.monorepo_triage.layer1_scanner": 1,
    "tests.test_layer0_invariants": 1,
    "tests.test_layer1_scanner": 2,
    "src.monorepo_triage.layer2_slice_planner": 2,
    "tests.test_layer2_slice_planner": 3,
    "examples.run_django_sprint_demo": 3,
    "src.monorepo_triage.server": 3,
    "tests.test_server": 4
  }
}
```

## Why Static AST / Lexical Extraction is Used Over Build-Daemon Execution

In an enterprise pre-flight assessment over a customer VPN or VDI, executing arbitrary customer build wrappers (`mvn`, `gradle`, `bazel`, `npm postinstall`) before triage is slow and often fails due to missing internal artifact mirrors or native toolchain mismatches. Static AST parsing (`ast.parse` statement-block traversal for Python) and comment-stripped lexical import extraction (for TypeScript/JavaScript including `index` barrels, `export from`, and `@/` aliases, Go package directories, and Java/Maven sub-projects) run deterministically in milliseconds with zero network egress and zero untrusted code execution.

## Limitations & Uncertainty

* **Dynamic Dispatch & Reflection:** Static import extraction does not resolve runtime reflection (`importlib.import_module`, Java `Class.forName`, or dependency-injection XML/YAML wiring). Dynamic edges must be supplied via the `plan_dependency_graph` tool if needed.
* **Token Estimator Spread:** The $\lceil \text{bytes} / 3.5 \rceil$ heuristic is an intentional conservative upper bound across common code tokenizers (`cl100k_base` / `o200k_base` / SentencePiece), typically overestimating by 5% to 12% on dense punctuation so packed slices stay safely beneath hard context ceilings.
* **DLP Quarantine Scope:** Layer 1 screens active source files for structural secret patterns (PEM private keys, `AKIA*` AWS keys, `ghp_*` GitHub tokens). It is a pre-flight safety gate, not a replacement for full git-history secret scanning.

## How It Was Built (Prototype -> Cold Adversarial Breaker -> Regression Suite)

Asking a single LLM session to practice strict "Test-First TDD" is mostly theater: when the same model writes both the tests and the implementation in one pass, it writes happy-path tests that mirror its own blindspots.

Instead, this repository was built in three distinct stages:
1. **Working Nascent Prototype:** I specified the 4-layer architecture and domain invariants from my Black Duck field experience, and directed a fast code-generation model to build a working prototype with 48 baseline unit tests.
2. **Cold-Context Adversarial Red-Teaming & Live Repo Profiling:** Once the nascent tool was running, I spawned isolated, zero-context reviewer models tasked strictly with breaking the working code via live Python probes and profiled full-stack system telemetry (`/proc/self/io`, `/proc/self/status`, `cProfile`) against `django/django` and `trpc/trpc`. Across three adversarial rounds, that process uncovered **19 real defects and systems bottlenecks** that passed the original 48 happy-path tests (including full disk reads on pruned `node_modules` files, $O(L^3)$ TypeScript regex backtracking, $O(K^2 \log K)$ FFD tuple re-sorting, cross-service microservice alias collisions, false Python `__init__.py` cycles on PEP 8 imports, Go package directory resolution failures, TypeScript `index.ts` barrel blindspots, backtick comment corruption, symlink shadowing, and `scc_id` delimiter collisions).
3. **Regression Test Hardening:** Each concrete failure mode was turned into a failing regression test first and then fixed, expanding the suite to **75 passing unit tests**.

For the complete defect log, benchmark telemetry, and architectural breakdown, see [VERIFICATION_LOG.md](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md).

## Run

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 -m mypy --strict src tests examples/run_django_sprint_demo.py
ruff check src tests examples/run_django_sprint_demo.py
PYTHONPATH=src python3 examples/run_django_sprint_demo.py
PYTHONPATH=src python3 -m monorepo_triage.server
```
