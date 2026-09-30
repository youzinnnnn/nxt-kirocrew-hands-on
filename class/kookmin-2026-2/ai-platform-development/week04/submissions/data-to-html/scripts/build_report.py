#!/usr/bin/env python3
"""data-to-html: documents 문서별 요약 + data CSV 핵심 표 -> 하나의 HTML 보고서.

표준 라이브러리만 사용. 원본 파일은 읽기만 한다.
종료 코드: 0 성공 / 1 입력 오류 / 2 처리 오류
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    """utf-8-sig로 CSV를 읽어 (헤더, 행 리스트)를 돌려준다."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [dict(r) for r in reader]
    return headers, rows


def to_int(v) -> int:
    try:
        return int(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return 0


def won(n: int) -> str:
    return f"{n:,}원"


# ---------------------------------------------------------------------------
# 문서 요약
# ---------------------------------------------------------------------------

# 문서 ID/날짜/행사 ID 같은 식별 메타 (한 줄에 여러 개일 수 있음)
META_RE = re.compile(r"(문서\s*ID|시행일|게시일|기준일|행사\s*ID)\s*[:：]", re.I)
# 본문 중 '키: 값' 형태의 핵심 사실 (일시·장소·정원·한도·금액·마감 등)
FACT_KEY_RE = re.compile(
    r"^\s*([가-힣A-Za-z][가-힣A-Za-z0-9 /()·]{0,18}?)\s*[:：]\s*(\S.*)$"
)
FACT_KEYWORDS = (
    "행사", "일시", "일자", "날짜", "시간", "장소", "정원", "인원", "모집",
    "한도", "금액", "단가", "예산", "지원", "마감", "기한", "기준", "대상",
    "수량", "재원", "연락", "담당", "비용", "요금",
)
# 숫자·금액·정원 등을 강조하기 위한 패턴
NUM_RE = re.compile(
    r"(\d[\d,]*\s*(?:원|명|건|개|인|시|분|%|쪽)"          # 4,000원 / 180명 / 14시
    r"|\d{4}-\d{2}-\d{2}(?:\s*\d{2}:\d{2})?"              # 2026-09-28 14:00
    r"|\d{1,2}:\d{2}"                                      # 14:00
    r"|\d[\d,]*)"                                          # 그 밖의 숫자
)


def highlight_nums(s: str) -> str:
    """이미 이스케이프된 문자열에서 숫자·금액을 <mark>로 강조."""
    return NUM_RE.sub(lambda m: f"<mark>{m.group(0)}</mark>", s)


def _first_sentence(body: str, max_chars: int = 90) -> str:
    """문단에서 요지 한 문장만 뽑는다. 첫 종결부호까지, 없으면 max_chars까지."""
    body = body.strip()
    if not body:
        return ""
    # 한국어/영문 종결부호 기준 첫 문장
    m = re.search(r"^(.*?[.。!?！？])(\s|$)", body)
    sent = m.group(1).strip() if m else body
    if len(sent) > max_chars:
        sent = sent[:max_chars].rstrip() + "…"
    return sent


def summarize_document(path: Path, detail: str = "brief",
                       max_clauses: int = 6, max_facts: int = 6) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines()]

    title = path.stem
    meta_line = ""
    facts: list[tuple[str, str]] = []       # (키, 값) 핵심 사실
    clauses: list[tuple[str, str]] = []     # (조 제목, 본문)

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(">"):  # 인용/면책 문구는 건너뜀
            continue
        if s.startswith("# ") and title == path.stem:
            title = s[2:].strip()
            continue
        if META_RE.search(s) and not meta_line:
            meta_line = re.sub(r"^#+\s*", "", s)
            continue
        m = re.match(r"^(#{2,6})\s+(.*)$", s)
        if m:
            clauses.append([m.group(2).strip(), ""])
            continue
        # 목록 기호 정리
        body = re.sub(r"^[-*+]\s+", "", s)
        # '키: 값' 형태의 핵심 사실이면 별도 수집
        fm = FACT_KEY_RE.match(body)
        if fm and any(k in fm.group(1) for k in FACT_KEYWORDS):
            facts.append((fm.group(1).strip(), fm.group(2).strip()))
            continue
        # 본문: 현재 조에 전체 문장을 이어 붙인다 (요약은 렌더 단계에서)
        if clauses and not clauses[-1][1].endswith(body):
            clauses[-1][1] = (clauses[-1][1] + " " + body).strip() if clauses[-1][1] else body
        elif not clauses:
            clauses.append(["", body])

    clause_pairs = [(h, b) for h, b in clauses if h or b]

    # 요약 모드: 본문을 요지 한 문장으로 줄이고, 조항 수를 제한한다.
    extra = 0
    if detail == "brief":
        summarized = []
        for h, b in clause_pairs:
            summarized.append((h, _first_sentence(b)))
        if len(summarized) > max_clauses:
            extra = len(summarized) - max_clauses
            summarized = summarized[:max_clauses]
        clause_pairs = summarized
    fact_extra = 0
    if len(facts) > max_facts:
        fact_extra = len(facts) - max_facts
        facts = facts[:max_facts]

    return {
        "file": path.name,
        "title": title,
        "meta": meta_line,
        "facts": facts,
        "fact_extra": fact_extra,
        "clauses": clause_pairs,
        "clause_extra": extra,
    }


