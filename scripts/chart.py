#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chart.py — 表图一体产物生成(自包含 HTML,内嵌 Chart.js,离线可用)

设计原则:**数据表和图表永远在同一个产物里**,不分开生成。
既可由 query.py --format html 自动调用(推荐),也可手工拼装。

手工用法:
  python3 chart.py --type line --title "FYP 月度趋势" \
    --labels "2025-11,2025-12,2026-01" --series "FYP(万元):48059.57,61822.19,103530.76" \
    --table-header "月份,FYP(万元)" --table-rows "2025-11,48059.57|2025-12,61822.19"

  # 不带图、只要表(如 single 单值场景):--type none
  python3 chart.py --type none --title "本月 APE" --table-header "APE(万元)" --table-rows "2325.40"

多系列(对比场景):--series 可传多次。
产物:./output/[日期_]标题.html(目录与日期前缀见 config.yaml output 节)。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_adapter import SKILL_ROOT, load_config  # noqa: E402

PALETTE = ["#2167ae", "#5495cf", "#91bfe3", "#23366f", "#7a86a3", "#4f5f7f"]

BASE_CSS = """
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f4f9fc; color: #23366f; margin: 0; padding: 32px; }
  .frame { max-width: 960px; margin: 0 auto; background: #fff;
           border: 1px solid rgba(35,54,111,0.12); border-radius: 8px; padding: 24px 28px; }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
  .sub { font-size: 12px; color: #7a86a3; margin-bottom: 14px; }
  .headline { font-size: 14px; font-weight: 600; color: #2167ae; background: #eef6fc;
              border-left: 3px solid #2167ae; padding: 8px 12px; margin-bottom: 16px;
              border-radius: 0 4px 4px 0; }
  .kpi { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
  .kpi .card { flex: 1 1 160px; background: #f4f9fc; border: 1px solid rgba(35,54,111,0.10);
               border-radius: 6px; padding: 14px 16px; }
  .kpi .card .lab { font-size: 11px; color: #7a86a3; margin-bottom: 6px; }
  .kpi .card .val { font-size: 22px; font-weight: 700; color: #23366f; }
  .chartbox { position: relative; height: 380px; margin: 4px 0 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 4px; }
  th, td { padding: 7px 10px; border-bottom: 1px solid rgba(35,54,111,0.08); text-align: left; }
  th { background: #f4f9fc; font-weight: 600; color: #23366f; font-size: 12px; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  tbody tr:hover { background: #fafcfe; }
  details { margin-top: 16px; font-size: 11px; color: #7a86a3; }
  details pre { white-space: pre-wrap; background: #f7fafc; padding: 10px;
                border-radius: 4px; border: 1px solid rgba(35,54,111,0.08); }
  .foot { font-size: 11px; color: #7a86a3; margin-top: 14px;
          border-top: 1px solid rgba(35,54,111,0.10); padding-top: 10px; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>__CSS__
</style>
</head>
<body>
<div class="frame">
  <h1>__TITLE__</h1>
  <div class="sub">__SUBTITLE__</div>
  __HEADLINE____KPI____CHART____TABLE____SQL__
  <div class="foot">data-guide-agent · 数据源:脱敏保单明细库(演示数据)</div>
</div>
__CHARTJS_BLOCK____SCRIPT_BLOCK__
</body>
</html>
"""

