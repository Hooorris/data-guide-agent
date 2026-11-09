#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_report.py — 复杂分析模式的对外交付物:报告型 HTML

与「分析档案」(session_report.py,过程留痕、内部用)不同,本脚本产出
**无引导痕迹的报告**:封面 + 执行摘要 + 按模板骨架排序的章节 + 分析路径页脚。

骨架定义:knowledge/analysis_template.yaml(章节顺序 / 必备节 / 标题匹配关键词)
映射方式:把 session 状态里的章节按标题关键词对号入座到骨架槽位,按骨架顺序渲染。

回退机制(双产物约定的兜底):
  - 必备节(required)缺失,或渲染过程任何异常 → 自动回退档案模式:
    调用 session_report.build_html 产出过程档案,打印告警,退出码 2。

用法:
  python3 final_report.py --session 20261109-个险价值 \
      --title "个险渠道价值专题分析" \
      --summary "个险 VNB 同比 -15.0%,量缩质升" \
      --summary-points "VNB 12,984.91 万(-15.0%)|NBM 37.0%(+4.5pct)|缺口集中于 X" \
      --subtitle "2026 考核年累 · 承保口径"

  # 不传 --summary 也能跑:执行摘要取最后一节的 headline
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402
from chart import BASE_CSS, PALETTE, build_config, render_table, safe_name  # noqa: E402
from db_adapter import SKILL_ROOT, load_config  # noqa: E402
from session_report import build_html as build_archive  # noqa: E402
from session_report import load_state  # noqa: E402


class ReportFallback(Exception):
    """触发回退档案模式的异常。"""


def load_template(path: str | None = None) -> dict:
    p = Path(path) if path else SKILL_ROOT / "knowledge" / "analysis_template.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def map_sections(template: dict, sections: list[dict]) -> tuple[list[dict], list[str]]:
    """按骨架槽位匹配 session 章节,返回 (按骨架顺序排列的章节, 缺失的必备节标题)。"""
    remaining = list(sections)
    ordered, missing = [], []
    for slot in template.get("sections", []):
        hit = None
        for sec in remaining:
            title = str(sec.get("title", ""))
            if any(kw in title for kw in slot.get("match", [])):
                hit = sec
                break
        if hit is not None:
            remaining.remove(hit)
            hit = dict(hit)
            hit["title"] = slot["title"]  # 报告里用骨架标准节名
            ordered.append(hit)
        elif slot.get("required"):
            missing.append(slot["title"])
    # 骨架外的章节(用户临时加的方向)附在结论节之前,不丢内容
    extra = [s for s in remaining if s not in ordered]
    if extra:
        insert_at = max(len(ordered) - 1, 0) if ordered else 0
        ordered[insert_at:insert_at] = extra
    return ordered, missing


REPORT_CSS = BASE_CSS + """
  .cover { text-align: left; border-bottom: 2px solid #23366f; padding-bottom: 16px;
           margin-bottom: 20px; }
  .cover h1 { font-size: 22px; }
  .cover .meta { font-size: 12px; color: #7a86a3; margin-top: 6px; }
  .exec { background: #eef6fc; border: 1px solid rgba(35,54,111,0.14); border-radius: 8px;
          padding: 16px 20px; margin-bottom: 24px; }
  .exec .lead { font-size: 15px; font-weight: 600; color: #2167ae; margin-bottom: 10px; }
  .exec .pts { display: flex; gap: 12px; flex-wrap: wrap; }
  .exec .pts .pt { flex: 1 1 180px; background: #fff; border: 1px solid rgba(35,54,111,0.10);
                   border-radius: 6px; padding: 10px 14px; font-size: 13px; color: #23366f; }
  .sec { margin-bottom: 28px; }
  .sec h2 { font-size: 16px; font-weight: 600; color: #23366f; margin: 0 0 10px;
            border-left: 4px solid #2167ae; padding-left: 10px; }
  .bridge { font-size: 12px; color: #7a86a3; margin: 0 0 8px 14px; }
  .path { font-size: 11px; color: #7a86a3; margin-top: 24px; border-top: 1px solid rgba(35,54,111,0.10);
          padding-top: 12px; }
  .path ol { margin: 6px 0 0 18px; padding: 0; }
"""

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body id="top">
<div class="frame">
  <div class="cover">
    <h1>__TITLE__</h1>
    <div class="meta">__SUBTITLE__ · 生成于 __DATE__</div>
  </div>
  __EXEC__
  __SECTIONS__
  <div class="path"><b>分析路径</b>(过程留痕见同目录分析档案)
    <ol>__PATH_ITEMS__</ol>
    <div style="margin-top:8px">data-guide-agent · 数据源:脱敏保单明细库(演示数据)· 口径:承保(if_)/ 考核年制</div>
  </div>
