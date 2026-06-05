#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import libcst as cst
import libcst.matchers as m


class StripComments(cst.CSTTransformer):
    def leave_TrailingWhitespace(self, original_node, updated_node):
        if updated_node.comment is None:
            return updated_node
        return updated_node.with_changes(comment=None, whitespace=cst.SimpleWhitespace(""))

    def leave_EmptyLine(self, original_node, updated_node):
        if updated_node.comment is None:
            return updated_node
        return cst.RemoveFromParent()

    def leave_ParenthesizedWhitespace(self, original_node, updated_node):
        empty = [line for line in updated_node.empty_lines if line.comment is None]
        first = updated_node.first_line
        if first.comment is not None:
            first = first.with_changes(comment=None, whitespace=cst.SimpleWhitespace(""))
        return updated_node.with_changes(empty_lines=tuple(empty), first_line=first)


def _is_docstring(stmt: cst.BaseStatement) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    if len(stmt.body) != 1:
        return False
    inner = stmt.body[0]
    if not isinstance(inner, cst.Expr):
        return False
    val = inner.value
    return isinstance(val, cst.SimpleString) or isinstance(val, cst.ConcatenatedString)


class StripDocstrings(cst.CSTTransformer):
    def _filter_body(self, body):
        return [stmt for stmt in body if not _is_docstring(stmt)]

    def leave_Module(self, original_node, updated_node):
        new_body = self._filter_body(updated_node.body)
        return updated_node.with_changes(body=new_body)

    def _strip_indented(self, block):
        if not isinstance(block, cst.IndentedBlock):
            return block
        new_body = self._filter_body(block.body)
        if not new_body:
            new_body = [cst.SimpleStatementLine(body=[cst.Pass()])]
        return block.with_changes(body=new_body)

    def leave_FunctionDef(self, original_node, updated_node):
        return updated_node.with_changes(body=self._strip_indented(updated_node.body))

    def leave_ClassDef(self, original_node, updated_node):
        return updated_node.with_changes(body=self._strip_indented(updated_node.body))


def strip_python(src: str) -> str:
    tree = cst.parse_module(src)
    tree = tree.visit(StripComments())
    tree = tree.visit(StripDocstrings())
    out = tree.code
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


SQL_LINE_COMMENT = re.compile(r"^[ \t]*--.*?\n", re.MULTILINE)
SQL_TRAILING_COMMENT = re.compile(r"([^'\n])\s+--.*?$", re.MULTILINE)


def strip_sql(src: str) -> str:
    out = SQL_LINE_COMMENT.sub("", src)
    out = SQL_TRAILING_COMMENT.sub(r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def strip_wordlist(src: str) -> str:
    return "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#")) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root).resolve()

    py_files = sorted(root.rglob("*.py"))
    sql_files = sorted(root.rglob("*.sql"))
    txt_files = sorted(root.rglob("wordlist.txt"))

    for path in py_files:
        if "__pycache__" in path.parts or "/tests/" in str(path):
            continue
        src = path.read_text()
        try:
            out = strip_python(src)
        except cst.ParserSyntaxError as exc:
            print(f"[SKIP] {path}: {exc}", file=sys.stderr)
            continue
        if out != src:
            path.write_text(out)
            print(f"py   {path.relative_to(root)}")

    for path in sql_files:
        src = path.read_text()
        out = strip_sql(src)
        if out != src:
            path.write_text(out)
            print(f"sql  {path.relative_to(root)}")

    for path in txt_files:
        src = path.read_text()
        out = strip_wordlist(src)
        if out != src:
            path.write_text(out)
            print(f"txt  {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