def collect_inputs(paths: list[str]) -> tuple[list[Path], list[Path]]:
    """입력 경로(폴더/파일)들을 확장자로 나눠 (md/txt 목록, csv 목록)로 돌려준다."""
    docs: list[Path] = []
    csvs: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    ext = f.suffix.lower()
                    if ext in (".md", ".txt"):
                        docs.append(f)
                    elif ext == ".csv":
                        csvs.append(f)
        elif p.is_file():
            ext = p.suffix.lower()
            if ext in (".md", ".txt"):
                docs.append(p)
            elif ext == ".csv":
                csvs.append(p)
    return docs, csvs


def render_documents(files: list[Path], detail: str = "brief") -> str:
    if not files:
        return ""
    cards = []
    for p in files:
        d = summarize_document(p, detail=detail)
        facts = ""
        if d["facts"]:
            chips = "".join(
                f'<div class="fact"><span class="fact-k">{esc(k)}</span>'
                f'<span class="fact-v">{highlight_nums(esc(v))}</span></div>'
                for k, v in d["facts"]
            )
            if d.get("fact_extra"):
                chips += (f'<div class="fact"><span class="fact-k">…</span>'
                          f'<span class="fact-v">외 {d["fact_extra"]}개</span></div>')
            facts = f'<div class="facts">{chips}</div>'
        items = "".join(
            f"<li><b>{esc(h)}</b>{': ' if h and b else ''}{highlight_nums(esc(b))}</li>"
            for h, b in d["clauses"]
        )
        if d.get("clause_extra"):
            items += f'<li class="more">…외 {d["clause_extra"]}개 조항 (원문 참조)</li>'
        meta = f'<div class="meta">{esc(d["meta"])}</div>' if d["meta"] else ""
        cards.append(
            f'<div class="card">'
            f'<h3>{esc(d["title"])}</h3>'
            f'<div class="fname">{esc(d["file"])}</div>'
            f"{meta}"
            f"{facts}"
            f"<ul>{items}</ul>"
            f"</div>"
        )
    label = "핵심 요지" if detail == "brief" else "조항 본문"
    return (
        f'<p class="note">문서 {len(files)}개. 각 문서의 제목·메타·핵심 사실과 {label}만 간추렸습니다. '
        f"숫자·금액·정원은 강조 표시했습니다.</p>"
        f'<div class="grid">{"".join(cards)}</div>'
    )


# ---------------------------------------------------------------------------
# CSV 스키마 판별 + 집계
# ---------------------------------------------------------------------------

def table(headers: list[str], rows: list[list]) -> str:
    thead = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>"


