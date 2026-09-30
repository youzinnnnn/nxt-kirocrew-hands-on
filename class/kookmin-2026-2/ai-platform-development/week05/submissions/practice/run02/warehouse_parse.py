"""창고 재고 마크다운 파일을 읽어 창고명·품목별 수량·합계를 추출하는 공용 파서.

표준 라이브러리만 사용한다. 원본 데이터 파일은 읽기 전용으로만 접근하며 아무것도 쓰지 않는다.
"""

import re

# 제목: "# 창고 A 재고" 형태에서 창고명(공백 없는 토큰)을 뽑는다.
HEADING_RE = re.compile(r"^# 창고 (\S+) 재고$")
# 표 행: "| item | 12 |" 형태에서 (품목, 정수 수량)을 뽑는다.
# 한글 헤더행("| 품목 | 수량 |")과 구분행("|---|---:|")은 매칭되지 않는다.
ROW_RE = re.compile(r"^\|\s*([a-zA-Z0-9_-]+)\s*\|\s*(\d+)\s*\|$")


def parse_warehouse(path):
    """마크다운 창고 파일 하나를 파싱한다.

    Returns:
        (name, items, total)
        name  : 창고명 (str)
        items : {품목: 수량(int)} 딕셔너리
        total : 품목 수량 합계 (int)

    Raises:
        ValueError: 제목이 없거나 중복이거나, 품목 행이 없거나 중복일 때.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    name = None
    items = {}

    for raw in lines:
        line = raw.rstrip("\n")

        heading_match = HEADING_RE.match(line)
        if heading_match:
            if name is not None:
                raise ValueError(f"제목이 중복되었습니다: {path}")
            name = heading_match.group(1)
            continue

        row_match = ROW_RE.match(line)
        if row_match:
            item = row_match.group(1)
            qty = int(row_match.group(2))
            if item in items:
                raise ValueError(f"품목이 중복되었습니다: {item} ({path})")
            items[item] = qty

    if name is None:
        raise ValueError(f"창고 제목을 찾을 수 없습니다: {path}")
    if not items:
        raise ValueError(f"품목 행을 찾을 수 없습니다: {path}")

    total = sum(items.values())
    return name, items, total
