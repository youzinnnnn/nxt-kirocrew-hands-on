#!/usr/bin/env python3
"""Merge per-warehouse intermediate JSON files into result.json.

Reads the three intermediate files produced by task_warehouse.py, then builds
result.json following practice/출력형식.md. Uses only the standard library.

Exit codes: 0 ok, 1 missing/invalid intermediate, 2 argument/IO error.
"""
import argparse
import json
import sys
from pathlib import Path

WAREHOUSES = ["A", "B", "C"]


def load_intermediate(intermediate_dir: Path, warehouse: str) -> dict:
    path = intermediate_dir / f"warehouse-{warehouse.lower()}.json"
    if not path.exists():
        print(f"missing intermediate file: {path}", file=sys.stderr)
        raise SystemExit(1)
    try:
        with path.open(encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"invalid intermediate {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)


def build_result(intermediate_dir: Path) -> dict:
    parts = {w: load_intermediate(intermediate_dir, w) for w in WAREHOUSES}

    source_files = sorted(p["source_file"] for p in parts.values())
    warehouse_totals = {w: int(parts[w]["total"]) for w in WAREHOUSES}

    item_totals: dict[str, int] = {}
    low_stock: list[dict] = []
    for w in WAREHOUSES:
        part = parts[w]
        for item, qty in part["items"].items():
            item_totals[item] = item_totals.get(item, 0) + int(qty)
        for row in part["low_stock"]:
            low_stock.append(
                {
                    "item": row["item"],
                    "quantity": int(row["quantity"]),
                    "warehouse": w,
                }
            )

    grand_total = sum(warehouse_totals.values())

    return {
        "source_files": source_files,
        "warehouse_totals": warehouse_totals,
        "item_totals": item_totals,
        "grand_total": grand_total,
        "low_stock_basis": "warehouse_row",
        "threshold": 5,
        "low_stock": low_stock,
    }


def build_report(result: dict) -> str:
    lines: list[str] = []
    lines.append("# 창고 재고 집계 보고서")
    lines.append("")
    lines.append(f"- 원본 파일: {', '.join(result['source_files'])}")
    lines.append(f"- 저재고 기준(low_stock_basis): `{result['low_stock_basis']}`"
                 f" (창고별 행 수량 < {result['threshold']})")
    lines.append(f"- 전체 합계(grand_total): **{result['grand_total']}**")
    lines.append("")

    lines.append("## 창고별 합계")
    lines.append("")
    lines.append("| 창고 | 합계 |")
    lines.append("| --- | ---: |")
    for w, total in result["warehouse_totals"].items():
        lines.append(f"| {w} | {total} |")
    lines.append(f"| **합계** | **{result['grand_total']}** |")
    lines.append("")

    lines.append("## 품목별 총수량")
    lines.append("")
    lines.append("| 품목 | 총수량 |")
    lines.append("| --- | ---: |")
    for item, qty in result["item_totals"].items():
        lines.append(f"| {item} | {qty} |")
    lines.append("")

    lines.append("## 저재고 목록")
    lines.append("")
    lines.append(f"기준: `{result['low_stock_basis']}`, 임계값(threshold) = {result['threshold']}")
    lines.append("")
    if result["low_stock"]:
        lines.append("| 품목 | 수량 | 창고 |")
        lines.append("| --- | ---: | --- |")
        for row in result["low_stock"]:
            lines.append(f"| {row['item']} | {row['quantity']} | {row['warehouse']} |")
    else:
        lines.append("저재고 항목 없음.")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge warehouse intermediates into result.json")
    here = Path(__file__).resolve().parent
    parser.add_argument("--intermediate", default=str(here / "intermediate"),
                        help="directory holding warehouse-*.json intermediates")
    parser.add_argument("--out", default=str(here / "result.json"),
                        help="output result.json path")
    parser.add_argument("--report", default=str(here / "report.md"),
                        help="output report.md path")
    args = parser.parse_args(argv)

    intermediate_dir = Path(args.intermediate)
    result = build_result(intermediate_dir)

    out_path = Path(args.out)
    try:
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        print(f"cannot write {out_path}: {exc}", file=sys.stderr)
        return 2

    report_path = Path(args.report)
    try:
        with report_path.open("w", encoding="utf-8") as fh:
            fh.write(build_report(result))
            fh.write("\n")
    except OSError as exc:
        print(f"cannot write {report_path}: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {out_path}")
    print(f"wrote {report_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
