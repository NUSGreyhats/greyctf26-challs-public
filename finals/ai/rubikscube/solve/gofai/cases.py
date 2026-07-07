"""Tiny Ortega-style case tables for the GOFAI strategy.

Generated from public 2x2 cube mechanics and standard Ortega stage
constraints; not generated from or derived through ``solve/group_theory``.
All algorithms are stored in relative notation with the acquired first face
treated as relative D.
"""

from __future__ import annotations

from dataclasses import dataclass

MoveToken = str

PROVENANCE = (
    "generated from public rubikscube mechanics and Ortega stage constraints; "
    "no solve/group_theory data path"
)


@dataclass(frozen=True, slots=True)
class CaseAlgorithm:
    name: str
    moves: tuple[MoveToken, ...]


OLL_ALGORITHMS: tuple[CaseAlgorithm, ...] = (
    CaseAlgorithm("left-bar", ("L", "U", "L'", "U", "F", "U'", "F'")),
    CaseAlgorithm("anti-sune", ("R", "U", "U", "R'", "U'", "R", "U'", "R'")),
    CaseAlgorithm("front-bar", ("F", "U'", "F'", "U", "R'", "F'", "R")),
    CaseAlgorithm("t", ("R", "U", "R'", "U'", "R'", "F", "R", "F'")),
    CaseAlgorithm("l", ("F", "R'", "F'", "R", "U", "R", "U'", "R'")),
    CaseAlgorithm("u", ("R", "R", "U", "U", "R", "U", "U", "R", "R")),
    CaseAlgorithm("bar-swap", ("F", "R'", "F'", "U", "R'", "U'", "R")),
    CaseAlgorithm("bar-twist", ("F", "R'", "F'", "R", "F'", "U", "F")),
)

PBL_ALGORITHMS: tuple[CaseAlgorithm, ...] = (
    CaseAlgorithm("adjacent-both", ("R", "R", "U'", "B", "B", "U", "U", "R", "R", "U'", "R", "R")),
    CaseAlgorithm("adjacent-u", ("R", "U'", "R", "F", "F", "R'", "U", "R'")),
    CaseAlgorithm("adjacent-u-inverse", ("R", "U'", "R", "F", "F", "R'", "U", "R'")),
    CaseAlgorithm("diag-u", ("F", "R", "U'", "R'", "U'", "R", "U", "R'", "F'", "R", "U", "R'", "U'", "R'", "F", "R", "F'")),
    CaseAlgorithm("diag-both", ("R", "R", "F", "F", "R", "R")),
    CaseAlgorithm("adjacent-alt", ("R", "U", "R'", "F'", "R", "U", "R'", "U'", "R'", "F", "R", "R", "U'", "R'")),
    CaseAlgorithm("adjacent-alt-inverse", ("R", "U", "R'", "U", "R'", "F", "R", "R", "U'", "R'", "U'", "R", "U", "R'", "F'")),
    CaseAlgorithm("front-adjacent", ("F", "U'", "F", "R", "R", "F'", "U", "F'")),
    CaseAlgorithm("front-adjacent-inverse", ("F", "U'", "F", "R", "R", "F'", "U", "F'")),
    CaseAlgorithm("back-adjacent", ("B", "U'", "B", "L", "L", "B'", "U", "B'")),
    CaseAlgorithm("sune-perm", ("R", "U", "R'", "U'", "R'", "F", "R", "R", "U'", "R'", "U'", "R", "U", "R'", "F'")),
    CaseAlgorithm("axis-diagonal", ("B", "F", "R", "B", "F", "U'", "U'", "R'", "L'", "F'", "R'", "L'")),
    CaseAlgorithm("paired-adjacent", ("R'", "B", "L'", "U'", "F'", "U'", "L'", "R'", "F'", "D'", "B'", "F'")),
    CaseAlgorithm("offset-cycle", ("D", "F", "R'", "F", "R'", "D'", "R", "R", "D'", "R'", "F", "U", "R")),
    CaseAlgorithm("lower-offset", ("D", "R'", "F", "L'", "D", "D", "R", "D", "B")),
    CaseAlgorithm("side-offset", ("L", "F", "B", "D'", "L'", "D", "L'", "F'", "U", "F'", "L'", "D'", "F'")),
)

