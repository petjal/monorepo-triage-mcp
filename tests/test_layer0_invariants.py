"""Tests for Layer 0 Invariants, Boundary Corridors, and Numerical Substrates."""

import math
from pathlib import Path

import pytest

from monorepo_triage.layer0_invariants import (
    estimate_source_tokens,
    resolve_confined_path,
    shannon_entropy_bits_per_byte,
    validate_entropy_threshold,
    validate_line_length_limit,
    validate_token_budget,
)


class TestTokenBudgetValidation:
    def test_valid_token_budgets(self) -> None:
        assert validate_token_budget(500) == 500
        assert validate_token_budget(16000) == 16000
        assert validate_token_budget(128000) == 128000
        assert validate_token_budget(2_000_000) == 2_000_000

    def test_boundary_violations(self) -> None:
        with pytest.raises(ValueError, match="Token budget"):
            validate_token_budget(499)
        with pytest.raises(ValueError, match="Token budget"):
            validate_token_budget(2_000_001)

    def test_type_enforcement(self) -> None:
        with pytest.raises(TypeError):
            validate_token_budget(True)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_token_budget(False)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_token_budget(16000.0)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_token_budget("16000")  # type: ignore[arg-type]


class TestLineLengthLimitValidation:
    def test_valid_limits(self) -> None:
        assert validate_line_length_limit(120) == 120
        assert validate_line_length_limit(1000) == 1000
        assert validate_line_length_limit(10_000) == 10_000

    def test_boundary_violations(self) -> None:
        with pytest.raises(ValueError, match="Line length limit"):
            validate_line_length_limit(119)
        with pytest.raises(ValueError, match="Line length limit"):
            validate_line_length_limit(10_001)

    def test_type_enforcement(self) -> None:
        with pytest.raises(TypeError):
            validate_line_length_limit(True)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_line_length_limit(1000.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_line_length_limit("1000")  # type: ignore[arg-type]


class TestEntropyThresholdValidation:
    def test_valid_thresholds(self) -> None:
        assert validate_entropy_threshold(3.0) == pytest.approx(3.0)
        assert validate_entropy_threshold(5.2) == pytest.approx(5.2)
        assert validate_entropy_threshold(8.0) == pytest.approx(8.0)

    def test_boundary_violations(self) -> None:
        with pytest.raises(ValueError, match="Entropy threshold"):
            validate_entropy_threshold(2.99)
        with pytest.raises(ValueError, match="Entropy threshold"):
            validate_entropy_threshold(8.01)

    def test_non_finite_values(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_entropy_threshold(float("nan"))
        with pytest.raises(ValueError, match="finite"):
            validate_entropy_threshold(float("inf"))
        with pytest.raises(ValueError, match="finite"):
            validate_entropy_threshold(float("-inf"))

    def test_type_enforcement(self) -> None:
        with pytest.raises(TypeError):
            validate_entropy_threshold(True)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            validate_entropy_threshold("5.2")  # type: ignore[arg-type]


class TestPathConfinement:
    def test_valid_nested_path(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subfile = repo / "src" / "main.py"
        subfile.parent.mkdir()
        subfile.write_text("print('hello')")

        resolved = resolve_confined_path(repo, Path("src/main.py"))
        assert resolved == subfile.resolve()

    def test_escape_via_dot_dot_rejected(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        with pytest.raises(ValueError, match="escapes repository root"):
            resolve_confined_path(repo, Path("../outside.py"))

    def test_escape_via_symlink_rejected(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("classified")

        escaping_symlink = repo / "sym_link"
        escaping_symlink.symlink_to(outside_file)

        with pytest.raises(ValueError, match="escapes repository root"):
            resolve_confined_path(repo, escaping_symlink)


class TestShannonEntropy:
    def test_empty_bytes(self) -> None:
        assert shannon_entropy_bits_per_byte(b"") == 0.0

    def test_single_byte_repeat(self) -> None:
        assert shannon_entropy_bits_per_byte(b"AAAAA" * 100) == 0.0

    def test_two_equal_symbols(self) -> None:
        assert shannon_entropy_bits_per_byte(b"AB" * 50) == pytest.approx(1.0, abs=1e-6)

    def test_uniform_256_bytes(self) -> None:
        data = bytes(range(256))
        assert shannon_entropy_bits_per_byte(data) == pytest.approx(8.0, abs=1e-6)

    def test_ascii_source_code_typical_entropy(self) -> None:
        code = b"def calculate_total(items):\n    return sum(item.price for item in items)\n"
        h = shannon_entropy_bits_per_byte(code)
        assert 3.5 <= h <= 5.0


class TestEstimateSourceTokens:
    def test_empty_string(self) -> None:
        assert estimate_source_tokens("") == 0

    def test_single_character(self) -> None:
        assert estimate_source_tokens("x") == 1

    def test_typical_code(self) -> None:
        text = "def hello():\n    return 'world'\n"
        encoded_len = len(text.encode("utf-8"))
        expected = math.ceil(encoded_len / 3.5)
        assert estimate_source_tokens(text) == expected

    def test_type_enforcement(self) -> None:
        with pytest.raises(TypeError):
            estimate_source_tokens(123)  # type: ignore[arg-type]