def stat_cards(items: list[tuple[str, str]]) -> str:
    """CSV 핵심 수치를 시각적으로 강조하는 KPI 카드 묶음. items=[(라벨, 값)]."""
    cells = "".join(
        f'<div class="stat"><div class="stat-v">{esc(v)}</div>'
        f'<div class="stat-k">{esc(k)}</div></div>'
        for k, v in items
    )
    return f'<div class="stats">{cells}</div>'


def agg_signup(headers, rows) -> str:
    total = len(rows)
    # 신청상태별 인원
    status: dict[str, int] = {}
    for r in rows:
        k = (r.get("신청상태") or "").strip() or "(빈칸)"
        status[k] = status.get(k, 0) + 1
    status_rows = [[k, v] for k, v in sorted(status.items(), key=lambda x: -x[1])]

    # 옵션 컬럼: 헤더에서 신청상태/식별자 외의 값 컬럼
    known = {"신청_ID", "행사_ID", "이름", "신청상태", "신청일"}
    option_cols = [h for h in headers if h not in known]

    confirmed = [r for r in rows if (r.get("신청상태") or "").strip() == "확정"]
    opt_rows = []
    for col in option_cols:
        counts: dict[str, int] = {}
        for r in confirmed:
            v = (r.get(col) or "").strip() or "(빈칸)"
            counts[v] = counts.get(v, 0) + 1
        cell = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        opt_rows.append([col, cell])

    out = [stat_cards([
        ("총 신청", f"{total}건"),
        ("확정", f"{len(confirmed)}명"),
        ("신청상태 종류", f"{len(status)}가지"),
    ])]
    out.append(f'<p class="note">총 신청 {total}건.</p>')
    out.append("<h4>신청상태별 인원</h4>")
    out.append(table(["신청상태", "인원"], status_rows))
    out.append(f'<h4>확정 {len(confirmed)}명 기준 옵션별 신청</h4>')
    out.append(table(["옵션", "값별 인원"], opt_rows))
    return "".join(out)


IN_TYPES = {"수입", "환불입금"}
OUT_TYPES = {"지출", "환불지급"}


def agg_accounting(headers, rows) -> str:
    # 행사 × 재원 순액(수입계열 +, 지출계열 -)
    by_event_fund: dict[tuple[str, str], int] = {}
    by_type: dict[str, list] = {}  # type -> [sum, count]
    for r in rows:
        ev = (r.get("행사_ID") or "").strip()
        fund = (r.get("재원") or "").strip()
        typ = (r.get("유형") or "").strip()
        amt = to_int(r.get("금액"))
        signed = amt if typ in IN_TYPES else (-amt if typ in OUT_TYPES else 0)
        by_event_fund[(ev, fund)] = by_event_fund.get((ev, fund), 0) + signed
        s = by_type.setdefault(typ, [0, 0])
        s[0] += amt
        s[1] += 1

    ef_rows = [
        [ev, fund, won(v)]
        for (ev, fund), v in sorted(by_event_fund.items())
    ]
    type_rows = [
        [t, won(s[0]), s[1]] for t, s in sorted(by_type.items(), key=lambda x: -x[1][0])
    ]

    income_total = sum(s[0] for t, s in by_type.items() if t in IN_TYPES)
    expense_total = sum(s[0] for t, s in by_type.items() if t in OUT_TYPES)
    net_total = income_total - expense_total

    out = [stat_cards([
        ("거래", f"{len(rows)}건"),
        ("수입 계열", won(income_total)),
        ("지출 계열", won(expense_total)),
        ("전체 순액", won(net_total)),
    ])]
    out.append(f'<p class="note">거래 {len(rows)}건. 부호: 수입·환불입금 +, 지출·환불지급 −.</p>')
    out.append("<h4>유형별 합계(부호 없는 원금액)</h4>")
    out.append(table(["유형", "금액 합", "건수"], type_rows))
    out.append("<h4>행사 × 재원 순액</h4>")
    out.append(table(["행사_ID", "재원", "순액"], ef_rows))
    return "".join(out)


