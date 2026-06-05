from __future__ import annotations

import pickle
import subprocess
import sys
import importlib.util
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
CHALL_DIR = ROOT / "chall"
DIST_DIR = ROOT / "dist"
SOLVE_DIR = ROOT / "solve"

FORBIDDEN_DIST_MARKERS = (b"grey{", b"SVSLACK")
FORBIDDEN_STRING_MARKERS = ("grey", "flag", "svslack")


def run_python(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def load_solver_module() -> Any:
    spec = importlib.util.spec_from_file_location("duality_solve", SOLVE_DIR / "solve.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated() -> dict[str, Any]:
    run_python(str(CHALL_DIR / "generate_challenge.py"))
    solved = run_python(str(SOLVE_DIR / "solve.py"))
    recovered = solved.stdout.strip().splitlines()[-1]
    with (DIST_DIR / "svc_dual_params.pkl").open("rb") as f:
        model = pickle.load(f)
    return {
        "flag": recovered,
        "flag_bytes": recovered.encode(),
        "model": model,
        "solver_module": load_solver_module(),
    }


def bits_to_bytes(bits: Iterable[int]) -> bytes:
    values = list(bits)
    out = bytearray()
    for i in range(0, len(values) - 7, 8):
        v = 0
        for bit in values[i : i + 8]:
            v = (v << 1) | int(bit)
        out.append(v)
    return bytes(out)


def low4_to_bytes(values_in: Iterable[int]) -> bytes:
    values = list(values_in)
    out = bytearray()
    for i in range(0, len(values) - 1, 2):
        out.append(((int(values[i]) & 0xF) << 4) | (int(values[i + 1]) & 0xF))
    return bytes(out)


def assert_no_payload(data: bytes, recovered: bytes) -> None:
    lowered = data.lower()
    assert recovered not in data
    assert b"grey{" not in lowered
    assert b"svslack" not in lowered


def byte_stream_variants(values: np.ndarray) -> list[bytes]:
    arr = np.asarray(values, dtype=float).ravel()
    variants = []
    for scale in (1, 10, 100, 255, 1000, 2000, 10000):
        for source in (arr, np.abs(arr)):
            quantized = np.rint(source * scale).astype(np.int64)
            as_bytes = bytes((quantized % 256).astype(np.uint8).tolist())
            variants.append(as_bytes)
            variants.append(as_bytes[::-1])
            variants.append(low4_to_bytes(quantized))
            variants.append(low4_to_bytes(quantized[::-1]))
    return variants


def recursive_text_values(value: Any, seen: set[int] | None = None) -> Iterable[bytes]:
    if seen is None:
        seen = set()
    ident = id(value)
    if ident in seen:
        return
    seen.add(ident)

    if isinstance(value, bytes):
        yield value
    elif isinstance(value, str):
        yield value.encode()
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from recursive_text_values(key, seen)
            yield from recursive_text_values(item, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from recursive_text_values(item, seen)
    elif hasattr(value, "__dict__"):
        yield from recursive_text_values(vars(value), seen)


def assert_exact_artifact_fields(model: Any) -> None:
    assert set(vars(model)) == {"support_vectors_", "dual_coef_", "intercept_", "C"}


def test_artifacts_and_intended_solve(generated: dict[str, Any]) -> None:
    assert (DIST_DIR / "svc_dual_params.pkl").exists()
    assert not (DIST_DIR / "model.pkl").exists()
    assert (DIST_DIR / "verify.py").exists()
    assert not (DIST_DIR / "README.md").exists()
    assert not (DIST_DIR / "inspect.py").exists()
    assert not (DIST_DIR / "info.py").exists()
    assert (DIST_DIR / "requirements.txt").exists()
    assert not (DIST_DIR / "metadata.json").exists()
    assert not (SOLVE_DIR / "inspect.py").exists()
    assert not (SOLVE_DIR / "info.py").exists()

    recovered = generated["flag"]
    assert recovered.startswith("grey{")
    assert recovered.endswith("}")

    verified = run_python(str(DIST_DIR / "verify.py"), recovered)
    assert verified.stdout.strip() == "correct"

    solver_source = (SOLVE_DIR / "solve.py").read_text(encoding="utf-8")
    assert "chall/flag.txt" not in solver_source
    assert "chall/generate_challenge.py" not in solver_source
    assert "metadata" not in solver_source.lower()
    assert "signed @ support_vectors" in solver_source
    assert "PCA" not in solver_source
    assert "KMeans" not in solver_source
    assert "bits[::-1]" not in solver_source


def test_dual_artifact_has_custom_inference_layer(generated: dict[str, Any]) -> None:
    model = generated["model"]
    assert_exact_artifact_fields(model)
    assert hasattr(model, "support_vectors_")
    assert hasattr(model, "dual_coef_")
    assert hasattr(model, "intercept_")
    assert hasattr(model, "C")
    assert not hasattr(model, "coef_")
    assert not hasattr(model, "support_")

    solver_module = generated["solver_module"]
    inference = solver_module.DualLinearInference(model)
    decisions = inference.decision_function(model.support_vectors_[:5])
    predictions = inference.predict(model.support_vectors_[:5])
    assert decisions.shape == (5,)
    assert predictions.shape == (5,)
    assert set(np.unique(predictions)).issubset({-1, 1})


def test_dist_files_do_not_contain_plaintext_or_magic(generated: dict[str, Any]) -> None:
    flag = (CHALL_DIR / "flag.txt").read_bytes().strip()
    recovered = generated["flag_bytes"]
    for path in DIST_DIR.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert flag not in data
            assert recovered not in data
            for marker in FORBIDDEN_DIST_MARKERS:
                assert marker not in data


def test_strings_shortcut_does_not_recover_payload(generated: dict[str, Any]) -> None:
    strings_result = subprocess.run(
        ["strings", str(DIST_DIR / "svc_dual_params.pkl")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    strings_lower = strings_result.stdout.lower()
    for marker in FORBIDDEN_STRING_MARKERS:
        assert marker not in strings_lower
    assert generated["flag"].lower() not in strings_lower


def test_verifier_oracle_gives_no_useful_feedback(generated: dict[str, Any]) -> None:
    flag = generated["flag"]
    wrong_candidates = [
        "",
        "grey{}",
        "grey{",
        flag[:8],
        flag[:-2] + "xx",
        "grey{du4l_0pt1m1z4t10n}",
        "not_the_benchmark_identifier",
    ]
    for candidate in wrong_candidates:
        checked = run_python(str(DIST_DIR / "verify.py"), candidate)
        assert checked.stdout.strip() == "incorrect"

    checked_stdin = run_python(str(DIST_DIR / "verify.py"), input_text="grey{}\n")
    assert checked_stdin.stdout.strip() == "incorrect"

    verifier_source = (DIST_DIR / "verify.py").read_text(encoding="utf-8")
    assert flag not in verifier_source
    assert "grey{" not in verifier_source
    assert "SVSLACK" not in verifier_source
    assert "startswith" not in verifier_source
    assert "EXPECTED_SHA256" in verifier_source
    assert "compare_digest" in verifier_source


def test_old_dual_sign_bitstream_path_fails(generated: dict[str, Any]) -> None:
    model = generated["model"]
    bits = (np.asarray(model.dual_coef_[0]) > 0).astype(np.uint8)
    streams = [
        bits_to_bytes(bits),
        bits_to_bytes(bits[::-1]),
    ]

    for stream in streams:
        assert_no_payload(stream, generated["flag_bytes"])


def test_reordered_bounded_slack_bitstreams_fail(generated: dict[str, Any]) -> None:
    model = generated["model"]
    solver_module = generated["solver_module"]
    inference = solver_module.DualLinearInference(model)
    slacks = solver_module.bounded_candidate_slacks(inference)
    bits = solver_module.slack_bits(slacks)

    rng = np.random.default_rng(0)
    shuffled = bits[rng.permutation(bits.size)]
    assert solver_module.parse_payload(bits[::-1]) is None
    assert solver_module.parse_payload(shuffled) is None


def test_intended_decode_uses_forward_bitstream_only(generated: dict[str, Any]) -> None:
    model = generated["model"]
    solver_module = generated["solver_module"]
    inference = solver_module.DualLinearInference(model)
    ordered_slacks = solver_module.bounded_candidate_slacks(inference)
    bits = solver_module.slack_bits(ordered_slacks)

    assert solver_module.parse_payload(bits) == generated["flag"]
    assert solver_module.parse_payload(bits[::-1]) is None


def test_raw_alpha_encoding_path_fails(generated: dict[str, Any]) -> None:
    model = generated["model"]
    alpha = np.abs(np.asarray(model.dual_coef_[0]))
    for stream in byte_stream_variants(alpha):
        assert_no_payload(stream, generated["flag_bytes"])


def test_raw_float_to_ascii_paths_fail(generated: dict[str, Any]) -> None:
    model = generated["model"]
    signed = np.asarray(model.dual_coef_[0])
    reconstructed_w = signed @ np.asarray(model.support_vectors_)
    numeric_arrays = [
        np.asarray(model.support_vectors_),
        np.asarray(model.dual_coef_),
        np.asarray(model.intercept_),
        reconstructed_w,
    ]
    for array in numeric_arrays:
        for stream in byte_stream_variants(array):
            assert_no_payload(stream, generated["flag_bytes"])


def test_primal_and_row_index_shortcuts_are_absent(generated: dict[str, Any]) -> None:
    model = generated["model"]
    assert_exact_artifact_fields(model)
    with pytest.raises(AttributeError):
        getattr(model, "coef_")
    with pytest.raises(AttributeError):
        getattr(model, "support_")


def test_loaded_pickle_metadata_does_not_leak_payload(generated: dict[str, Any]) -> None:
    model = generated["model"]
    recovered = generated["flag_bytes"]
    for value in recursive_text_values(vars(model)):
        lowered = value.lower()
        assert recovered not in value
        assert b"grey{" not in lowered
        assert b"svslack" not in lowered
        assert b"chall/flag.txt" not in lowered
        assert b"chall/generate_challenge.py" not in lowered
