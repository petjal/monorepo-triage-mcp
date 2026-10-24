# monorepo-triage-mcp

A deterministic legacy codebase pre-flight inspector, bloat pruner, Neo4j knowledge-graph exporter, and topological work-slice planner for autonomous coding agents, exposed as a Model Context Protocol (MCP) server (`triage_and_plan_repository` and `plan_dependency_graph`).

> **How This Was Built (16-Year Enterprise Triage Architecture + AI-Executed Implementation):**
> I am a 16-year enterprise systems and performance bottleneck engineer (`bds_bom_Partition` at Black Duck), not a career Python compiler developer. I built this proof-of-concept using the same **20% Human Architecture & Verification / 80% Autonomous AI Execution** workflow that enterprise modernization demands: I defined the 4-layer partitioning architecture, boundary invariants, and repository heuristics from my Black Duck field experience, and directed AI coding agents to write the Python code, unit tests, and documentation. Because single-pass AI code generation passed 48 happy-path unit tests while hiding severe architectural and systems edge-case bugs, I drove five rounds of isolated, zero-context adversarial red-teaming and Linux `cgroups v2` / `/proc/self/io` syscall profiling against live clones of `django/django` and `trpc/trpc` to isolate, verify, and lock down 34 defect remediations across an extensive regression test suite.

> **Repository Document Map (Tool vs. External Case Studies vs. Internal QA):**
> 1. **[`README.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/README.md) (This Document — The Tool):** Architecture, algorithms, and usage of the `monorepo-triage-mcp` server.
> 2. **[`CASE_STUDIES.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/CASE_STUDIES.md) (Assessing External Codebases *With* the Tool):** Plain-English executive brief and technical pre-flight findings generated **by** `monorepo-triage-mcp` when scanning **`trpc/trpc`** (Green Light: 100% Swarm-Ready across 27 waves) and **`django/django`** (Green Light: 3 Database Backend Knots across 68 waves) in preparation for a large-scale AI modernization project.
> 3. **[`VERIFICATION_LOG.md`](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md) (Auditing *Our Own* Source Code):** Multi-round cold-context adversarial red-teaming, 34 defect remediations, 85-test regression suite, and Linux cgroup telemetry of `monorepo-triage-mcp`'s own Python codebase.

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
  * **Modernization Plan:** Strongly Connected Components (SCCs), bottom-up wave numbers (`0..k`), and token-bounded agent work slices (`READY` vs `OVERSIZED_COUPLED_KNOT` vs `OVERSIZED_SINGLE_MODULE`).
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
1. **`django/django`** (7,085 files, 86 MB on disk: 2,982 active modules / 5.64M active tokens, 4,103 pruned files / 7.28M pruned tokens, 3 circular dependency knots across 68 modernization waves, 4 documentation symlink loops skipped; internal `.git/` packfiles and tool caches excluded from metric inflation).
2. **`trpc/trpc`** (1,656 files, 32 MB on disk: 852 active TypeScript modules / 775K active tokens, 804 pruned files / 1.37M pruned tokens, 3 circular dependency knots across 27 modernization waves; with +4,000 synthetic test files: 5,657 files, 4,805 pruned files / 1.40M pruned tokens).

| Target / Metric | Before Systems Optimization (`c97de85`) | After Systems Optimization (1-vCPU / 128 MB cgroup) | Improvement |
| :--- | :--- | :--- | :--- |
| **`trpc/trpc` (+4k `node_modules`) Total Time** | `2,149.14 ms` | **`282.62 ms`** | **7.6x faster** |
| **`trpc/trpc` Kernel Read Syscalls (`/proc/self/io syscr`)** | `11,373` syscalls (`48.30 MB` VFS read) | **`3,300` syscalls (`7.16 MB` VFS read)** | **71.0% fewer syscalls / 85.2% less I/O** |
| **`trpc/trpc` Peak Resident Memory (`VmHWM`)** | `30.43 MB` | **`22.14 MB`** (`0` network egress) | **27.2% lower peak RAM** |
| **`django/django` (7,085 files) Total Time** | `5,705.29 ms` | **`2,517.95 ms`** (`2,742.70 ms` in 128 MB cgroup) | **2.3x faster** (`9.3x` non-AST speedup) |
| **`django/django` Peak Resident Memory (`VmHWM`)** | `58.93 MB` | **`56.37 MB`** (`0` network egress) | Fits comfortably in 128 MB RAM |
| **TS `export` + 600 Indented Comments (25 KB)** | `7,140.39 ms` ($O(L^3)$ regex backtracking) | **`0.58 ms`** (linear single-pass regex) | **12,311x faster** |
| **20,000-Module FFD Slice Packing** | `5,181.13 ms` ($O(K^2 \log K)$ tuple re-sort) | **`97.44 ms`** (mutable bin + capacity pruning) | **53.2x faster** |

## Self-Hosting Example

Running `triage_and_plan_repository` on this repository itself (`token_budget=16000`, omitting `files` and `condensation_nodes` arrays for brevity):

