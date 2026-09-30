"""단일 창고 집계 DAG 노드 (표준 라이브러리만 사용).

창고 문자 하나(A/B/C ...)를 인자로 받아
  1. practice/data/warehouse-<letter>.md 를 warehouse_parse 로 읽고
  2. 창고 합계·품목별 수량·저재고 목록(창고별 행 기준, 수량 < THRESHOLD)을 계산해
  3. submissions/practice/run01/intermediate/warehouse-<letter>.json 으로 저장한다.

각 창고 작업은 서로 의존하지 않는 독립 노드다. 입력 파일은 읽기 전용.

사용법:
    python task_warehouse.py A
    python task_warehouse.py a --threshold 5

종료 코드: 0 성공 / 1 파싱 실패 / 2 입력 오류
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from warehouse_parse import WarehouseParseError, parse_warehouse

THRESHOLD = 5

# run01 = 이 스크립트가 있는 디렉터리; week05 = run01 의 4단계 상위
_RUN01_DIR = Path(__file__).resolve().parent
_WEEK05_DIR = _RUN01_DIR.parents[2]
_DATA_DIR = _WEEK05_DIR / "practice" / "data"
_INTERMEDIATE_DIR = _RUN01_DIR / "intermediate"


def aggregate_warehouse(letter: str, threshold: int = THRESHOLD) -> dict:
    """한 창고를 파싱·집계해 중간 결과 dict 를 반환한다."""
    src = _DATA_DIR / f"warehouse-{letter.lower()}.md"
    if not src.is_file():
        raise FileNotFoundError(f"입력 파일이 없습니다: {src}")

    name, items, total = parse_warehouse(src)

    low_stock = [
        {"item": item, "quantity": qty}
        for item, qty in items.items()
        if qty < threshold
    ]

    return {
        "warehouse": name,
        "source_file": src.name,
        "total": total,
        "items": items,
        "threshold": threshold,
        "low_stock_basis": "warehouse_row",
        "low_stock": low_stock,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="단일 창고 재고 집계 (DAG 노드)")
    ap.add_argument("letter", help="창고 문자, 예: A B C")
    ap.add_argument("--threshold", type=int, default=THRESHOLD,
                    help=f"저재고 상한 (기본 {THRESHOLD}, 미만이면 저재고)")
    args = ap.parse_args(argv)

    try:
        result = aggregate_warehouse(args.letter, args.threshold)
    except FileNotFoundError as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2
    except WarehouseParseError as exc:
        print(f"파싱 실패: {exc}", file=sys.stderr)
        return 1

    _INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _INTERMEDIATE_DIR / f"warehouse-{args.letter.lower()}.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"저장 완료: {out_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
