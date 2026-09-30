"""창고 재고 마크다운 파서 (표준 라이브러리만 사용).

practice/data 의 warehouse-*.md 파일 하나를 UTF-8로 읽어
 - 제목 '# 창고 X 재고' 에서 창고 이름(X)을 추출하고
 - '| 품목 | 수량 |' 형식의 품목 행을 파싱한다.

검사기 정규식과 동일한 패턴을 사용한다:
  제목    : ^# 창고 (\\S+) 재고$
  품목 행 : ^\\|\\s*([a-zA-Z0-9_-]+)\\s*\\|\\s*(\\d+)\\s*\\|$

제목 누락/중복, 품목 중복 시 예외를 발생시킨다.
입력 파일은 읽기 전용으로만 다룬다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

# 검사기와 동일한 정규식
_HEADING_RE = re.compile(r"^# 창고 (\S+) 재고$")
_ROW_RE = re.compile(r"^\|\s*([a-zA-Z0-9_-]+)\s*\|\s*(\d+)\s*\|$")


class WarehouseParseError(ValueError):
    """창고 파일 파싱 실패 시 발생하는 예외."""


def parse_warehouse(path: str | Path) -> Tuple[str, Dict[str, int], int]:
    """단일 warehouse-*.md 파일을 파싱한다.

    반환값: (창고 이름, {품목: 수량(int)}, 창고 합계(int))

    예외:
        WarehouseParseError -- 제목 누락/중복 또는 품목 행 중복 시.
    """
    text = Path(path).read_text(encoding="utf-8")

    warehouse_name: str | None = None
    items: Dict[str, int] = {}

    for line in text.splitlines():
        stripped = line.rstrip("\n").rstrip("\r")

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            if warehouse_name is not None:
                raise WarehouseParseError(
                    f"제목이 둘 이상입니다: '{warehouse_name}' 이후 '{heading_match.group(1)}'"
                )
            warehouse_name = heading_match.group(1)
            continue

        row_match = _ROW_RE.match(stripped)
        if row_match:
            item = row_match.group(1)
            quantity = int(row_match.group(2))
            if item in items:
                raise WarehouseParseError(f"중복된 품목 행입니다: '{item}'")
            items[item] = quantity

    if warehouse_name is None:
        raise WarehouseParseError(f"제목 '# 창고 X 재고' 을(를) 찾을 수 없습니다: {path}")

    total = sum(items.values())
    return warehouse_name, items, total


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python warehouse_parse.py <warehouse-*.md>", file=sys.stderr)
        raise SystemExit(2)

    try:
        name, item_map, total_qty = parse_warehouse(sys.argv[1])
    except WarehouseParseError as exc:
        print(f"파싱 실패: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(
        {"warehouse": name, "items": item_map, "total": total_qty},
        ensure_ascii=False,
        indent=2,
    ))
