#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query.py — 参数化模板查询 CLI

用法(SKILL.md 里有面向 Agent 的完整说明):
  python3 query.py --intent single  --metric ape         --period 2026YTD [--branch Branch_01] [--caliber if|sm]
  python3 query.py --intent compare --metric vnb         --period 2026YTD [--dim branch] [--branches Branch_01,Branch_03]
  python3 query.py --intent trend   --metric fyp         --period 2026YTD [--grain month] [--branch ...]
  python3 query.py --intent yoy     --metric std_premium --period 2026YTD [--branch ...]
  python3 query.py --intent share   --metric fyp         --period 2026YTD --dim channel
  python3 query.py --intent topn    --metric ape         --period 2026YTD --dim branch [--n 5]
  python3 query.py --intent koujing --metric nbm          # 口径问答,不查库

period DSL(考核年制:上年 11-01 起;考核季 Q1=上年11月~当年3月,Q2=4~6,Q3=7~9,Q4=10月):
  2026YTD = 2026 考核年累(2025-11-01 ~ 数据锚点)
  2026FY  = 2026 考核年全年(2025-11-01 ~ 2026-10-31)
  2026Q3  = 2026 考核年 Q3(2026-07-01 ~ 2026-09-30)
  2026-09 = 自然月(2026-09-01 ~ 2026-09-30)

输出:默认 markdown 表格 + 元信息;--format json 输出结构化结果;
      --format html 输出**表图一体**单文件产物(数据表与图表同页),查数场景应默认使用。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_adapter import get_adapter, load_config, load_knowledge  # noqa: E402

INTENTS = ["menu", "single", "compare", "trend", "yoy", "share", "topn", "koujing"]
CORE3 = ("个险", "银保", "经代")


# ---------------------------------------------------------------- 指标菜单
def run_menu(kb, packs) -> str:
    """把指标库摊成菜单——指标选择一律来自这里,不靠记忆默认某个指标。"""
    cards = {m["id"]: m for m in kb["metrics"]}
    used, lines = set(), ["### 可用指标(来自指标库 metric_cards.yaml)"]
    for pk in packs.get("packs", []):
        lines.append(f'\n{pk["icon"]} **{pk["name"]}** — {pk["description"]}')
        for mid in pk["metrics"]:
            c = cards.get(mid)
            if not c:
                continue
            used.add(mid)
            alias = "/".join(c.get("aliases", [])[:2]) or "-"
            lines.append(f'- `{mid}` **{c["name"]}** — {alias} · {c["unit"]}')
    rest = [m for m in kb["metrics"] if m["id"] not in used]
    if rest:
        lines.append("\n🔧 **其他指标**")
        for c in rest:
            alias = "/".join(c.get("aliases", [])[:2]) or "-"
            lines.append(f'- `{c["id"]}` **{c["name"]}** — {alias} · {c["unit"]}')
    lines.append("\n**可下钻维度**:" + " / ".join(
        f'`{k}` {v["name"]}' for k, v in kb["dims"].items()))
    return "\n".join(lines)


# ---------------------------------------------------------------- 时间口径
def resolve_period(period: str, anchor: str) -> tuple[str, str, str]:
    """period DSL → (start, end, label)。日期一律 text ISO 直接比字符串。"""
    a = dt.date.fromisoformat(anchor)
    p = period.strip().upper()
    if p.endswith("YTD") or p.endswith("FY"):
        year = int(p[:4])
        start = dt.date(year - 1, 11, 1)
        if p.endswith("FY"):
            end = dt.date(year, 10, 31)
            label = f"{year} 考核年({start}~{end})"
        else:
            end = min(a, dt.date(year, 10, 31))
            label = f"{year} 考核年累({start}~{end})"
        return start.isoformat(), end.isoformat(), label
    if p.endswith(("Q1", "Q2", "Q3", "Q4")):
        year = int(p[:4])
        q = p[-2:]
        spans = {
            "Q1": (dt.date(year - 1, 11, 1), dt.date(year, 3, 31)),
            "Q2": (dt.date(year, 4, 1), dt.date(year, 6, 30)),
            "Q3": (dt.date(year, 7, 1), dt.date(year, 9, 30)),
            "Q4": (dt.date(year, 10, 1), dt.date(year, 10, 31)),
        }
        start, end = spans[q]
        return start.isoformat(), end.isoformat(), f"{year} 考核年{q}({start}~{end})"
    # 自然月 YYYY-MM
    ym = period.strip()
    y, m = int(ym[:4]), int(ym[5:7])
    start = dt.date(y, m, 1)
    end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
    return start.isoformat(), end.isoformat(), f"{ym} 自然月({start}~{end})"