RESEARCH_OLL_ALGORITHMS: tuple[CaseAlgorithm, ...] = (
    CaseAlgorithm("research-oll-000", ("R", "B", "L'", "R'", "U", "R'", "B'", "R", "L", "F")),
    CaseAlgorithm("research-oll-001", ("B", "U'", "R", "B'", "R'", "B'", "U")),
    CaseAlgorithm("research-oll-002", ("F", "U'", "F'", "L'", "F'", "L", "F")),
    CaseAlgorithm("research-oll-003", ("F'", "U", "F", "R", "F", "R'", "F'")),
    CaseAlgorithm("research-oll-004", ("L", "U'", "B'", "U", "B", "L'")),
    CaseAlgorithm("research-oll-005", ("R", "B'", "R", "B", "U", "R'")),
    CaseAlgorithm("research-oll-006", ("F'", "U'", "F", "R'", "F", "R", "F'")),
)

RESEARCH_PBL_ALGORITHMS: tuple[CaseAlgorithm, ...] = (
    CaseAlgorithm("research-pbl-000", ("L'", "B'", "U", "B'", "F'", "L", "F", "L")),
    CaseAlgorithm("research-pbl-001", ("B'", "U'", "L'", "U'", "U'", "R", "F'", "L")),
    CaseAlgorithm("research-pbl-002", ("L'", "D'", "L'", "F'", "F'", "L", "D", "L")),
    CaseAlgorithm("research-pbl-003", ("B'", "U", "L", "D'", "D'", "R'", "D'", "L'")),
    CaseAlgorithm("research-pbl-004", ("D", "F", "R'", "D'", "R", "R", "D", "R", "F'")),
    CaseAlgorithm("research-pbl-005", ("U", "L", "U", "R", "U", "U", "L'", "D'", "B'")),
    CaseAlgorithm("research-pbl-006", ("D", "R", "D", "U", "F", "L'", "B", "L'", "R'", "U'", "B")),
    CaseAlgorithm("research-pbl-007", ("R", "F", "R'", "F'", "R", "B", "R'", "F", "R", "B'", "F'", "R'")),
    CaseAlgorithm("research-pbl-008", ("L'", "F", "L'", "B", "U", "R", "U'", "D'", "F'", "D", "B'", "F'")),
    CaseAlgorithm("research-pbl-009", ("R'", "B", "L'", "D'", "F'", "L'", "R'", "D", "R", "F'", "R", "F'")),
    CaseAlgorithm("research-pbl-010", ("L'", "D'", "L'", "B'", "D", "B'", "B'", "D", "B'", "L'", "B'", "L'")),
    CaseAlgorithm("research-pbl-011", ("D", "R", "D", "U", "R'", "D", "F", "D", "B'", "R", "F", "R'", "F'")),
    CaseAlgorithm("research-pbl-012", ("R", "L", "U", "F", "R'", "F'", "U", "L'", "R'", "D'", "L", "D'", "B")),
    CaseAlgorithm("research-pbl-013", ("B'", "U'", "R'", "F'", "D", "L", "D", "L'", "D", "B", "D'", "L'")),
    CaseAlgorithm("research-pbl-014", ("D", "F", "B", "R", "F", "D", "R", "D", "L'", "F", "L'", "U'", "F")),
    CaseAlgorithm("research-pbl-015", ("B'", "D'", "U'", "L'", "U'", "L", "D", "B", "D'", "B'", "D", "L'")),
    CaseAlgorithm("research-pbl-016", ("D", "F", "D", "R", "D", "F", "D'", "F'", "D'", "R'", "D'", "R'", "F'")),
    CaseAlgorithm("research-pbl-017", ("U", "F", "L'", "B", "U", "D", "R'", "B", "L'")),
    CaseAlgorithm("research-pbl-018", ("F", "U'", "R'", "F'", "L", "B", "R'", "F'", "D'", "L'", "R'", "F'")),
    CaseAlgorithm("research-pbl-019", ("L'", "F", "L'", "B", "R'", "D'", "U'", "F'", "L", "F'", "U'", "F'")),
    CaseAlgorithm("research-pbl-020", ("F", "L", "U", "L", "U", "F", "U", "F'", "U", "L'", "U'", "F'")),
    CaseAlgorithm("research-pbl-021", ("F", "R'", "D'", "R'", "L'", "F'", "L", "F'")),
    CaseAlgorithm("research-pbl-022", ("F'", "L", "U", "B", "D", "B", "D", "U", "L'", "U'", "B'", "F'")),
)