</div>
__CHARTJS_BLOCK____SCRIPT_BLOCK__
</body>
</html>
"""


def _render_report_section(sec: dict, idx: int) -> tuple[str, dict | None]:
    """报告版章节:无目录链接、无轮次痕迹;保留 headline / 图 / 表 / 折叠 SQL。"""
    parts = [f'<section class="sec" id="s{idx}">']
    parts.append(f'<h2>{idx} · {sec.get("title", "")}</h2>')
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
    parts.append(render_table(sec.get("table_columns") or [], sec.get("table_rows") or []))
    if sec.get("sql"):
        parts.append(f'<details><summary>取数 SQL</summary><pre>{sec["sql"]}</pre></details>')
    parts.append("</section>")
    return "".join(parts), cfg


def build_report(state: dict, template: dict, title: str, subtitle: str,
                 summary: str | None, summary_points: list[str]) -> Path:
    sections = state.get("sections") or []
    if not sections:
        raise ReportFallback("session 没有任何章节")

    ordered, missing = map_sections(template, sections)
    if missing:
        raise ReportFallback(f"必备节缺失:{'、'.join(missing)}")

    # 执行摘要:一句总论 + 至多 N 个关键数(模板 summary.max_points 控制)
    lead = summary or (ordered[-1].get("headline") if ordered else "") or state.get("title", "")
    max_pts = int(template.get("summary", {}).get("max_points", 3))
    pts = summary_points[:max_pts]
    exec_html = ('<div class="exec"><div style="font-size:11px;color:#7a86a3;margin-bottom:6px">执行摘要</div>'
                 '<div class="lead">' + lead + "</div>"
                 + ('<div class="pts">' + "".join(f'<div class="pt">{p}</div>' for p in pts) + "</div>" if pts else "")
                 + "</div>")

    frags, configs = [], []
    for i, sec in enumerate(ordered, 1):
        frag, cfg = _render_report_section(sec, i)
        frags.append(frag)
        if cfg:
            configs.append((i, cfg))

    path_items = "".join(
        f"<li>{sec.get('added_at', '')} · {sec.get('title', '')}"
        f"{(' — ' + re.sub(r'<[^>]+>', '', str(sec.get('headline', '')))[:50]) if sec.get('headline') else ''}</li>"
        for sec in sections)

    chartjs_block = script_block = ""
    if configs:
        chartjs_block = f"<script>{(SKILL_ROOT / 'assets' / 'chart.umd.min.js').read_text(encoding='utf-8')}</script>"
        js = [f"new Chart(document.getElementById('c{i}'), {json.dumps(cfg, ensure_ascii=False)});"
              for i, cfg in configs]
        script_block = "<script>\n" + "\n".join(js) + "\n</script>"

    html = (REPORT_TEMPLATE
            .replace("__CSS__", REPORT_CSS)
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__DATE__", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__EXEC__", exec_html)
            .replace("__SECTIONS__", "".join(frags))
            .replace("__PATH_ITEMS__", path_items)
            .replace("__CHARTJS_BLOCK__", chartjs_block)
            .replace("__SCRIPT_BLOCK__", script_block))

    cfg_out = load_config().get("output", {})
    prefix = dt.date.today().strftime("%Y-%m-%d") + "_" if cfg_out.get("date_prefix", True) else ""
    out_dir = Path(cfg_out.get("dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{prefix}{safe_name(state['session'])}_经营分析报告.html"
    out.write_text(html, encoding="utf-8")
    return out.resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description="data-guide-agent 复杂分析报告(对外交付物)")
    ap.add_argument("--session", required=True, help="过程档案的 session id")
    ap.add_argument("--template", help="骨架 yaml 路径(默认 knowledge/analysis_template.yaml)")
    ap.add_argument("--title", default="", help="报告标题(默认取档案标题)")
    ap.add_argument("--subtitle", default="", help="副标题(期间/口径)")
    ap.add_argument("--summary", help="执行摘要:一句总论(默认取最后一节结论)")
    ap.add_argument("--summary-points", help="执行摘要关键数,'|' 分隔,至多取模板 max_points 个")
    args = ap.parse_args()

    state = load_state(args.session)
    title = args.title or state.get("title") or f"{args.session} 经营分析报告"
    subtitle = args.subtitle or state.get("subtitle", "")
    points = [p.strip() for p in (args.summary_points or "").split("|") if p.strip()]

    try:
        template = load_template(args.template)
        out = build_report(state, template, title, subtitle, args.summary, points)
    except (ReportFallback, Exception) as e:  # noqa: BLE001 — 任何渲染异常都回退
        print(f"⚠️ 报告生成失败,已回退档案模式:{e}")
        archive = build_archive(state)
        print(f"过程档案(交付替代物):{archive}")
        return 2

    print(f"报告已生成:{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
