"""통합 작업 스크립트: 세 창고 중간 JSON을 합쳐 result.json과 report.md를 쓴다.

DAG의 통합 노드로, 창고 A·B·C 세 집계 작업이 모두 중간 파일을 생성한 뒤에만
실행할 수 있다. intermediate 폴더의 세 중간 JSON
({warehouse, total, items:{품목: 수량}})을 읽어 다음을 계산한다.

- source_files: 사용한 입력 .md 파일 이름 목록(정렬)
- warehouse_totals: 창고 이름 -> 정수 합계
- item_totals: 품목 이름 -> 전체 창고 정수 합계
- grand_total: 창고 합계의 총합
- low_stock: 전체 창고 품목 합계(item_total)가 threshold 미만인 품목

low_stock_basis는 item_total, threshold는 5로 기록한다. 모든 수치는 정수.
표준 라이브러리만 사용하고, 중간 파일은 읽기 전용으로만 접근한다.

사용법:
    python merge.py [--intermediate <중간_폴더>] [--out-json result.json]
                    [--out-report report.md]
"""

import argparse
import json
import os
import sys

THRESHOLD = 5
LOW_STOCK_BASIS = "item_total"

# 창고 이름 -> 입력 .md 파일 이름 (source_files 표기용)
WAREHOUSE_SOURCE = {
    "A": "warehouse-a.md",
    "B": "warehouse-b.md",
    "C": "warehouse-c.md",
}


def load_intermediates(intermediate_dir):
    """intermediate 폴더의 중간 JSON을 읽어 창고 이름별로 중복을 제거한 dict로 반환한다.

    같은 창고가 여러 파일(예: a.json 과 warehouse-a.json)로 존재해도 창고당 한
    번만 집계되도록, warehouse 키를 기준으로 중복을 제거한다. 이렇게 하면 이 통합
    작업을 여러 번 실행하거나 폴더에 중간 파일이 중복돼 있어도 결과가 동일하다
    (idempotent). 같은 창고의 서로 다른 값이 발견되면 오류로 처리한다.
    """
    by_warehouse = {}
    for name in sorted(os.listdir(intermediate_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(intermediate_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        wh = data["warehouse"]
        if wh in by_warehouse and by_warehouse[wh] != data:
            raise ValueError(
                f"창고 {wh}에 대해 서로 다른 중간 결과가 발견되었습니다: {path}"
            )
        by_warehouse[wh] = data
    if not by_warehouse:
        raise ValueError(f"중간 JSON 파일이 없습니다: {intermediate_dir}")
    return by_warehouse


def merge(by_warehouse):
    """창고 이름별 중간 결과(dict)를 통합해 result 구조를 만든다."""
    warehouse_totals = {}
    item_totals = {}
    source_files = set()

    for wh, rec in by_warehouse.items():
        warehouse_totals[wh] = int(rec["total"])
        for item, qty in rec["items"].items():
            item_totals[item] = item_totals.get(item, 0) + int(qty)
        source_files.add(WAREHOUSE_SOURCE.get(wh, f"warehouse-{wh.lower()}.md"))

    grand_total = sum(warehouse_totals.values())

    low_stock = [
        {"item": item, "quantity": int(total)}
        for item, total in sorted(item_totals.items())
        if int(total) < THRESHOLD
    ]

    result = {
        "source_files": sorted(source_files),
        "warehouse_totals": {wh: int(t) for wh, t in sorted(warehouse_totals.items())},
        "item_totals": {item: int(t) for item, t in sorted(item_totals.items())},
        "grand_total": int(grand_total),
        "low_stock_basis": LOW_STOCK_BASIS,
        "threshold": THRESHOLD,
        "low_stock": low_stock,
    }
    return result


def build_report(result):
    """result 구조로 짧은 Markdown 보고서 문자열을 만든다."""
    lines = []
    lines.append("# 창고 재고 점검 보고서 (run02)")
    lines.append("")
    lines.append(f"- 입력 파일: {', '.join(result['source_files'])}")
    lines.append(f"- 전체 수량(grand_total): {result['grand_total']}")
    lines.append(
        f"- 저재고 기준: {result['low_stock_basis']} "
        f"(전체 창고 품목 합계가 {result['threshold']} 미만)"
    )
    lines.append("")

    lines.append("## 창고별 합계")
    lines.append("")
    lines.append("| 창고 | 합계 |")
    lines.append("| --- | ---: |")
    for wh, total in result["warehouse_totals"].items():
        lines.append(f"| {wh} | {total} |")
    lines.append("")

    lines.append("## 품목별 총수량")
    lines.append("")
    lines.append("| 품목 | 전체 합계 |")
    lines.append("| --- | ---: |")
    for item, total in result["item_totals"].items():
        lines.append(f"| {item} | {total} |")
    lines.append("")

    lines.append(f"## 저재고 목록 (item_total < {result['threshold']})")
    lines.append("")
    if result["low_stock"]:
        lines.append("| 품목 | 수량 |")
        lines.append("| --- | ---: |")
        for entry in result["low_stock"]:
            lines.append(f"| {entry['item']} | {entry['quantity']} |")
    else:
        lines.append("저재고 품목 없음.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="세 창고 중간 JSON을 통합해 result.json과 report.md를 쓴다."
    )
    parser.add_argument(
        "--intermediate",
        default=os.path.join(here, "intermediate"),
        help="중간 JSON 폴더 경로 (기본: ./intermediate)",
    )
    parser.add_argument(
        "--out-json",
        default=os.path.join(here, "result.json"),
        help="출력 result.json 경로 (기본: ./result.json)",
    )
    parser.add_argument(
        "--out-report",
        default=os.path.join(here, "report.md"),
        help="출력 report.md 경로 (기본: ./report.md)",
    )
    args = parser.parse_args(argv)

    try:
        records = load_intermediates(args.intermediate)
        result = merge(records)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"통합 실패: {exc}", file=sys.stderr)
        return 2

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with open(args.out_report, "w", encoding="utf-8") as f:
        f.write(build_report(result))

    print(
        f"통합 완료: 창고 {len(result['warehouse_totals'])}개, "
        f"품목 {len(result['item_totals'])}종, 전체 {result['grand_total']}, "
        f"저재고 {len(result['low_stock'])}종 -> "
        f"{args.out_json}, {args.out_report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
