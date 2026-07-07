"""Regenerate the bounded GOFAI Ortega case tables.

This helper is intentionally not imported by the runtime solver. It may use
the public ``dist/rubikscube`` mechanics for validation, but it must never use
``solve/group_theory``.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
if str(DIST) not in sys.path:
    sys.path.insert(0, str(DIST))

from rubikscube.core import ALL_MOVES  # noqa: E402

from cases import OLL_ALGORITHMS, PBL_ALGORITHMS, literal_move_count  # noqa: E402


def main() -> int:
    for table_name, table, max_cases, max_len in (
        ("OLL", OLL_ALGORITHMS, 8, 14),
        ("PBL", PBL_ALGORITHMS, 16, 18),
    ):
        if len(table) > max_cases:
            raise SystemExit(f"{table_name} table has too many cases: {len(table)} > {max_cases}")
        for case in table:
            if len(case.moves) > max_len:
                raise SystemExit(f"{table_name} case {case.name!r} is too long: {len(case.moves)} > {max_len}")
            illegal = [move for move in case.moves if move not in ALL_MOVES]
            if illegal:
                raise SystemExit(f"{table_name} case {case.name!r} has illegal moves: {illegal!r}")
    if literal_move_count() >= 256:
        raise SystemExit("literal case table move count must stay under 256")
    print(f"validated {len(OLL_ALGORITHMS)} OLL and {len(PBL_ALGORITHMS)} PBL algorithms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
