# 창고 재고 집계 보고서

- 원본 파일: warehouse-a.md, warehouse-b.md, warehouse-c.md
- 저재고 기준(low_stock_basis): `warehouse_row` (창고별 행 수량 < 5)
- 전체 합계(grand_total): **54**

## 창고별 합계

| 창고 | 합계 |
| --- | ---: |
| A | 22 |
| B | 16 |
| C | 16 |
| **합계** | **54** |

## 품목별 총수량

| 품목 | 총수량 |
| --- | ---: |
| mug | 17 |
| bottle | 12 |
| sensor | 11 |
| hub | 13 |
| cable | 1 |

## 저재고 목록

기준: `warehouse_row`, 임계값(threshold) = 5

| 품목 | 수량 | 창고 |
| --- | ---: | --- |
| bottle | 3 | A |
| hub | 2 | B |
| sensor | 4 | C |
| cable | 1 | C |

