# -*- coding: utf-8 -*-
"""
빛담 가을사진전(E04) 집계 스크립트
근거 문서:
  ACCOUNT-01 회계 집계 기준 (기초잔액/부호/현재잔액/E04 순지출/구매계획 산식)
  RULE-01    학교지원금 지침 (지원 대상/제외/자금 구분)
  CLUB-01    동아리 운영 규칙 (확정 인원 기준, 회비)
  APPROVAL-FUND-04 지원금 승인서 (총 한도 1,500,000 / 1차 1,000,000=T091)
  APPROVAL-SPACE-04 장소 승인서 (승인 정원 160)
  CHANGE-SPACE-04  정원 변경 승인서 (160->180, 2026-09-23)
표준 라이브러리만 사용. 원본 CSV는 읽기 전용.
"""
import csv
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent / "집계_E04.json"

# ACCOUNT-01 제1조: 기초 잔액
OPENING = {"학교지원금": 0, "동아리회비": 800000}
EVENT = "E04"  # 행사 범위 (ACCOUNT-01 제3조: E04 구분)


def read_csv(path):
    # BOM 대응: utf-8-sig
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows


def main():
    signup = read_csv(DATA / "참가신청.csv")
    account = read_csv(DATA / "회계내역.csv")
    plan = read_csv(DATA / "구매계획.csv")

    read_counts = {
        "참가신청.csv": len(signup),
        "회계내역.csv": len(account),
        "구매계획.csv": len(plan),
    }

    # ---- 1) 참가 상태별 인원 (E04만) ----
    e04_signup = [r for r in signup if r["행사_ID"] == EVENT]
    status_counts = {}
    for r in e04_signup:
        status_counts[r["신청상태"]] = status_counts.get(r["신청상태"], 0) + 1
    confirmed = [r for r in e04_signup if r["신청상태"] == "확정"]
    n_confirmed = len(confirmed)  # CLUB-01 제1조: 구매 기본 인원 = 확정 인원

    # ---- 2) 확정자의 선택 (인화체험 / 식음료) ----
    def choice_counts(rows, field):
        c = {}
        for r in rows:
            v = (r.get(field) or "").strip() or "(빈칸)"
            c[v] = c.get(v, 0) + 1
        return c

    confirmed_choices = {
        "인화체험": choice_counts(confirmed, "인화체험"),
        "식음료": choice_counts(confirmed, "식음료"),
    }

    # ---- 3) 회계 집계 (ACCOUNT-01 제2조 부호) ----
    # 수입/환불입금 +, 지출/환불지급 -
    PLUS = {"수입", "환불입금"}
    MINUS = {"지출", "환불지급"}

    def money_flow(rows):
        agg = {"학교지원금": {"수입": 0, "환불입금": 0, "지출": 0, "환불지급": 0},
               "동아리회비": {"수입": 0, "환불입금": 0, "지출": 0, "환불지급": 0}}
        other_types = set()
        for r in rows:
            fund = r["재원"]
            typ = r["유형"]
            amt = int(r["금액"])
            if fund not in agg:
                agg[fund] = {"수입": 0, "환불입금": 0, "지출": 0, "환불지급": 0}
            if typ in agg[fund]:
                agg[fund][typ] += amt
            else:
                other_types.add(typ)
        return agg, other_types

    # 전체(동아리 전체 잔액용): ACCOUNT-01 제3조 현재잔액 = 기초 + 수입 + 환불입금 - 지출 - 환불지급
    all_agg, unexpected = money_flow(account)
    balances = {}
    for fund, base in OPENING.items():
        a = all_agg.get(fund, {"수입": 0, "환불입금": 0, "지출": 0, "환불지급": 0})
        balances[fund] = base + a["수입"] + a["환불입금"] - a["지출"] - a["환불지급"]

    # E04 순지출 (ACCOUNT-01 제3조): 지출 + 환불지급 - 환불입금 (수입 제외)
    e04_rows = [r for r in account if r["행사_ID"] == EVENT]
    e04_agg, _ = money_flow(e04_rows)
    e04_net_spend = {}
    for fund, a in e04_agg.items():
        e04_net_spend[fund] = a["지출"] + a["환불지급"] - a["환불입금"]

    # 지원금 승인서 대조 (APPROVAL-FUND-04)
    t091 = next((r for r in account if r["거래_ID"] == "T091"), None)

    # ---- 4) 구매계획 (ACCOUNT-01 제5조) ----
    # 참가자 = 확정인원 x 계수, 고정 = 계수. 예정비용 = 단가 x 수량
    def plan_for(headcount):
        result = {"학교지원금": 0, "동아리회비": 0}
        items = []
        for p in plan:
            basis = p["수량기준"]
            factor = int(p["계수"])
            unit = int(p["단가"])
            fund = p["예정재원"]
            if basis == "참가자":
                qty = headcount * factor
            elif basis == "고정":
                qty = factor
            else:
                qty = None
            cost = unit * qty if qty is not None else None
            if cost is not None:
                result[fund] = result.get(fund, 0) + cost
            items.append({"항목_ID": p["항목_ID"], "물품": p["물품"],
                          "수량기준": basis, "수량": qty, "단가": unit,
                          "예정비용": cost, "예정재원": fund})
        return {"인원": headcount, "재원별_예정비용": result,
                "총_예정비용": sum(v for v in result.values()), "항목": items}

    purchase_plans = {
        "140명": plan_for(140),
        "160명": plan_for(160),
        "180명": plan_for(180),
        f"확정인원({n_confirmed}명)": plan_for(n_confirmed),
    }

    out = {
        "행사": "빛담 가을사진전과 인화 체험 (E04)",
        "기준일": "2026-09-22 (ACCOUNT-01)",
        "읽은_행수": read_counts,
        "참가_상태별_인원_E04": status_counts,
        "확정_인원": n_confirmed,
        "확정자_선택": confirmed_choices,
        "기초_잔액": OPENING,
        "재원별_현재_잔액": balances,
        "E04_재원별_순지출": e04_net_spend,
        "학교지원금_승인": {
            "총_승인_한도": 1500000,
            "1차_지급액": 1000000,
            "1차_지급_거래": "T091",
            "T091_확인": ({"금액": int(t091["금액"]), "유형": t091["유형"],
                          "재원": t091["재원"]} if t091 else "확인 필요: T091 없음"),
            "잔여_미지급": 500000,
            "근거": "APPROVAL-FUND-04, RULE-01 제5조(미입금액 현금 미가산)",
        },
        "구매계획": purchase_plans,
        "정원_근거": {
            "홍보_정원": 180,
            "홍보_문서": "NOTICE-04",
            "장소_승인_정원_원": 160,
            "장소_승인_문서": "APPROVAL-SPACE-04",
            "변경_승인_정원": 180,
            "변경_승인_문서": "CHANGE-SPACE-04 (2026-09-23, 160->180 대체)",
            "현행_유효_정원": 180,
        },
        "예상외_유형": sorted(unexpected),
        "근거_문서_조항": {
            "기초잔액/부호/순지출/구매산식": "ACCOUNT-01 제1~5조",
            "확정인원_기준": "CLUB-01 제1조",
            "지원금_한도/제외": "RULE-01 제2·3·5조, APPROVAL-FUND-04",
            "정원": "APPROVAL-SPACE-04 / CHANGE-SPACE-04",
        },
        "확인_필요": [],
    }

    if unexpected:
        out["확인_필요"].append(f"회계 유형에 예상외 값 존재: {sorted(unexpected)}")
    if t091 is None:
        out["확인_필요"].append("APPROVAL-FUND-04 1차 지급 거래 T091이 회계 CSV에 없음")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("READ ROWS:", read_counts)
    print("STATUS:", status_counts, "| CONFIRMED:", n_confirmed)
    print("BALANCES:", balances)
    print("E04 NET SPEND:", e04_net_spend)
    print("T091:", out["학교지원금_승인"]["T091_확인"])
    for k, v in purchase_plans.items():
        print(f"PLAN {k}: 총 {v['총_예정비용']:,}원 | {v['재원별_예정비용']}")
    print("UNEXPECTED TYPES:", sorted(unexpected))
    print("확인 필요:", out["확인_필요"])
    print("SAVED:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
