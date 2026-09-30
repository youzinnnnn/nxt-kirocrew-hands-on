"""창고 하나를 집계하는 재사용 가능한 작업 스크립트.

warehouse_parse.parse_warehouse로 입력 마크다운을 읽어
{warehouse, total, items:{품목: 수량(int)}} 구조의 중간 JSON 파일을 쓴다.

특정 창고명·경로를 하드코딩하지 않는다. 입력 경로와 출력 경로를 인자로 받아
A·B·C 세 창고 모두에 동일하게 쓰인다. 표준 라이브러리만 사용하고
원본 데이터 파일은 읽기 전용으로만 접근한다.

사용법:
    python task_aggregate.py <입력_창고_md> <출력_중간_json>
"""

import argparse
import json
import sys

from warehouse_parse import parse_warehouse


def aggregate(input_path, output_path):
    """입력 창고 파일을 집계해 중간 JSON을 쓴다.

    Returns:
        dict: 기록한 중간 결과 {warehouse, total, items}
    """
    name, items, total = parse_warehouse(input_path)

    result = {
        "warehouse": name,
        "total": int(total),
        "items": {item: int(qty) for item, qty in items.items()},
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="창고 마크다운 하나를 집계해 중간 JSON 파일로 저장한다."
    )
    parser.add_argument("input", help="입력 창고 마크다운 파일 경로")
    parser.add_argument("output", help="출력 중간 JSON 파일 경로")
    args = parser.parse_args(argv)

    try:
        result = aggregate(args.input, args.output)
    except (OSError, ValueError) as exc:
        print(f"집계 실패: {exc}", file=sys.stderr)
        return 2

    print(
        f"집계 완료: 창고 {result['warehouse']} "
        f"품목 {len(result['items'])}종 합계 {result['total']} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
