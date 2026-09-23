# -*- coding: utf-8 -*-
"""
club-budget-check : 동아리 행사 참가·회계·구매계획 집계

원본: week04/submissions/집계.py 를 범용화.
근거 문서(값이 아니라 산식·규칙만 코드에 담음):
  ACCOUNT-01 회계 집계 기준 - 기초잔액/부호/현재잔액/행사 순지출/구매 산식
  RULE-01    학교지원금 지침    - 지원 대상/제외/자금 구분
  CLUB-01    동아리 운영 규칙   - 구매 기본 인원 = 확정 인원
  APPROVAL-FUND-04 지원금 승인서 - 총 한도/1차 지급/미입금 미가산

원칙:
- 파이썬 3.10+ 표준 라이브러리만 사용(csv/json/argparse/pathlib). 외부 패키지·네트워크 없음.
- CSV는 utf-8-sig로 읽어 BOM 대응. 금액은 정수 원 단위.
- 원본 CSV는 읽기 전용. 출력은 --out JSON에만 쓴다.
- 기초잔액·정원 시나리오·지원금 한도 등 '값'은 하드코딩하지 않고 인자로 받는다.
  근거 문서에서 확인한 값만 넘긴다. 안 넘기면 결과에서 '확인 필요'로 남긴다.

종료 코드: 0 성공 / 1 입력 오류 / 2 처리 오류
"""
import argparse
import csv
import json
import sys
from pathlib import Path

# 회계 유형 부호 (ACCOUNT-01 제2조)
PLUS = ("수입", "환불입금")
MINUS = ("지출", "환불지급")
FLOW_KEYS = ("수입", "환불입금", "지출", "환불지급")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_opening(pairs):
    """--opening 학교지원금=0 동아리회비=800000 -> dict[str,int]"""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--opening 형식 오류: '{p}' (재원=금액)")
        k, v = p.split("=", 1)
        out[k.strip()] = int(v)
    return out


def money_flow(rows, fund_field="재원", type_field="유형", amount_field="금액"):
    agg = {}
    other_types = set()
    for r in rows:
        fund = r[fund_field]
        typ = r[type_field]
        amt = int(r[amount_field])
        agg.setdefault(fund, {k: 0 for k in FLOW_KEYS})
        if typ in FLOW_KEYS:
            agg[fund][typ] += amt
        else:
            other_types.add(typ)
    return agg, other_types


