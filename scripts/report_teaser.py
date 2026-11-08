#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_teaser.py — 彩蛋简报生成(演示版,图表版)

一轮分析后,把某机构的核心指标整理成一页 HTML 简报:
KPI 大数字卡(含同比) + 渠道 FYP 环形图 + APE/FYP 月度趋势双线图。
用法:
  python3 report_teaser.py --branch Branch_01 --period 2026YTD
  python3 report_teaser.py --branch Branch_01,Branch_03 --period 2026Q3
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import query as Q  # noqa: E402
from db_adapter import SKILL_ROOT, get_adapter, load_config, load_knowledge  # noqa: E402

KPI_METRICS = ["ape", "fyp", "std_premium", "vnb"]
PALETTE = ["#2167ae", "#5495cf", "#91bfe3", "#23366f", "#7a86a3"]


def fetch_all(adapter, cards, branch: str | None, period: str):
    anchor = adapter.anchor_date()
    start, end, plabel = Q.resolve_period(period, anchor)

    # KPI 卡:本期值 + 同比
    kpis = []
    for mid in KPI_METRICS:
        card = cards[mid]
        caliber = Q.pick_caliber(card, None)
        expr = Q.metric_expr(card, caliber)
        wh = [Q.period_where(start, end)] + Q.scope_filter(card, None, branch, None)
        cur = adapter.execute(
            f"SELECT {expr} FROM {adapter.table} WHERE {' AND '.join(wh)}")[1][0][0] or 0
        wh_pre = [Q.period_where(Q.shift_year(start, -1), Q.shift_year(end, -1))] + \
            Q.scope_filter(card, None, branch, None)
        prev = adapter.execute(
            f"SELECT {expr} FROM {adapter.table} WHERE {' AND '.join(wh_pre)}")[1][0][0]
        rate = round((cur - prev) / prev * 100, 1) if prev else None
        kpis.append({"name": card["name"], "unit": card["unit"],
                     "value": float(cur), "yoy": rate})

    # 渠道 FYP 占比
    fyp = cards["fyp"]
    expr = Q.metric_expr(fyp, "if")
    wh = [Q.period_where(start, end)] + Q.scope_filter(fyp, "channel", branch, None)
    ch = adapter.execute(
        f"SELECT channel_name, {expr} FROM {adapter.table} WHERE {' AND '.join(wh)} "
        f"GROUP BY channel_name ORDER BY 2 DESC")
    channels = {"labels": [r[0] for r in ch[1]],
                "values": [float(r[1] or 0) for r in ch[1]]}

    # APE / FYP 月度趋势
    trend = {"labels": [], "ape": [], "fyp": []}
    for mid, key in (("ape", "ape"), ("fyp", "fyp")):
        card = cards[mid]
        expr = Q.metric_expr(card, "if")
        wh = [Q.period_where(start, end)] + Q.scope_filter(card, None, branch, None)
        _, rows = adapter.execute(
            f"SELECT SUBSTR(trans_date,1,7) AS ym, {expr} FROM {adapter.table} "
            f"WHERE {' AND '.join(wh)} GROUP BY ym ORDER BY ym")
        if not trend["labels"]:
            trend["labels"] = [r[0] for r in rows]
        trend[key] = [float(r[1] or 0) for r in rows]

    return plabel, kpis, channels, trend


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f4f9fc; color: #23366f; margin: 0; padding: 32px; }
  .frame { max-width: 960px; margin: 0 auto; }
  .banner { background: #fff8e6; border: 1px solid #e5c97a; color: #8a6d1d;
            border-radius: 6px; padding: 8px 14px; font-size: 12px; margin-bottom: 16px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { font-size: 12px; color: #7a86a3; margin-bottom: 20px; }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .kpi { background: #fff; border: 1px solid rgba(35,54,111,0.12); border-radius: 8px; padding: 14px 16px; }
  .kpi .n { font-size: 12px; color: #7a86a3; }
  .kpi .v { font-size: 24px; font-weight: 700; margin: 6px 0 2px; font-variant-numeric: tabular-nums; }
  .kpi .u { font-size: 12px; font-weight: 400; color: #7a86a3; }
  .kpi .y { font-size: 12px; font-weight: 600; }
  .up { color: #c0392b; } .down { color: #1e8449; }
  .grid { display: grid; grid-template-columns: 5fr 7fr; gap: 12px; }
  .sec { background: #fff; border: 1px solid rgba(35,54,111,0.12); border-radius: 8px;
         padding: 16px 20px 20px; }
  .sec h2 { font-size: 14px; margin: 0 0 12px; }
  .foot { font-size: 11px; color: #7a86a3; margin-top: 14px; }
  @media (max-width: 800px) { .kpis { grid-template-columns: repeat(2,1fr); } .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="frame">
  <div class="banner">⚠️ 演示版简报 · 由 data-guide-agent 一键生成,数据为脱敏演示数据,结论未经人工复核</div>
  <h1>__TITLE__</h1>
  <div class="sub">__PERIOD__ · 承保口径 · 生成于 __DATE__</div>
  <div class="kpis">__KPIS__</div>
  <div class="grid">
    <div class="sec"><h2>渠道结构(FYP,万元)</h2><canvas id="ch"></canvas></div>
    <div class="sec"><h2>月度趋势(万元)</h2><canvas id="tr"></canvas></div>
  </div>
  <div class="foot">data-guide-agent · report_teaser.py · 数据源:脱敏保单明细库</div>
</div>
<script>__CHARTJS__</script>
<script>
const channels = __CHANNELS__;
const trend = __TREND__;
const palette = __PALETTE__;
new Chart(document.getElementById('ch'), {
  type: 'doughnut',
  data: { labels: channels.labels,
    datasets: [{ data: channels.values, backgroundColor: palette,
                 borderColor: '#fff', borderWidth: 2 }] },
  options: { plugins: { legend: { position: 'bottom' } }, cutout: '58%' }
});
new Chart(document.getElementById('tr'), {
  type: 'line',
  data: { labels: trend.labels, datasets: [
    { label: 'APE', data: trend.ape, borderColor: palette[0], backgroundColor: palette[0],
      borderWidth: 2, tension: 0.3, pointRadius: 3 },
    { label: 'FYP', data: trend.fyp, borderColor: palette[2], borderDash: [6,4],
      borderWidth: 2, tension: 0.3, pointRadius: 3 }
  ] },
  options: { plugins: { legend: { position: 'bottom' } },
             scales: { y: { beginAtZero: true } } }
});
</script>
</body>
</html>
"""


def fmt(v: float) -> str:
    return f"{v:,.2f}"


def main():
    ap = argparse.ArgumentParser(description="彩蛋简报(演示版·图表版)")
    ap.add_argument("--branch", help="分公司,逗号分隔;缺省全公司")
    ap.add_argument("--period", default="2026YTD")
    ap.add_argument("--out", help="输出路径")
    args = ap.parse_args()

    cfg = load_config()
    adapter = get_adapter(cfg)
    kb = load_knowledge("metric_cards")
    cards = {m["id"]: m for m in kb["metrics"]}

    scope = args.branch if args.branch else "全公司"
    plabel, kpis, channels, trend = fetch_all(adapter, cards, args.branch, args.period)

    kpi_html = ""
    for k in kpis:
        if k["yoy"] is None:
            yoy = '<span style="color:#7a86a3">同期无基数</span>'
        else:
            cls = "up" if k["yoy"] >= 0 else "down"
            sign = "+" if k["yoy"] >= 0 else ""
            yoy = f'<span class="{cls}">同比 {sign}{k["yoy"]}%</span>'
        kpi_html += (f'<div class="kpi"><div class="n">{k["name"]}</div>'
                     f'<div class="v">{fmt(k["value"])}<span class="u"> {k["unit"]}</span></div>'
                     f'<div class="y">{yoy}</div></div>')

    chartjs = (SKILL_ROOT / "assets" / "chart.umd.min.js").read_text(encoding="utf-8")
    title = f"{scope} 经营简报"
    html = (HTML.replace("__TITLE__", title)
                .replace("__PERIOD__", plabel)
                .replace("__DATE__", dt.date.today().isoformat())
                .replace("__KPIS__", kpi_html)
                .replace("__CHARTJS__", chartjs)
                .replace("__CHANNELS__", json.dumps(channels, ensure_ascii=False))
                .replace("__TREND__", json.dumps(trend, ensure_ascii=False))
                .replace("__PALETTE__", json.dumps(PALETTE)))

    if args.out:
        out = Path(args.out)
    else:
        out_dir = Path(cfg.get("output", {}).get("dir", "./output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = dt.date.today().strftime("%Y-%m-%d") + "_" if cfg.get("output", {}).get("date_prefix", True) else ""
        out = out_dir / f"{prefix}{scope}_经营简报_演示版.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(str(out.resolve()))


if __name__ == "__main__":
    main()