def shift_year(date_iso: str, years: int) -> str:
    d = dt.date.fromisoformat(date_iso)
    try:
        return d.replace(year=d.year + years).isoformat()
    except ValueError:  # 2-29
        return d.replace(year=d.year + years, day=28).isoformat()


# ---------------------------------------------------------------- 指标解析
def metric_expr(card: dict, caliber: str) -> str:
    """指标 → SQL 聚合表达式(金额万元/比率%)。"""
    if card.get("derived"):
        return card[f"formula_{caliber}"]
    col = card[f"column_{caliber}"]
    if card["unit"] == "万元":
        return f"ROUND(SUM({col})/10000, 2)"
    return f"SUM({col})"


def pick_caliber(card: dict, caliber: str | None) -> str:
    if card.get("caliber") == "if_only":
        return "if"
    return "sm" if caliber == "sm" else "if"  # 默认承保


def scope_filter(card: dict, dim: str | None, branch: str | None,
                 channel: str | None, dim_col: str | None = None) -> list[str]:
    """WHERE 片段:NBM/标保率全渠道口径只算核心三渠道;分组时剔除空值分组。"""
    wh = []
    if card.get("channel_scope") == "core3" and not channel and dim != "channel":
        wh.append("channel_name IN ('个险','银保','经代')")
    if branch:
        bs = ",".join(f"'{b.strip()}'" for b in branch.split(","))
        wh.append(f"branch_name IN ({bs})")
    if channel:
        wh.append(f"channel_name = '{channel.strip()}'")
    if dim_col:
        wh.append(f"{dim_col} IS NOT NULL")
    return wh


def period_where(start: str, end: str) -> str:
    return f"trans_date >= '{start}' AND trans_date <= '{end}'"


# ---------------------------------------------------------------- 各意图
def run_single(adapter, card, caliber, start, end, args):
    expr = metric_expr(card, caliber)
    wh = [period_where(start, end)] + scope_filter(card, None, args.branch, args.channel)
    sql = f"SELECT {expr} AS value FROM {adapter.table} WHERE {' AND '.join(wh)}"
    cols, rows = adapter.execute(sql)
    v = rows[0][0]
    return {
        "columns": [f"{card['name']}({card['unit']})"],
        "rows": [[v]],
        "sql": sql,
        "headline": f"**{card['name']}:{v} {card['unit']}**",
    }


def run_compare(adapter, card, caliber, start, end, kb, args):
    dim = args.dim or "branch"
    dcol = kb["dims"][dim]["column"]
    dname = kb["dims"][dim]["name"]
    expr = metric_expr(card, caliber)
    wh = [period_where(start, end)] + scope_filter(card, dim, args.branch, args.channel, dcol)
    if args.branches and dim == "branch":
        bs = ",".join(f"'{b.strip()}'" for b in args.branches.split(","))
        wh.append(f"{dcol} IN ({bs})")
    sql = (f"SELECT {dcol} AS dim, {expr} AS value FROM {adapter.table} "
           f"WHERE {' AND '.join(wh)} GROUP BY {dcol} ORDER BY value DESC")
    cols, rows = adapter.execute(sql)
    return {
        "columns": [dname, f"{card['name']}({card['unit']})"],
        "rows": [list(r) for r in rows],
        "sql": sql,
        "headline": f"按{dname}对比 {card['name']}(共 {len(rows)} 组)",
    }


def run_trend(adapter, card, caliber, start, end, kb, args):
    expr = metric_expr(card, caliber)
    wh = [period_where(start, end)] + scope_filter(card, None, args.branch, args.channel)
    sql = (f"SELECT SUBSTR(trans_date, 1, 7) AS ym, {expr} AS value "
           f"FROM {adapter.table} WHERE {' AND '.join(wh)} "
           f"GROUP BY ym ORDER BY ym")
    cols, rows = adapter.execute(sql)
    return {
        "columns": ["月份", f"{card['name']}({card['unit']})"],
        "rows": [list(r) for r in rows],
        "sql": sql,
        "headline": f"{card['name']} 月度趋势",
    }


