# 창고 재고 점검 보고서 (run02)

- 입력 파일: warehouse-a.md, warehouse-b.md, warehouse-c.md
- 전체 수량(grand_total): 54
- 저재고 기준: item_total (전체 창고 품목 합계가 5 미만)

## 창고별 합계

| 창고 | 합계 |
| --- | ---: |
| A | 22 |
| B | 16 |
| C | 16 |

## 품목별 총수량

| 품목 | 전체 합계 |
| --- | ---: |
| bottle | 12 |
| cable | 1 |
| hub | 13 |
| mug | 17 |
| sensor | 11 |

## 저재고 목록 (item_total < 5)

| 품목 | 수량 |
| --- | ---: |
| cable | 1 |

## 수치 일치 확인

result.json과 report.md의 모든 수치가 일치함을 확인했다.
- 창고별 합계: A=22, B=16, C=16 → grand_total 54 (22+16+16=54)
- 품목별 총수량 합계: bottle 12 + cable 1 + hub 13 + mug 17 + sensor 11 = 54 → grand_total과 동일
- 저재고 목록: 두 파일 모두 cable(1) 한 건으로 동일

## run01 → run02 저재고 목록 비교

- **run01** (`low_stock_basis: warehouse_row`, threshold 5): 창고별 행 단위 수량이 5 미만인 항목을 판정하여 **4건** — bottle(A, 3), hub(B, 2), sensor(C, 4), cable(C, 1).
- **run02** (`low_stock_basis: item_total`, threshold 5): 전체 창고의 품목별 총수량으로 판정하여 **1건** — cable(1).

전체 창고를 합산하면 mug=17, bottle=12, sensor=11, hub=13으로 모두 임계값 5 이상이 되어 run01에서 저재고였던 bottle·hub·sensor는 run02에서 제외되고, 전 창고 합계가 1로 유일하게 5 미만인 cable만 저재고로 남는다.