def main(argv=None):
    ap = argparse.ArgumentParser(description="동아리 행사 참가·회계·구매계획 집계")
    ap.add_argument("--data", required=True, help="CSV 폴더 (참가신청/회계내역/구매계획 .csv)")
    ap.add_argument("--out", required=True, help="결과 JSON 경로")
    ap.add_argument("--event", required=True, help="행사 ID (예: E04)")
    ap.add_argument("--opening", nargs="*", default=[],
                    help="재원별 기초잔액 (예: 학교지원금=0 동아리회비=800000)")
    ap.add_argument("--headcounts", nargs="*", type=int, default=[],
                    help="구매계획 인원 시나리오 (예: 140 160 180). 확정인원은 자동 포함")
    ap.add_argument("--signup", default="참가신청.csv")
    ap.add_argument("--account", default="회계내역.csv")
    ap.add_argument("--plan", default="구매계획.csv")
    # 지원금 승인서 대조 (선택)
    ap.add_argument("--fund-name", default=None, help="지원금 재원명 (예: 학교지원금)")
    ap.add_argument("--fund-limit", type=int, default=None, help="총 승인 한도")
    ap.add_argument("--fund-first", type=int, default=None, help="1차 지급액")
    ap.add_argument("--fund-first-txn", default=None, help="1차 지급 거래 ID (예: T091)")
    ap.add_argument("--event-name", default=None, help="행사 이름 (보고용)")
    ap.add_argument("--basis-date", default=None, help="집계 기준일 (보고용)")
    args = ap.parse_args(argv)

    data = Path(args.data)
    if not data.is_dir():
        print(f"[입력오류] data 폴더 없음: {data}", file=sys.stderr)
        return 1
    paths = {n: data / getattr(args, k) for n, k in
             (("참가신청", "signup"), ("회계내역", "account"), ("구매계획", "plan"))}
    for name, p in paths.items():
        if not p.is_file():
            print(f"[입력오류] {name} CSV 없음: {p}", file=sys.stderr)
            return 1

    try:
        opening = parse_opening(args.opening)
    except ValueError as e:
        print(f"[입력오류] {e}", file=sys.stderr)
        return 1

    try:
        signup = read_csv(paths["참가신청"])
        account = read_csv(paths["회계내역"])
        plan = read_csv(paths["구매계획"])
    except Exception as e:  # noqa: BLE001
        print(f"[처리오류] CSV 파싱 실패: {e}", file=sys.stderr)
        return 2

    ev = args.event
    read_counts = {paths["참가신청"].name: len(signup),
                   paths["회계내역"].name: len(account),
                   paths["구매계획"].name: len(plan)}
    need_check = []

    try:
        # 1) 참가 상태별 인원 (해당 행사만) — CLUB-01 제1조
        ev_signup = [r for r in signup if r["행사_ID"] == ev]
        status_counts = {}
        for r in ev_signup:
            status_counts[r["신청상태"]] = status_counts.get(r["신청상태"], 0) + 1
        confirmed = [r for r in ev_signup if r["신청상태"] == "확정"]
        n_confirmed = len(confirmed)

        # 2) 확정자 선택 (참가신청의 옵션 컬럼 = 고정 3열 제외 나머지)
        base_cols = {"신청_ID", "행사_ID", "이름", "신청상태", "신청일"}
        option_cols = [c for c in (signup[0].keys() if signup else []) if c not in base_cols]

        def choice_counts(rows, field):
            c = {}
            for r in rows:
                v = (r.get(field) or "").strip() or "(빈칸)"
                c[v] = c.get(v, 0) + 1
            return c

        confirmed_choices = {col: choice_counts(confirmed, col) for col in option_cols}

        # 3) 회계 (ACCOUNT-01 제2·3조)
        all_agg, unexpected = money_flow(account)
        balances = {}
        opening_used = dict(opening)
        for fund, a in all_agg.items():
            base = opening.get(fund)
            if base is None:
                base = 0
                if fund not in opening:
                    need_check.append(f"재원 '{fund}' 기초잔액 미제공 — 0으로 가정(확인 필요)")
                    opening_used[fund] = 0
            balances[fund] = base + a["수입"] + a["환불입금"] - a["지출"] - a["환불지급"]

        # 행사 순지출 = 지출 + 환불지급 - 환불입금 (수입 제외) — ACCOUNT-01 제3조
        ev_rows = [r for r in account if r["행사_ID"] == ev]
        ev_agg, _ = money_flow(ev_rows)
        ev_net_spend = {f: a["지출"] + a["환불지급"] - a["환불입금"] for f, a in ev_agg.items()}

        # 4) 구매계획 (ACCOUNT-01 제5조): 참가자=인원x계수, 고정=계수, 예정비용=단가x수량
        def plan_for(headcount):
            result, items = {}, []
            for p in plan:
                basis, factor = p["수량기준"], int(p["계수"])
                unit, fund = int(p["단가"]), p["예정재원"]
                if basis == "참가자":
                    qty = headcount * factor
                elif basis == "고정":
                    qty = factor
                else:
                    qty = None
                cost = unit * qty if qty is not None else None
                if cost is not None:
                    result[fund] = result.get(fund, 0) + cost
                items.append({"항목_ID": p.get("항목_ID"), "물품": p.get("물품"),
                              "수량기준": basis, "수량": qty, "단가": unit,
                              "예정비용": cost, "예정재원": fund})
            return {"인원": headcount, "재원별_예정비용": result,
                    "총_예정비용": sum(result.values()), "항목": items}

        scenarios = list(dict.fromkeys(args.headcounts))  # 중복 제거, 순서 유지
        purchase_plans = {f"{h}명": plan_for(h) for h in scenarios}
        purchase_plans[f"확정인원({n_confirmed}명)"] = plan_for(n_confirmed)

        # 지원금 승인 대조 (선택)
        fund_block = None
        if args.fund_name or args.fund_limit or args.fund_first_txn:
            txn = None
            if args.fund_first_txn:
                txn = next((r for r in account if r.get("거래_ID") == args.fund_first_txn), None)
                if txn is None:
                    need_check.append(f"1차 지급 거래 {args.fund_first_txn}이 회계 CSV에 없음")
            fund_block = {
                "재원": args.fund_name,
                "총_승인_한도": args.fund_limit,
                "1차_지급액": args.fund_first,
                "1차_지급_거래": args.fund_first_txn,
                "거래_확인": ({"금액": int(txn["금액"]), "유형": txn["유형"], "재원": txn["재원"]}
                             if txn else None),
                "근거": "APPROVAL-FUND / RULE-01 제5조(미입금액 현금 미가산)",
            }
            if args.fund_limit and args.fund_first is not None:
                fund_block["잔여_미지급"] = args.fund_limit - args.fund_first

        if not opening:
            need_check.append("기초잔액(--opening) 미제공 — 현재 잔액은 순증감만 반영, 확인 필요")
        if unexpected:
            need_check.append(f"회계 유형에 예상외 값 존재: {sorted(unexpected)}")

        out = {
            "행사": args.event_name or ev,
            "행사_ID": ev,
            "기준일": args.basis_date,
            "읽은_행수": read_counts,
            "참가_상태별_인원": status_counts,
            "확정_인원": n_confirmed,
            "확정자_선택": confirmed_choices,
            "기초_잔액": opening_used,
            "재원별_현재_잔액": balances,
            "행사_재원별_순지출": ev_net_spend,
            "지원금_승인": fund_block,
            "구매계획": purchase_plans,
            "예상외_유형": sorted(unexpected),
            "근거_문서_조항": {
                "기초잔액/부호/순지출/구매산식": "ACCOUNT-01 제1~5조",
                "확정인원_기준": "CLUB-01 제1조",
                "지원금_한도/제외": "RULE-01 제2·3·5조",
            },
            "확인_필요": need_check,
        }
    except KeyError as e:
        print(f"[처리오류] CSV 컬럼 없음: {e} (헤더 확인 필요)", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"[처리오류] {e}", file=sys.stderr)
        return 2

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("READ ROWS:", read_counts)
    print(f"[{ev}] STATUS:", status_counts, "| CONFIRMED:", n_confirmed)
    print("BALANCES:", balances)
    print("EVENT NET SPEND:", ev_net_spend)
    for k, v in purchase_plans.items():
        print(f"PLAN {k}: 총 {v['총_예정비용']:,}원 | {v['재원별_예정비용']}")
    print("확인 필요:", need_check or "없음")
    print("SAVED:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