def run_yoy(adapter, card, caliber, start, end, args):
    expr = metric_expr(card, caliber)
    base_where = [period_where(start, end)] + scope_filter(card, None, args.branch, args.channel)
    last_where = [period_where(shift_year(start, -1), shift_year(end, -1))] + \
        scope_filter(card, None, args.branch, args.channel)
    sql_cur = f"SELECT {expr} FROM {adapter.table} WHERE {' AND '.join(base_where)}"
    sql_pre = f"SELECT {expr} FROM {adapter.table} WHERE {' AND '.join(last_where)}"
    cur = adapter.execute(sql_cur)[1][0][0]
    prev = adapter.execute(sql_pre)[1][0][0]
    unit = card["unit"]
    if prev in (None, 0):
        delta = "同期无基数"
        rate = None
    else:
        d = cur - prev
        rate = round(d / prev * 100, 1)
        delta = f"{'+' if d >= 0 else ''}{round(d, 2)} {unit}({'+' if rate >= 0 else ''}{rate}%)"
    return {
        "columns": ["期间", f"{card['name']}({unit})"],
        "rows": [["本期", cur], ["上年同期", prev], ["同比", delta]],
        "sql": sql_cur + ";\n" + sql_pre,
        "headline": f"**{card['name']} 同比 {'+' if (rate or 0) >= 0 else ''}{rate}%**(本期 {cur} vs 同期 {prev} {unit})" if rate is not None else f"{card['name']} 同期无基数",
        "yoy_rate": rate,
    }


def run_share(adapter, card, caliber, start, end, kb, args):
    dim = args.dim or "channel"
    dcol = kb["dims"][dim]["column"]
    dname = kb["dims"][dim]["name"]
    expr = metric_expr(card, caliber)
    wh = [period_where(start, end)] + scope_filter(card, dim, args.branch, args.channel, dcol)
    sql = (f"SELECT {dcol} AS dim, {expr} AS value, "
           f"ROUND({expr} / NULLIF(SUM({expr}) OVER (), 0) * 100, 1) AS share "
           f"FROM {adapter.table} WHERE {' AND '.join(wh)} "
           f"GROUP BY {dcol} ORDER BY value DESC")
    cols, rows = adapter.execute(sql)
    return {
        "columns": [dname, f"{card['name']}({card['unit']})", "占比(%)"],
        "rows": [list(r) for r in rows],
        "sql": sql,
        "headline": f"{card['name']} 按{dname}结构占比",
    }


def run_topn(adapter, card, caliber, start, end, kb, args):
    dim = args.dim or "branch"
    dcol = kb["dims"][dim]["column"]
    dname = kb["dims"][dim]["name"]
    n = int(args.n or 5)
    expr = metric_expr(card, caliber)
    wh = [period_where(start, end)] + scope_filter(card, dim, args.branch, args.channel, dcol)
    sql = (f"SELECT {dcol} AS dim, {expr} AS value FROM {adapter.table} "
           f"WHERE {' AND '.join(wh)} GROUP BY {dcol} "
           f"ORDER BY value DESC LIMIT {n}")
    cols, rows = adapter.execute(sql)
    return {
        "columns": [dname, f"{card['name']}({card['unit']})"],
        "rows": [list(r) for r in rows],
        "sql": sql,
        "headline": f"{card['name']} TOP {n}(按{dname})",
    }