def agg_purchase(headers, rows) -> str:
    out_rows = []
    fixed_total = 0
    for r in rows:
        item = (r.get("물품") or "").strip()
        basis = (r.get("수량기준") or "").strip()
        coef = to_int(r.get("계수"))
        price = to_int(r.get("단가"))
        fund = (r.get("예정재원") or "").strip()
        if basis == "고정":
            qty = coef
            cost = won(qty * price)
            fixed_total += qty * price
        else:  # 참가자 등: 확정인원 미지정이면 곱 비움
            qty = f"{coef}×확정인원"
            cost = "(확정인원 필요)"
        out_rows.append([item, basis, str(coef), won(price), fund, str(qty), cost])
    out = [stat_cards([
        ("구매 예정 항목", f"{len(rows)}개"),
        ("'고정' 소계", won(fixed_total)),
    ])]
    out.append(
        f'<p class="note">구매 예정 {len(rows)}개 항목. 이미 처리된 회계와 합산하지 않음. '
        f"수량기준 '고정' 소계 {won(fixed_total)}.</p>"
    )
    out.append(
        table(["물품", "수량기준", "계수", "단가", "예정재원", "수량", "예정비용"], out_rows)
    )
    return "".join(out)


def generic_preview(headers, rows, n=10) -> str:
    prev = [[r.get(h, "") for h in headers] for r in rows[:n]]
    return (
        f'<p class="note">총 {len(rows)}행. 알려진 스키마가 아니어서 상위 {min(n, len(rows))}행 미리보기.</p>'
        + table(headers, prev)
    )


def classify_and_aggregate(path: Path) -> tuple[str, str]:
    headers, rows = read_csv(path)
    hset = set(headers)
    if {"신청상태"} <= hset and ("인화체험" in hset or "식음료" in hset or "행사_ID" in hset and "이름" in hset):
        return "참가신청", agg_signup(headers, rows)
    if {"재원", "유형", "금액"} <= hset:
        return "회계내역", agg_accounting(headers, rows)
    if {"물품", "수량기준", "계수", "단가"} <= hset:
        return "구매계획", agg_purchase(headers, rows)
    return "일반", generic_preview(headers, rows)


def render_data(files: list[Path]) -> str:
    if not files:
        return ""
    sections = []
    for p in files:
        kind, body = classify_and_aggregate(p)
        sections.append(
            f'<div class="card wide">'
            f"<h3>{esc(p.name)} <span class=\"tag\">{esc(kind)}</span></h3>"
            f"{body}</div>"
        )
    return "".join(sections)


# ---------------------------------------------------------------------------
# HTML 셸
# ---------------------------------------------------------------------------

FONT_LINK = (
    '<link rel="preconnect" href="https://cdn.jsdelivr.net">'
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">'
)