```json
{
  "scan_summary": {
    "active_tokens": 44791,
    "pruned_tokens": 18904,
    "quarantined_tokens": 0,
    "token_reduction_ratio": 0.2968,
    "symlink_loops_skipped": [],
    "recommended_exclusions": [],
    "pruned_file_count": 7
  },
  "modernization_plan": {
    "cyclic_knot_count": 0,
    "max_wave_depth": 4,
    "total_active_tokens": 44791,
    "token_budget": 16000,
    "slices": [
      {
        "slice_id": "wave_0_slice_00",
        "wave": 0,
        "scc_ids": [
          "src.monorepo_triage",
          "src.monorepo_triage.layer0_invariants"
        ],
        "modules": [
          "src.monorepo_triage",
          "src.monorepo_triage.layer0_invariants"
        ],
        "total_tokens": 1300,
        "status": "READY"
      },
      {
        "slice_id": "wave_1_slice_00",
        "wave": 1,
        "scc_ids": [
          "src.monorepo_triage.layer1_scanner",
          "tests.test_layer0_invariants"
        ],
        "modules": [
          "src.monorepo_triage.layer1_scanner",
          "tests.test_layer0_invariants"
        ],
        "total_tokens": 8812,
        "status": "READY"
      },
      {
        "slice_id": "wave_2_slice_00",
        "wave": 2,
        "scc_ids": [
          "src.monorepo_triage.layer2_slice_planner",
          "tests.test_layer1_scanner"
        ],
        "modules": [
          "src.monorepo_triage.layer2_slice_planner",
          "tests.test_layer1_scanner"
        ],
        "total_tokens": 15519,
        "status": "READY"
      },
      {
        "slice_id": "wave_3_slice_00",
        "wave": 3,
        "scc_ids": [
          "src.monorepo_triage.server",
          "tests.test_layer2_slice_planner"
        ],
        "modules": [
          "src.monorepo_triage.server",
          "tests.test_layer2_slice_planner"
        ],
        "total_tokens": 11601,
        "status": "READY"
      },
      {
        "slice_id": "wave_3_slice_01",
        "wave": 3,
        "scc_ids": [
          "examples.run_django_sprint_demo"
        ],
        "modules": [
          "examples.run_django_sprint_demo"
        ],
        "total_tokens": 5681,
        "status": "READY"
      },
      {
        "slice_id": "wave_4_slice_00",
        "wave": 4,
        "scc_ids": [
          "tests.test_server"
        ],
        "modules": [
          "tests.test_server"
        ],
        "total_tokens": 1878,
        "status": "READY"
      }
    ]
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

Asking a single LLM session to practice strict "Test-First TDD" is mostly theater: when the same model writes both the tests and the implementation in one pass, it writes happy-path tests that mirror its own blindspots. Indeed, `git log` shows that the initial builder subagent committed Stage 1 as 8 alternating `test(layerX)` $\rightarrow$ `feat(layerX)` commits across 8 minutes (`fd91474`..`3946e55`). All 48 tests passed 100% on the first run, yet hid 20+ severe architectural and systems defects.

Instead, this repository was hardened in three distinct stages:
1. **Working Nascent Prototype:** I specified the 4-layer architecture and domain invariants from my Black Duck field experience, and directed a fast code-generation model to build a working prototype with 48 baseline unit tests.
2. **Cold-Context Adversarial Red-Teaming & Live Repo Profiling:** Once the nascent tool was running, I spawned isolated, zero-context reviewer models tasked strictly with breaking the working code via live Python probes and profiled full-stack system telemetry (`/proc/self/io`, `/proc/self/status`, `cProfile`) against `django/django` and `trpc/trpc`. Across five adversarial rounds, that process uncovered **28 real defects and systems bottlenecks** that passed the original 48 happy-path tests (including full disk reads on pruned `node_modules` files, $O(L^3)$ TypeScript regex backtracking, $O(K^2 \log K)$ FFD tuple re-sorting, cross-service microservice alias collisions, false Python `__init__.py` cycles on PEP 8 imports, AST module-load traversal false knots vs function-local lazy loading, Go package directory and stdlib resolution, TypeScript `.index` barrels and `@scope/pkg` aliases, backtick comment corruption, symlink shadowing, and `scc_id` delimiter collisions).
3. **Regression Test Hardening:** Each concrete failure mode was turned into a failing regression test first and then fixed, expanding the suite to **85 passing unit tests**.

For the complete defect log, benchmark telemetry, and architectural breakdown, see [VERIFICATION_LOG.md](https://github.com/petjal/monorepo-triage-mcp/blob/master/VERIFICATION_LOG.md).

## Run

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 -m mypy --strict src tests examples/run_django_sprint_demo.py
ruff check src tests examples/run_django_sprint_demo.py
PYTHONPATH=src python3 examples/run_django_sprint_demo.py
PYTHONPATH=src python3 -m monorepo_triage.server
```