# ---------------------------------------------------------------- 累积档案(同一会话多轮追加)
DOC_CSS = BASE_CSS + """
  .frame { max-width: 1060px; }
  .toc { background: #f4f9fc; border: 1px solid rgba(35,54,111,0.10); border-radius: 6px;
         padding: 10px 16px; margin-bottom: 8px; font-size: 12px; }
  .toc b { font-size: 12px; color: #23366f; }
  .toc ol { margin: 6px 0 0; padding-left: 20px; color: #7a86a3; }
  .toc li { margin: 3px 0; }
  .toc a { color: #2167ae; text-decoration: none; }
  .toc a:hover { text-decoration: underline; }
  .toc .meta { color: #7a86a3; font-size: 11px; }
  section.sec { border-top: 1px solid rgba(35,54,111,0.10); margin-top: 20px; padding-top: 16px; }
  section.sec h2 { font-size: 15px; font-weight: 600; margin: 0 0 2px; }
  section.sec .step { font-size: 11px; color: #7a86a3; margin-bottom: 10px; }
  .totop { display: block; text-align: right; font-size: 11px; color: #7a86a3;
           text-decoration: none; margin-top: 6px; }
  .bridge { font-size: 12px; color: #4f5f7f; background: #f7fafc;
            border: 1px dashed rgba(35,54,111,0.18); border-radius: 4px;
            padding: 8px 12px; margin: 0 0 14px; }
"""

DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>__CSS__
</style>
</head>
<body>
<div class="frame">
  <h1>__TITLE__</h1>
  <div class="sub">__SUBTITLE__</div>
  __TOC__
  __SECTIONS__
  <div class="foot">data-guide-agent · 数据源:脱敏保单明细库(演示数据) ·
  同一份分析档案按轮次累积,越往下越细,不必逐个文件打开</div>