# 디자인 시스템 -----------------------------------------------------------
# - shadcn/ui: HSL 토큰(--background/--card/--border/--muted/--primary),
#   둥근 모서리(--radius), 낮은 대비의 단정한 카드·배지·테이블.
# - Apple 미니멀: 넉넉한 여백, 절제된 타이포, 저채도 뉴트럴 팔레트.
# - Flowbite: 상단 스티키 앱바 + 좌측 위계, 콘텐츠는 중앙 정렬 컨테이너.
# - 간격: Tailwind 8px 스케일(8/16/24/32/48)만 사용.
# - Pretendard 기본 폰트.
# - Magic UI: 은은한 backdrop-blur, 옅은 glow, 스크롤 진입 reveal 만.
CSS = """
:root{
  --background:210 20% 98%; --foreground:222 20% 18%;
  --card:0 0% 100%; --muted:210 16% 96%; --muted-foreground:215 14% 46%;
  --border:214 18% 90%; --primary:222 22% 22%; --primary-foreground:0 0% 100%;
  --accent:212 20% 94%; --radius:12px;
  --shadow:0 1px 2px hsl(222 20% 18% / .04), 0 8px 24px hsl(222 20% 18% / .05);
}
@media (prefers-color-scheme:dark){
  :root{--background:222 22% 9%; --foreground:210 16% 92%; --card:222 20% 12%;
    --muted:222 16% 16%; --muted-foreground:215 14% 62%; --border:222 14% 20%;
    --primary:210 16% 92%; --primary-foreground:222 22% 12%; --accent:222 16% 18%;
    --shadow:0 1px 2px hsl(0 0% 0% / .3), 0 8px 24px hsl(0 0% 0% / .35);}
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  font-family:'Pretendard','Pretendard Variable',-apple-system,BlinkMacSystemFont,
    system-ui,'Segoe UI',sans-serif;
  margin:0; background:hsl(var(--background)); color:hsl(var(--foreground));
  line-height:1.6; -webkit-font-smoothing:antialiased; letter-spacing:-.011em;
}
/* Flowbite식 스티키 앱바 + Magic UI 은은한 blur/glow */
.appbar{
  position:sticky; top:0; z-index:10;
  padding:24px 32px;
  background:hsl(var(--background) / .72); backdrop-filter:saturate(160%) blur(12px);
  border-bottom:1px solid hsl(var(--border));
}
.appbar::after{content:'';position:absolute;left:0;right:0;bottom:-1px;height:1px;
  background:linear-gradient(90deg,transparent,hsl(var(--foreground)/.08),transparent)}
.appbar h1{margin:0;font-size:20px;font-weight:650;letter-spacing:-.02em}
.appbar p{margin:8px 0 0;font-size:13px;color:hsl(var(--muted-foreground))}
main{max-width:1024px;margin:0 auto;padding:32px 16px 48px}
section{margin-bottom:48px}
.section-head{display:flex;align-items:baseline;gap:8px;margin:0 0 24px}
.section-head h2{font-size:15px;font-weight:600;margin:0;letter-spacing:-.01em}
.section-head .count{font-size:12px;color:hsl(var(--muted-foreground));
  background:hsl(var(--muted));padding:0 8px;border-radius:999px;line-height:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(304px,1fr));gap:16px}
/* shadcn Card + Apple 여백 + Magic UI reveal */
.card{
  background:hsl(var(--card)); border:1px solid hsl(var(--border));
  border-radius:var(--radius); padding:24px; box-shadow:var(--shadow);
  animation:reveal .5s cubic-bezier(.16,1,.3,1) both;
}
.card.wide{margin-bottom:16px}
@keyframes reveal{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.card{animation:none}}
.card h3{margin:0 0 8px;font-size:15px;font-weight:600;letter-spacing:-.01em;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.card h4{margin:24px 0 8px;font-size:12px;font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;color:hsl(var(--muted-foreground))}
.card h4:first-of-type{margin-top:16px}
.fname{font-size:12px;color:hsl(var(--muted-foreground));
  font-variant-numeric:tabular-nums;margin-bottom:8px}
.meta{font-size:12px;color:hsl(var(--muted-foreground));background:hsl(var(--muted));
  padding:8px 8px;border-radius:8px;margin-bottom:16px}
.card ul{margin:0;padding-left:16px;font-size:13px}
.card li{margin-bottom:8px}
.card li b{font-weight:600}
.card li.more{color:hsl(var(--muted-foreground));font-size:12px;list-style:none;margin-left:-16px}
/* 핵심 사실 칩 (텍스트 문서의 중요한 키:값) */
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
.fact{display:flex;flex-direction:column;gap:0;background:hsl(var(--muted));
  border:1px solid hsl(var(--border));border-radius:8px;padding:8px 8px;min-width:0}
.fact-k{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
  color:hsl(var(--muted-foreground))}
.fact-v{font-size:13px;font-weight:600;letter-spacing:-.01em;
  font-variant-numeric:tabular-nums}
/* 숫자·금액 강조 */
mark{background:hsl(38 92% 88%);color:hsl(28 74% 26%);padding:0 3px;border-radius:4px;
  font-weight:600;font-variant-numeric:tabular-nums}
@media (prefers-color-scheme:dark){
  mark{background:hsl(38 60% 24%);color:hsl(42 92% 78%)}
}
/* CSV 핵심 KPI 카드 */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:8px;margin:16px 0 24px}
.stat{background:linear-gradient(180deg,hsl(var(--muted)),hsl(var(--card)));
  border:1px solid hsl(var(--border));border-radius:var(--radius);padding:16px;
  box-shadow:var(--shadow)}
.stat-v{font-size:22px;font-weight:700;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums;line-height:1.2}
.stat-k{font-size:11px;font-weight:500;color:hsl(var(--muted-foreground));
  margin-top:8px;text-transform:uppercase;letter-spacing:.04em}
/* shadcn Badge */
.tag{font-size:11px;font-weight:500;background:hsl(var(--accent));
  color:hsl(var(--muted-foreground));padding:0 8px;line-height:20px;border-radius:999px;
  border:1px solid hsl(var(--border))}
/* shadcn Table */
table{border-collapse:separate;border-spacing:0;width:100%;font-size:13px;margin-bottom:8px;
  font-variant-numeric:tabular-nums;border:1px solid hsl(var(--border));border-radius:8px;overflow:hidden}
th,td{padding:8px;text-align:left;border-bottom:1px solid hsl(var(--border))}
tbody tr:last-child td{border-bottom:none}
th{background:hsl(var(--muted));font-weight:600;font-size:12px;
  color:hsl(var(--muted-foreground))}
tbody tr:hover{background:hsl(var(--muted) / .5)}
td:last-child,th:last-child{text-align:right}
.note{font-size:12px;color:hsl(var(--muted-foreground));margin:8px 0 16px}
footer{text-align:center;font-size:12px;color:hsl(var(--muted-foreground));padding:32px 16px}
"""


