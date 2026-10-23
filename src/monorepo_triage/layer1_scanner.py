"""Layer 1: Deterministic Repository Scanner, Bloat Pruning, DLP Quarantine, and AST Dependency Extractor."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FileDisposition = Literal["ACTIVE_SOURCE", "PRUNED_BLOAT", "QUARANTINED_DLP"]


@dataclass(frozen=True)
class FileRecord:
    rel_path: str
    module_id: str | None
    disposition: FileDisposition
    reason: str
    estimated_tokens: int
    shannon_entropy: float
    max_line_length: int
    imports: tuple[str, ...]


@dataclass(frozen=True)
class ScanSummary:
    root_path: str
    files: tuple[FileRecord, ...]
    active_tokens: int
    pruned_tokens: int
    quarantined_tokens: int
    token_reduction_ratio: float
    symlink_loops_skipped: tuple[str, ...]
    recommended_exclusions: tuple[str, ...]


def scan_repository(
    root: Path,
    max_line_length: int = 1000,
    entropy_threshold: float = 5.2,
) -> ScanSummary:
    """Scan repository deterministically, classifying bloat, secrets, and active source."""
    raise NotImplementedError("scan_repository contract not implemented")