DIRECT_RESEARCH_PBL_ALGORITHMS: tuple[CaseAlgorithm, ...] = (
    CaseAlgorithm("direct-pbl-000", ("L", "B", "L", "B'", "D", "L", "U", "L", "F'", "L'", "D'")),
    CaseAlgorithm("direct-pbl-001", ("B", "F", "D'", "L", "R", "B'", "R'", "D'", "B'", "U", "L")),
    CaseAlgorithm("direct-pbl-002", ("L", "U", "B'", "L'", "L'", "B", "L", "B")),
    CaseAlgorithm("direct-pbl-003", ("L", "U'", "R'", "B", "L", "U'", "L'", "F'", "L'", "B'", "F'", "L'")),
    CaseAlgorithm("direct-pbl-004", ("L'", "F'", "U", "F'", "U", "L", "U", "F", "L'", "F'", "U'", "F'")),
    CaseAlgorithm("direct-pbl-005", ("F", "L", "D", "B'", "D", "L", "U'", "D'", "B", "D'", "R'", "L'")),
    CaseAlgorithm("direct-pbl-006", ("D", "B'", "D", "U", "L", "B", "L", "D", "F'")),
    CaseAlgorithm("direct-pbl-007", ("D", "L", "R", "B'", "L'", "D'", "R'", "L'", "F'", "B'", "L")),
    CaseAlgorithm("direct-pbl-008", ("L'", "U'", "B", "U'", "U'", "F'", "R'", "B'")),
    CaseAlgorithm("direct-pbl-009", ("L", "F", "D", "B'", "D", "L", "D", "L", "B'")),
    CaseAlgorithm("direct-pbl-010", ("F'", "L", "F'", "L'", "D'", "F'", "U'", "D'", "L", "F'", "R'", "L'")),
    CaseAlgorithm("direct-pbl-011", ("B", "R", "U", "B", "F", "U'", "B", "U'", "F'", "R'", "B'")),
    CaseAlgorithm("direct-pbl-012", ("R", "U", "R", "F", "B", "U", "B'", "R'", "U")),
    CaseAlgorithm("direct-pbl-013", ("B", "R", "U", "R", "B", "D'", "F'", "B'", "R'", "U'", "L'", "R'")),
    CaseAlgorithm("direct-pbl-014", ("B", "R", "U", "L", "D", "F'", "D", "U", "R'", "U", "L'", "R'")),
    CaseAlgorithm("direct-pbl-015", ("B'", "L'", "R'", "U'", "B'", "R'", "D'", "L", "B'", "L'", "F'", "B'")),
    CaseAlgorithm("direct-pbl-016", ("L'", "F'", "U", "L'", "L'", "D'", "L'", "B'")),
    CaseAlgorithm("direct-pbl-017", ("D", "F'", "L'", "D'", "F", "B", "R", "F", "L'", "B'", "R")),
    CaseAlgorithm("direct-pbl-018", ("R'", "U", "F", "R'", "B", "L", "U", "L", "U", "L'", "B'", "F'")),
    CaseAlgorithm("direct-pbl-019", ("R'", "F", "D", "F'", "F'", "U'", "L'", "F")),
    CaseAlgorithm("direct-pbl-020", ("F'", "L'", "B'", "U'", "F", "B", "R", "F'", "U'", "D'", "L'", "F'")),
    CaseAlgorithm("direct-pbl-021", ("L'", "F'", "R'", "U'", "D'", "F'", "D", "L")),
    CaseAlgorithm("direct-pbl-022", ("D", "L", "B", "D'", "B", "B", "U", "R", "B")),
    CaseAlgorithm("direct-pbl-023", ("F'", "U", "F'", "L'", "R'", "U", "R", "F")),
    CaseAlgorithm("direct-pbl-024", ("F'", "U", "B'", "U", "B'", "D", "L'", "R'", "F'", "U'", "L'", "R'")),
    CaseAlgorithm("direct-pbl-025", ("B'", "R'", "U'", "B", "R", "B", "D", "U", "R", "U", "L'", "R'")),
    CaseAlgorithm("direct-pbl-026", ("D", "F", "R'", "D'", "L'", "F", "R", "U'", "F")),
    CaseAlgorithm("direct-pbl-027", ("F'", "D", "F'", "U", "F'", "L", "D", "F", "R", "F'", "D'", "F'")),
    CaseAlgorithm("direct-pbl-028", ("B", "U'", "R'", "U'", "B", "U'", "L'", "R'", "B", "U", "L'", "R'")),
    CaseAlgorithm("direct-pbl-029", ("B", "L", "D", "R", "U", "F'", "U", "D", "L'", "D'", "R'", "L'")),
    CaseAlgorithm("direct-pbl-030", ("D", "F", "D", "R", "D", "D", "R'", "D'", "F'")),
    CaseAlgorithm("direct-pbl-031", ("R", "F", "R", "F", "L", "U", "L'", "R'", "B'", "U", "L'", "R'")),
    CaseAlgorithm("direct-pbl-032", ("L", "D'", "L'", "D'", "F", "D", "B'", "R", "F", "L", "F")),
    CaseAlgorithm("direct-pbl-033", ("R", "D", "R", "F'", "F'", "R'", "U'", "B")),
    CaseAlgorithm("direct-pbl-034", ("R", "D", "R", "B", "U'", "R'", "R'", "U'", "R'", "U'", "R'", "B'")),
    CaseAlgorithm("direct-pbl-035", ("B", "U", "B", "L'", "R'", "D", "F", "L", "D'", "U'", "B'", "F'")),
    CaseAlgorithm("direct-pbl-036", ("D", "B'", "D", "L", "B", "F", "D", "R", "F")),
    CaseAlgorithm("direct-pbl-037", ("R", "U", "R'", "U'", "R", "F'", "L'", "B'", "D'", "L'", "U'")),
    CaseAlgorithm("direct-pbl-038", ("D", "L", "B", "F", "U", "F'", "L'", "U", "D")),
    CaseAlgorithm("direct-pbl-039", ("B", "L", "D", "L", "B", "U'", "F'", "B'", "L'", "D", "R'", "L'")),
    CaseAlgorithm("direct-pbl-040", ("F", "L", "U", "F'", "L", "U'", "F'", "U'", "F", "D'", "U'", "F'")),
    CaseAlgorithm("direct-pbl-041", ("F", "B", "U", "B'", "D'", "R'", "U", "L'", "F'", "L'", "F'", "L'")),
    CaseAlgorithm("direct-pbl-042", ("R'", "D", "F'", "R", "F'", "D", "B", "D'", "L'", "D'", "R'")),
    CaseAlgorithm("direct-pbl-043", ("R'", "B'", "R'", "B'", "R'", "F'", "D'", "U'", "R'", "U", "L'", "R'")),
    CaseAlgorithm("direct-pbl-044", ("F", "L", "F", "L'", "R'", "U'", "B", "R", "D'")),
    CaseAlgorithm("direct-pbl-045", ("R", "U'", "L'", "F", "L'", "B", "U", "F'", "U'", "L'", "U'", "F'")),
    CaseAlgorithm("direct-pbl-046", ("L", "D", "B'", "D'", "U'", "R'", "B'", "L'", "D'")),
    CaseAlgorithm("direct-pbl-047", ("R", "L", "B", "R", "U'", "B'", "U", "B", "L", "F'", "U'")),
    CaseAlgorithm("direct-pbl-048", ("F'", "L'", "U'", "F'", "L'", "R'", "U'", "F'", "U'", "D'", "L'", "B'")),
    CaseAlgorithm("direct-pbl-049", ("F", "U", "L", "U'", "U'", "L'", "U'", "F'")),
)

def literal_move_count() -> int:
    return sum(len(case.moves) for case in OLL_ALGORITHMS + PBL_ALGORITHMS)


__all__ = [
    "CaseAlgorithm",
    "DIRECT_RESEARCH_PBL_ALGORITHMS",
    "OLL_ALGORITHMS",
    "PBL_ALGORITHMS",
    "PROVENANCE",
    "RESEARCH_OLL_ALGORITHMS",
    "RESEARCH_PBL_ALGORITHMS",
    "literal_move_count",
]