</div>
__CHARTJS_BLOCK____SCRIPT_BLOCK__
</body>
</html>
"""


# ---------------------------------------------------------------- 解析与配置
def parse_series(items: list[str]) -> list[dict]:
    series = []
    for it in items:
        name, _, nums = it.partition(":")
        values = [float(x) for x in nums.split(",") if x.strip() != ""]
        series.append({"name": name.strip() or "值", "values": values})
    return series


def build_config(chart_type: str, labels: list[str], series: list[dict]) -> dict:
    if chart_type == "pie":
        return {
            "type": "pie",
            "data": {"labels": labels, "datasets": [{
                "data": series[0]["values"],
                "backgroundColor": [PALETTE[i % len(PALETTE)] for i in range(len(labels))],
                "borderColor": "#ffffff", "borderWidth": 2,
            }]},
            "options": {"plugins": {"legend": {"position": "right"}},
                        "responsive": True, "maintainAspectRatio": False},
        }
    datasets = []
    for i, s in enumerate(series):
        color = PALETTE[i % len(PALETTE)]
        ds = {"label": s["name"], "data": s["values"],
              "borderColor": color, "backgroundColor": color,
              "borderWidth": 2, "tension": 0.3}
        if chart_type == "bar":
            ds["backgroundColor"] = color + "cc"
        else:
            ds["fill"] = False
            ds["pointRadius"] = 3
        datasets.append(ds)
    return {
        "type": "line" if chart_type == "line" else "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {"plugins": {"legend": {"display": len(series) > 1}},
                    "scales": {"y": {"beginAtZero": True}},
                    "responsive": True, "maintainAspectRatio": False},
    }


def safe_name(title: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", title).strip("_")
    return name[:60] or "chart"


# ---------------------------------------------------------------- HTML 片段
def _is_num(v) -> bool:
    """数据库 ROUND() 返回 Decimal,JSON 里是 int/float,都要认。"""
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _decimals_for(header: str) -> int:
    """按列名决定小数位:比率 1 位、件数 0 位、金额/其他 2 位(SKILL.md 口径红线)。"""
    h = str(header)
    if "%" in h or "率" in h:
        return 1
    if "件" in h:
        return 0
    return 2


def _fmt_num(v, dec: int = 2) -> str:
    """千分位 + 固定小数位(金额 2 位、比率 1 位)。"""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    return f"{float(v):,.{dec}f}"


def render_table(columns: list[str], rows: list[list]) -> str:
    if not columns:
        return ""
    # 某列是否数值列(按数据判断,决定右对齐)
    numeric = []
    for i in range(len(columns)):
        vals = [r[i] for r in rows if i < len(r)]
        numeric.append(bool(vals) and sum(1 for v in vals if _is_num(v)) >= max(1, len(vals) // 2))
    th = "".join(
        f'<th class="{"num" if numeric[i] else ""}">{c}</th>' for i, c in enumerate(columns))
    body = []
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            cls = ' class="num"' if numeric[i] else ""
            txt = (_fmt_num(v, _decimals_for(columns[i])) if _is_num(v)
                   else ("" if v is None else str(v)))
            tds.append(f"<td{cls}>{txt}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return ('<table><thead><tr>' + th + '</tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def render_kpi(columns: list[str], rows: list[list]) -> str:
    """单值场景(single/yoy)用 KPI 卡兜底,比硬塞图表更清楚。"""
    cards = []
    if len(rows) == 1 and len(columns) == 1:
        v = rows[0][0]
        txt = _fmt_num(v, _decimals_for(columns[0])) if _is_num(v) else str(v)
        cards.append(f'<div class="card"><div class="lab">{columns[0]}</div>'
                     f'<div class="val">{txt}</div></div>')
    return f'<div class="kpi">{"".join(cards)}</div>' if cards else ""


# ---------------------------------------------------------------- 自动图表规格
def auto_chart_spec(result: dict, pref: str = "auto"):
    """按意图把查询结果映射为 (chart_type, labels, series);返回 None 表示不出图。"""
    intent = result.get("intent", "")
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not rows or len(columns) < 2:
        return None
    if pref == "none":
        return None

    metric_col = next((i for i in (1, 2) if i < len(columns) and
                       any(_is_num(r[i]) for r in rows if i < len(r))), None)
    if metric_col is None:
        return None

    if intent == "yoy":
        labels = [str(r[0]) for r in rows[:2]]
        values = [float(r[1]) if _is_num(r[1]) else None for r in rows[:2]]
        if not all(v is not None for v in values):
            return None
        ctype = "bar" if pref in ("auto", "bar") else pref
        return ctype, labels, [{"name": columns[1], "values": values}]

    labels = [str(r[0]) for r in rows]
    values = [float(r[metric_col]) if _is_num(r[metric_col]) else 0 for r in rows]
    default = {"trend": "line", "share": "pie", "compare": "bar", "topn": "bar"}.get(intent, "bar")
    ctype = default if pref == "auto" else pref
    if ctype == "pie" and intent != "share":
        ctype = default
    return ctype, labels, [{"name": columns[metric_col], "values": values}]


def render_html(title: str, subtitle: str = "", series: list[dict] | None = None,
                labels: list[str] | None = None, chart_type: str = "bar",
                table_columns: list[str] | None = None,
                table_rows: list[list] | None = None,
                kpi_columns: list[str] | None = None,
                kpi_rows: list[list] | None = None,
                headline: str = "", sql_text: str = "") -> str:
    """生成单个 HTML:标题 + 结论 + (KPI/图) + 数据表 + 可选 SQL,全部在一个文件里。"""
    series = series or []
    labels = labels or []
    table_columns = table_columns or []
    table_rows = table_rows or []
    kpi_columns = kpi_columns if kpi_columns is not None else table_columns
    kpi_rows = kpi_rows if kpi_rows is not None else table_rows

    headline_html = f'<div class="headline">{headline}</div>' if headline else ""
    kpi_html = render_kpi(kpi_columns, kpi_rows) if (chart_type == "none" or not series) else ""
    chart_html, chartjs_block, script_block = "", "", ""
    if series and labels and chart_type != "none":
        cfg = build_config(chart_type, labels, series)
        chartjs_block = (f"<script>{(SKILL_ROOT / 'assets' / 'chart.umd.min.js').read_text(encoding='utf-8')}"
                         f"</script>")
        chart_html = '<div class="chartbox"><canvas id="c"></canvas></div>'
        script_block = ("<script>\nconst ctx = document.getElementById('c');\n"
                        f"new Chart(ctx, {json.dumps(cfg, ensure_ascii=False)});\n</script>")
    table_html = render_table(table_columns, table_rows)
    sql_html = f"<details><summary>取数 SQL</summary><pre>{sql_text}</pre></details>" if sql_text else ""

    return (TEMPLATE
            .replace("__CSS__", BASE_CSS)
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__HEADLINE__", headline_html)
            .replace("__KPI__", kpi_html)
            .replace("__CHART__", chart_html)
            .replace("__TABLE__", table_html)
            .replace("__SQL__", sql_html)
            .replace("__CHARTJS_BLOCK__", chartjs_block)
            .replace("__SCRIPT_BLOCK__", script_block))


def render_result_html(result: dict, chart_pref: str = "auto", out_path: str | None = None) -> Path:
    """查询结果 → 表图一体 HTML,返回产物路径。query.py --format html 直接调用。"""
    meta = f"{result.get('period_label', '')} · {result.get('caliber', '')}"
    spec = auto_chart_spec(result, chart_pref)
    if spec:
        ctype, labels, series = spec
    else:
        ctype, labels, series = "none", [], []
    headline = re.sub(r"\*\*", "", result.get("headline", "") or "").strip()
    mname = result.get("metric_name", "") or ""
    # 标题不重复:headline 已含指标名就单独用 headline
    if headline and mname and mname in headline:
        title = headline
    elif headline:
        title = f"{mname} · {headline}".strip(" ·")
    else:
        title = mname or "data-guide-agent 查询结果"
    title = title[:70]
    # 结论条与标题重复时不重复展示;single 单值已被 KPI 卡覆盖,不再重复出表
    head_html = "" if headline == title else headline
    t_cols = result.get("columns") or []
    t_rows = result.get("rows") or []
    if result.get("intent") == "single" and len(t_rows) == 1:
        t_cols, t_rows = [], []
    html = render_html(
        title=title,
        subtitle=meta,
        series=series, labels=labels, chart_type=ctype,
        table_columns=t_cols,
        table_rows=t_rows,
        kpi_columns=result.get("columns") or [],
        kpi_rows=result.get("rows") or [],
        headline=head_html,
        sql_text=(result.get("sql") or "").strip(),
    )
    cfg = load_config()
    if out_path:
        out = Path(out_path)
    else:
        out_dir = Path(cfg.get("output", {}).get("dir", "./output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if cfg.get("output", {}).get("date_prefix", True):
            prefix = dt.date.today().strftime("%Y-%m-%d") + "_"
        out = out_dir / f"{prefix}{safe_name(title)}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out.resolve()


# ---------------------------------------------------------------- 累积档案:章节渲染
def render_section(sec: dict, idx: int) -> tuple[str, dict | None]:
    """单个分析章节 → (HTML 片段, Chart.js 配置 or None)。

    sec 键:title / step / headline / bridge / labels / series / chart_type /
            table_columns / table_rows / kpi_columns / kpi_rows / sql
    """
    parts = [f'<section class="sec" id="s{idx}">']
    parts.append(f'<h2>{idx}. {sec.get("title", "")}</h2>')
    if sec.get("step"):
        parts.append(f'<div class="step">{sec["step"]}</div>')
    if sec.get("bridge"):
        parts.append(f'<div class="bridge">↳ {sec["bridge"]}</div>')
    if sec.get("headline"):
        parts.append(f'<div class="headline">{sec["headline"]}</div>')

    series = sec.get("series") or []
    labels = sec.get("labels") or []
    ctype = sec.get("chart_type") or ("bar" if series else "none")
    cfg = None
    if series and labels and ctype != "none":
        cfg = build_config(ctype, labels, series)
        parts.append(f'<div class="chartbox"><canvas id="c{idx}"></canvas></div>')
    elif not series:
        parts.append(render_kpi(sec.get("kpi_columns") or sec.get("table_columns") or [],
                                sec.get("kpi_rows") or sec.get("table_rows") or []))

    parts.append(render_table(sec.get("table_columns") or [], sec.get("table_rows") or []))
    if sec.get("sql"):
        parts.append(f'<details><summary>取数 SQL</summary><pre>{sec["sql"]}</pre></details>')
    parts.append('<a class="totop" href="#top">↑ 回到目录</a></section>')
    return "".join(parts), cfg


def render_document(title: str, subtitle: str, sections: list[dict]) -> str:
    """多轮分析 → 单份累积档案 HTML:目录导航 + 逐节(结论/图/表/SQL)。"""
    frags, configs = [], []
    toc_items = []
    for i, sec in enumerate(sections, 1):
        frag, cfg = render_section(sec, i)
        frags.append(frag)
        if cfg:
            configs.append((i, cfg))
        tip = sec.get("headline") or sec.get("step") or ""
        tip = re.sub(r"<[^>]+>", "", str(tip))[:40]
        toc_items.append(f'<li><a href="#s{i}">{i}. {sec.get("title", "")}</a>'
                         f'<span class="meta"> · {tip}</span></li>')

    toc = ('<div class="toc" id="top"><b>分析目录</b>'
           f'<span class="meta"> · 共 {len(sections)} 节,按轮次累积</span>'
           f'<ol>{"".join(toc_items)}</ol></div>')

    chartjs_block = script_block = ""
    if configs:
        chartjs_block = (f"<script>{(SKILL_ROOT / 'assets' / 'chart.umd.min.js').read_text(encoding='utf-8')}"
                         f"</script>")
        js = []
        for i, cfg in configs:
            js.append(f"new Chart(document.getElementById('c{i}'), "
                      f"{json.dumps(cfg, ensure_ascii=False)});")
        script_block = "<script>\n" + "\n".join(js) + "\n</script>"

    return (DOC_TEMPLATE
            .replace("__CSS__", DOC_CSS)
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__TOC__", toc)
            .replace("__SECTIONS__", "".join(frags))
            .replace("__CHARTJS_BLOCK__", chartjs_block)
            .replace("__SCRIPT_BLOCK__", script_block))


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="data-guide-agent 表图一体产物生成")
    ap.add_argument("--type", default="bar", choices=["line", "bar", "pie", "none"],
                    help="none = 不出图,只出表/KPI")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--headline", default="", help="结论文字,显示在图表上方")
    ap.add_argument("--labels", help="逗号分隔")
    ap.add_argument("--series", action="append", default=[],
                    help='格式 "系列名:v1,v2,...",可传多次')
    ap.add_argument("--table-header", help="表格表头,逗号分隔")
    ap.add_argument("--table-rows", help="表格数据,行内逗号分隔、行间用 | 分隔")
    ap.add_argument("--sql", default="", help="取数 SQL(折叠展示)")
    ap.add_argument("--out", help="输出文件路径(默认 ./output/标题.html)")
    args = ap.parse_args()

    labels = [x.strip() for x in (args.labels or "").split(",") if x.strip()]
    series = parse_series(args.series)
    columns = [x.strip() for x in (args.table_header or "").split(",") if x.strip()]
    rows: list[list] = []
    for line in (args.table_rows or "").split("|"):
        if line.strip():
            cells = [c.strip() for c in line.split(",")]
            parsed = []
            for c in cells:
                try:
                    parsed.append(float(c))
                except ValueError:
                    parsed.append(c)
            rows.append(parsed)

    if not columns and not series:
        raise SystemExit("至少提供 --table-header 或 --series 之一")

    html = render_html(title=args.title, subtitle=args.subtitle,
                       series=series, labels=labels,
                       chart_type=args.type if series else "none",
                       table_columns=columns, table_rows=rows,
                       headline=args.headline, sql_text=args.sql)

    cfg = load_config()
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(cfg.get("output", {}).get("dir", "./output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if cfg.get("output", {}).get("date_prefix", True):
            prefix = dt.date.today().strftime("%Y-%m-%d") + "_"
        out = out_dir / f"{prefix}{safe_name(args.title)}.html"
    out.write_text(html, encoding="utf-8")
    print(str(out.resolve()))


if __name__ == "__main__":
    main()
