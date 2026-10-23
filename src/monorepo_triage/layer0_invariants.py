"""Layer 0: Invariants, Boundary Corridor Validators, Path Confinement, and Token Estimator."""

import collections
import math
from pathlib import Path

MIN_TOKEN_BUDGET: int = 500
MAX_TOKEN_BUDGET: int = 2_000_000

MIN_LINE_LENGTH_LIMIT: int = 120
MAX_LINE_LENGTH_LIMIT: int = 10_000

MIN_ENTROPY_THRESHOLD: float = 3.0
MAX_ENTROPY_THRESHOLD: float = 8.0


def validate_token_budget(budget: int) -> int:
    """Validate token budget within [500, 2_000_000] corridor."""
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise TypeError(f"Token budget must be an integer, got {type(budget).__name__}")
    if budget < MIN_TOKEN_BUDGET or budget > MAX_TOKEN_BUDGET:
        raise ValueError(
            f"Token budget {budget} outside safe corridor [{MIN_TOKEN_BUDGET}, {MAX_TOKEN_BUDGET}]"
        )
    return budget


def validate_line_length_limit(max_chars: int) -> int:
    """Validate line length limit within [120, 10_000] corridor."""
    if isinstance(max_chars, bool) or not isinstance(max_chars, int):
        raise TypeError(f"Line length limit must be an integer, got {type(max_chars).__name__}")
    if max_chars < MIN_LINE_LENGTH_LIMIT or max_chars > MAX_LINE_LENGTH_LIMIT:
        raise ValueError(
            f"Line length limit {max_chars} outside corridor "
            f"[{MIN_LINE_LENGTH_LIMIT}, {MAX_LINE_LENGTH_LIMIT}]"
        )
    return max_chars


def validate_entropy_threshold(bits_per_byte: float) -> float:
    """Validate Shannon entropy threshold within [3.0, 8.0] bits/byte corridor."""
    if isinstance(bits_per_byte, bool) or not isinstance(bits_per_byte, (int, float)):
        raise TypeError(
            f"Entropy threshold must be a float or int, got {type(bits_per_byte).__name__}"
        )
    val = float(bits_per_byte)
    if not math.isfinite(val):
        raise ValueError(f"Entropy threshold must be finite, got {val}")
    if val < MIN_ENTROPY_THRESHOLD or val > MAX_ENTROPY_THRESHOLD:
        raise ValueError(
            f"Entropy threshold {val} outside corridor "
            f"[{MIN_ENTROPY_THRESHOLD}, {MAX_ENTROPY_THRESHOLD}]"
        )
    return val


def resolve_confined_path(root: Path, candidate: Path) -> Path:
    """Resolve candidate path strictly confined within root directory."""
    resolved_root = root.resolve()
    if candidate.is_absolute():
        resolved_candidate = candidate.resolve()
    else:
        resolved_candidate = (resolved_root / candidate).resolve()

    if not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError(
            f"Path escapes repository root confinement: {candidate} -> {resolved_candidate}"
        )
    return resolved_candidate


def shannon_entropy_bits_per_byte(data: bytes) -> float:
    """Calculate exact Shannon entropy in bits per byte [0.0, 8.0]."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"Expected bytes, got {type(data).__name__}")
    if len(data) == 0:
        return 0.0

    counts = collections.Counter(data)
    total = len(data)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return max(0.0, min(8.0, entropy))


def estimate_source_tokens(text: str) -> int:
    """Estimate token count deterministically for source code text."""
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    if len(text) == 0:
        return 0

    byte_len = len(text.encode("utf-8"))
    return max(1, math.ceil(byte_len / 3.5))


def validate_module_tokens(modules: dict[str, int]) -> dict[str, int]:
    """Validate that module map contains non-empty string keys and positive integer token weights."""
    if not isinstance(modules, dict):
        raise TypeError(f"Expected dict for modules, got {type(modules).__name__}")
    validated: dict[str, int] = {}
    for mod_id, weight in modules.items():
        if not isinstance(mod_id, str) or not mod_id.strip():
            raise ValueError(f"Module ID must be a non-empty string, got {mod_id!r}")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise TypeError(
                f"Token weight for {mod_id!r} must be an integer, got {type(weight).__name__}"
            )
        if weight < 0:
            raise ValueError(f"Token weight for {mod_id!r} must be non-negative (>= 0), got {weight}")
        validated[mod_id] = weight
    return validated

