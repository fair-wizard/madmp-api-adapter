"""Tiny console output helpers shared by the maDMP client scripts.

No dependencies beyond the standard library; colours are emitted only when
stdout is a terminal (so piping to a file or a pager stays readable).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return _c("1", text)


def dim(text: str) -> str:
    return _c("2", text)


def green(text: str) -> str:
    return _c("32", text)


def yellow(text: str) -> str:
    return _c("33", text)


def red(text: str) -> str:
    return _c("31", text)


def cyan(text: str) -> str:
    return _c("36", text)


def heading(text: str) -> None:
    print(f"\n{bold('=' * 3)} {bold(text)}")


def step(number: int, text: str) -> None:
    print(f"\n{bold(f'[{number}]')} {bold(text)}")


def info(text: str) -> None:
    print(f"  {dim('·')} {text}")


def ok(text: str) -> None:
    print(f"  {green('✓')} {text}")


def warn(text: str) -> None:
    print(f"  {yellow('!')} {text}")


def fail(text: str) -> None:
    print(f"  {red('✗')} {text}")


def kv(key: str, value: Any) -> None:
    print(f"  {dim(f'{key}:'):<24} {value}")


def trace(text: str) -> None:
    print(f"  {dim(text)}")


def dump(value: Any, *, max_lines: int | None = None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    lines = text.splitlines()
    shown = lines if max_lines is None else lines[:max_lines]
    for line in shown:
        print(f"  {line}")
    if max_lines is not None and len(lines) > max_lines:
        rest = len(lines) - max_lines
        print(f"  {dim(f'… {rest} more lines (use --json for the full body)')}")


def _cell(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > width:
        return text[: width - 1] + "…"
    return text.ljust(width)


def table(headers: list[str], rows: list[list[Any]], *, max_width: int = 44) -> None:
    if not rows:
        info("(no rows)")
        return
    widths = []
    for index, header in enumerate(headers):
        cells = [str(row[index]) for row in rows if row[index] is not None]
        longest = max([len(header), *[len(cell) for cell in cells]])
        widths.append(min(longest, max_width))
    header_line = "  ".join(
        bold(_cell(header, width)) for header, width in zip(headers, widths)
    )
    print(f"  {header_line}")
    print(f"  {dim('  '.join('-' * width for width in widths))}")
    for row in rows:
        line = "  ".join(_cell(cell, width) for cell, width in zip(row, widths))
        print(f"  {line}")


def confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input(f"  {yellow('?')} {question} [y/N] ").strip().lower()
    return answer in {"y", "yes"}
