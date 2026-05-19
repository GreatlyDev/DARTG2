import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path


def wrap(text: str, width: int) -> str:
    if not text:
        return "[EMPTY]"
    return "\n".join(textwrap.fill(line, width=width, replace_whitespace=False) for line in text.splitlines())


def candidate_text(row: dict) -> str:
    return str(row.get("candidate_response") or row.get("candidate_text") or row.get("rewrite_text") or "")


def anchor_text(row: dict) -> str:
    return str(row.get("anchor_response") or row.get("anchor_text") or "")


def render(row: dict, index: int, total: int, width: int) -> str:
    line = "=" * width
    bits = [
        line,
        f"{index + 1}/{total}  {row.get('candidate_id') or row.get('record_id') or '[no id]'}",
        line,
        f"anchor_id: {row.get('anchor_id', '')}",
        f"dialect  : {row.get('dialect_family', '')}",
        f"model    : {row.get('model', '')}",
        f"status   : {row.get('generation_status', '')}",
        f"passed   : {row.get('passed_quality_filter', '')}",
        f"reasons  : {', '.join(row.get('rejection_reasons') or [])}",
        f"cleanup  : {', '.join(row.get('student_text_corrections') or [])}",
        f"change   : {row.get('composite_change_score', '')}",
        "",
        "ANCHOR",
        "-" * width,
        wrap(anchor_text(row), width),
        "",
        "CANDIDATE",
        "-" * width,
        wrap(candidate_text(row), width),
    ]
    return "\n".join(bits)


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse generated DART candidates one record at a time.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--start", type=int, default=1)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"No records in {args.input}")
    width = min(max(shutil.get_terminal_size((100, 20)).columns, 60), 140)
    index = max(0, min(args.start - 1, len(rows) - 1))
    while True:
        print(render(rows[index], index, len(rows), width))
        command = input("\n[Enter] next | p previous | j N jump | q quit > ").strip().lower()
        if command in {"q", "quit"}:
            return
        if command in {"", "n", "next"}:
            index = min(index + 1, len(rows) - 1)
        elif command in {"p", "prev", "previous"}:
            index = max(index - 1, 0)
        elif command.startswith("j "):
            try:
                index = max(0, min(int(command.split()[1]) - 1, len(rows) - 1))
            except (IndexError, ValueError):
                print("Use: j <record number>")


if __name__ == "__main__":
    main()
