from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "dist"

FORBIDDEN = [
    b"grey{",
    b"grey{de_gr4dienT_1eaK4ge_rUnz_D3eP_iNdeeD_1906.08935}",
    b"original_sample",
    b"flag.txt",
    b"LastGradientNet",
    b"_initialize_for_challenge",
    b"MODEL_SEED",
    b"GENERATION_SEED",
    b"TRUE_LABEL",
    b"chall/",
    b"/chall",
    b"private/",
    b"/private",
]


def main() -> None:
    failures: list[str] = []
    for path in sorted(PUBLIC_DIR.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        for needle in FORBIDDEN:
            if needle in data:
                failures.append(f"{path.relative_to(ROOT)} contains forbidden marker {needle!r}")

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)

    print("public leak check passed")


if __name__ == "__main__":
    main()
