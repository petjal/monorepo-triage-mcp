"""Layer 0: Invariants, Boundary Corridor Validators, Path Confinement, and Token Estimator."""

from pathlib import Path


def validate_token_budget(budget: int) -> int:
    """Validate token budget within [500, 2_000_000] corridor."""
    raise NotImplementedError("validate_token_budget contract not implemented")


def validate_line_length_limit(max_chars: int) -> int:
    """Validate line length limit within [120, 10_000] corridor."""
    raise NotImplementedError("validate_line_length_limit contract not implemented")


def validate_entropy_threshold(bits_per_byte: float) -> float:
    """Validate Shannon entropy threshold within [3.0, 8.0] bits/byte corridor."""
    raise NotImplementedError("validate_entropy_threshold contract not implemented")


def resolve_confined_path(root: Path, candidate: Path) -> Path:
    """Resolve candidate path strictly confined within root directory."""
    raise NotImplementedError("resolve_confined_path contract not implemented")


def shannon_entropy_bits_per_byte(data: bytes) -> float:
    """Calculate exact Shannon entropy in bits per byte [0.0, 8.0]."""
    raise NotImplementedError("shannon_entropy_bits_per_byte contract not implemented")


def estimate_source_tokens(text: str) -> int:
    """Estimate token count deterministically for source code text."""
    raise NotImplementedError("estimate_source_tokens contract not implemented")