def build_html(title: str, doc_html: str, data_html: str) -> str:
    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        FONT_LINK,
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>",
        f'<header class="appbar"><h1>{esc(title)}</h1>'
        f"<p>documents 문서 요약 · data CSV 핵심 표</p></header>",
        "<main>",
    ]
    if doc_html:
        parts.append(f'<section><div class="section-head"><h2>문서 요약</h2></div>{doc_html}</section>')
    if data_html:
        parts.append(f'<section><div class="section-head"><h2>데이터 집계</h2></div>{data_html}</section>')
    parts.append("<footer>data-to-html 스킬로 생성 · 수업용 가상 자료</footer>")
    parts.append("</main></body></html>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="여러 md/txt·csv를 읽어 요약 HTML 보고서 생성"
    )
    ap.add_argument(
        "inputs",
        nargs="+",
        help="입력 경로(폴더 또는 파일). 폴더는 하위까지 훑어 .md/.txt는 요약, .csv는 표로 집계.",
    )
    ap.add_argument("--out", required=True, help="출력 HTML 경로")
    ap.add_argument("--title", default="문서·데이터 요약")
    ap.add_argument("--detail", choices=["brief", "full"], default="brief",
                    help="문서 요약 정도: brief(기본, 조항별 요지 한 문장·상위 6개) / full(조항 본문 전체)")
    args = ap.parse_args()

    try:
        docs, csvs = collect_inputs(args.inputs)
    except Exception as e:  # noqa: BLE001
        print(f"입력 오류: {e}", file=sys.stderr)
        return 1

    if not docs and not csvs:
        print("입력 오류: 읽을 .md/.txt/.csv 파일을 찾지 못했습니다.", file=sys.stderr)
        return 1

    try:
        doc_html = render_documents(docs, detail=args.detail)
        data_html = render_data(csvs)
    except Exception as e:  # noqa: BLE001
        print(f"처리 오류: {e}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(args.title, doc_html, data_html), encoding="utf-8")
    print(f"생성: {out} (문서 {len(docs)} · CSV {len(csvs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