def run_koujing(card, caliber):
    lines = [
        f"### {card['name']}({', '.join(card.get('aliases', [])[:2])})",
        f"- **定义**:{card['definition']}",
        f"- **单位**:{card['unit']}",
        f"- **口径**:{'仅承保' if card.get('caliber') == 'if_only' else '受理/承保双口径,默认承保(if_)'}",
    ]
    if card.get("channel_scope") == "core3":
        lines.append("- **全渠道口径**:只算 个险/银保/经代 三个渠道(法人业务/其他不参与),除非明确单渠道")
    if card.get("derived"):
        lines.append("- **计算纪律**:SUM/SUM 现算,禁止对单行比率取平均")
    if card.get("related"):
        lines.append(f"- **关联指标**:{', '.join(card['related'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 输出
def to_markdown(result: dict) -> str:
    cols = result["columns"]
    rows = result["rows"]
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="data-guide-agent 参数化查询")
    ap.add_argument("--intent", required=True, choices=INTENTS)
    ap.add_argument("--metric", help="指标 id(见 knowledge/metric_cards.yaml);--intent menu 时不需要")
    ap.add_argument("--period", help="如 2026YTD / 2026Q3 / 2026-09(koujing 意图不需要)")
    ap.add_argument("--dim", help="维度 id(branch/channel/product_category/single_premium_flag/participating_flag/value_product_flag/payment_frequency)")
    ap.add_argument("--branch", help="分公司过滤,逗号分隔")
    ap.add_argument("--branches", help="compare 时的机构组,逗号分隔")
    ap.add_argument("--channel", help="单渠道过滤")
    ap.add_argument("--caliber", choices=["if", "sm"], help="口径:默认 if(承保)")
    ap.add_argument("--grain", default="month", help="trend 粒度(目前支持 month)")
    ap.add_argument("--n", type=int, default=5, help="topn 的 N")
    ap.add_argument("--format", choices=["md", "json", "html"], default="md",
                    help="html = 表图一体的单文件产物(数据表与图表同页,推荐默认使用)")
    ap.add_argument("--chart", choices=["auto", "line", "bar", "pie", "none"], default="auto",
                    help="html 产物的图表形态;auto 按意图自动选(trend→line / share→pie / 其他→bar)")
    ap.add_argument("--out", help="html 产物输出路径")
    ap.add_argument("--session", help="分析档案 id:同一会话的多轮查询累积进同一份 HTML")
    ap.add_argument("--section-title", help="档案里的本节标题(默认「指标 · 期间」)")
    ap.add_argument("--bridge", help="与上一节的衔接说明,如「在上节缺口里,储蓄类贡献 -14.6%%」")
    ap.add_argument("--no-append", action="store_true",
                    help="配 --session 时只打印结论,不写入档案")
    args = ap.parse_args()

    kb = load_knowledge("metric_cards")
    cards = {m["id"]: m for m in kb["metrics"]}

    if args.intent == "menu":
        print(run_menu(kb, load_knowledge("theme_packs")))
        return

    if not args.metric:
        raise SystemExit("缺少 --metric。先跑 `--intent menu` 看可用指标,让用户选,不要自己默认。")
    if args.metric not in cards:
        known = ", ".join(sorted(cards))
        raise SystemExit(f"未知指标 '{args.metric}'。可用: {known}")
    card = cards[args.metric]

    if args.intent == "koujing":
        print(run_koujing(card, args.caliber))
        return

    if not args.period:
        raise SystemExit("该意图需要 --period(如 2026YTD / 2026Q3 / 2026-09)")
    if args.dim and args.dim not in kb["dims"]:
        known = ", ".join(sorted(kb["dims"]))
        raise SystemExit(f"未知维度 '{args.dim}'。可用: {known}")

    cfg = load_config()
    adapter = get_adapter(cfg)
    anchor = adapter.anchor_date()
    start, end, plabel = resolve_period(args.period, anchor)
    caliber = pick_caliber(card, args.caliber)

    runners = {"single": run_single, "compare": run_compare, "trend": run_trend,
               "yoy": run_yoy, "share": run_share, "topn": run_topn}
    fn = runners[args.intent]
    if args.intent in ("single", "yoy"):
        result = fn(adapter, card, caliber, start, end, args)
    else:
        result = fn(adapter, card, caliber, start, end, kb, args)

    result.update({
        "intent": args.intent,
        "metric": args.metric,
        "metric_name": card["name"],
        "period": args.period,
        "period_label": plabel,
        "caliber": "受理(sm_)" if caliber == "sm" else "承保(if_)",
        "followups": card.get("followups", []),
        "related": card.get("related", []),
    })

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.format == "html":
        # 表图一体:一次调用同时产出「数据表 + 图表」的单文件 HTML
        from chart import auto_chart_spec, render_result_html  # 延迟导入,避免 md 场景多余开销
        if args.session and not args.no_append:
            # 同一分析会话 → 追加进同一份「分析档案」,不新开文件
            from session_report import append_section
            spec = auto_chart_spec(result, args.chart)
            ctype, labels, series = spec if spec else ("none", [], [])
            sec = {
                "title": args.section_title or f"{card['name']} · {args.period}",
                "step": f"{args.intent} · {plabel} · {result['caliber']}",
                "headline": re.sub(r"\*\*", "", result.get("headline") or ""),
                "bridge": args.bridge or "",
                "labels": labels, "series": series, "chart_type": ctype,
                "table_columns": result["columns"], "table_rows": result["rows"],
                "sql": (result.get("sql") or "").strip(),
            }
            out, n = append_section(args.session, sec)
            print(f"> 期间:{plabel}|口径:{result['caliber']}\n")
            if result.get("headline"):
                print(result["headline"] + "\n")
            print(to_markdown(result))
            print(f"\n📄 已追加为分析档案第 {n} 节(同一份文件,含目录与前序结论):{out}")
        else:
            out = render_result_html(result, args.chart, args.out)
            print(f"> 期间:{plabel}|口径:{result['caliber']}\n")
            if result.get("headline"):
                print(result["headline"] + "\n")
            print(to_markdown(result))
            print(f"\n📄 表图一体产物:{out}")
    else:
        print(f"> 期间:{plabel}|口径:{result['caliber']}\n")
        if result.get("headline"):
            print(result["headline"] + "\n")
        print(to_markdown(result))


if __name__ == "__main__":
    main()
