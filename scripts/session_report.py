#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_report.py — 分析档案(累积产物)

动机:一次分析往往要追问三四轮,如果每轮产出一个独立 HTML,用户得挨个打开、
前后结论对不上。本脚本把同一会话的所有轮次写进**同一份 HTML**(带目录导航),
越往下越细,一张页面看完整条分析链。

状态文件:output/.sessions/<session>.json(记录标题 + 各章节数据)
产物:output/<日期>_<session>_分析档案.html(每次追加后整篇重建)

用法:
  # 1) 建档案(可省略,首次 append 会自动建)
  python3 session_report.py --session ch-2026 --title "2026 考核年渠道业绩分析"

  # 2) 追加一节(章节 JSON 从文件或标准输入读,避免命令行转义地狱)
  python3 session_report.py --session ch-2026 --append-section section.json
  echo '{"title":"...","table_columns":["渠道"],"table_rows":[["经代"]]}' \
    | python3 session_report.py --session ch-2026 --append-section -

  # 3) 查看/清空
  python3 session_report.py --session ch-2026 --show
  python3 session_report.py --session ch-2026 --reset

章节 JSON 字段(除 title 外都可选):
  title          小节标题(显示在目录里)
  step           步骤说明(如「第 2 轮 · 2026YTD · 承保口径」)
  headline       一句话结论(结论条)
  bridge         与上一节的衔接说明(如「在上节 -9.3% 的缺口里,储蓄类贡献 -14.6%」)
  labels / series / chart_type    图表数据,series=[{"name":..,"values":[..]}]
  table_columns / table_rows      数据表
  sql            取数 SQL(折叠展示)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chart import render_document, safe_name  # noqa: E402
from db_adapter import load_config  # noqa: E402


def _out_dir() -> Path:
    cfg = load_config()
    d = Path(cfg.get("output", {}).get("dir", "./output"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path(session: str) -> Path:
    d = _out_dir() / ".sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe_name(session)}.json"


def load_state(session: str) -> dict:
    p = _state_path(session)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"session": session, "title": f"{session} 分析档案", "subtitle": "",
            "created": dt.datetime.now().isoformat(timespec="seconds"), "sections": []}


def _json_default(o):
    """psycopg 的 Decimal 等类型 → JSON 可写。"""
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)


def save_state(state: dict) -> Path:
    p = _state_path(state["session"])
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1, default=_json_default),
                 encoding="utf-8")
    return p


def build_html(state: dict) -> Path:
    cfg = load_config()
    prefix = dt.date.today().strftime("%Y-%m-%d") + "_" if cfg.get("output", {}).get("date_prefix", True) else ""
    out = _out_dir() / f"{prefix}{safe_name(state['session'])}_分析档案.html"
    html = render_document(state["title"], state.get("subtitle", ""), state["sections"])
    out.write_text(html, encoding="utf-8")
    return out.resolve()


def append_section(session: str, section: dict, title: str | None = None,
                   subtitle: str | None = None) -> tuple[Path, int]:
    """追加一节并重建整份档案,返回 (产物路径, 本节序号)。"""
    state = load_state(session)
    if title:
        state["title"] = title
    if subtitle is not None:
        state["subtitle"] = subtitle
    if not section.get("title"):
        section["title"] = f"第 {len(state['sections']) + 1} 步"
    section["added_at"] = dt.datetime.now().strftime("%H:%M")
    state["sections"].append(section)
    save_state(state)
    return build_html(state), len(state["sections"])


def _read_json(arg: str) -> dict:
    if arg == "-":
        return json.load(sys.stdin)
    p = Path(arg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(arg)


def main():
    ap = argparse.ArgumentParser(description="data-guide-agent 分析档案(多轮累积产物)")
    ap.add_argument("--session", required=True, help="会话 id,同一分析复用同一个")
    ap.add_argument("--title", help="档案标题")
    ap.add_argument("--subtitle", help="副标题(期间/口径等)")
    ap.add_argument("--append-section", metavar="JSON|FILE|-",
                    help='章节 JSON:文件路径 / 内联 JSON / "-" 读 stdin')
    ap.add_argument("--show", action="store_true", help="打印当前档案结构")
    ap.add_argument("--reset", action="store_true", help="清空该会话的所有章节")
    args = ap.parse_args()

    if args.reset:
        p = _state_path(args.session)
        if p.exists():
            p.unlink()
        print(f"已清空会话 {args.session}")
        return

    if args.append_section:
        sec = _read_json(args.append_section)
        out, n = append_section(args.session, sec, args.title, args.subtitle)
        print(f"已追加第 {n} 节 → {out}")
        return

    state = load_state(args.session)
    if args.title:
        state["title"] = args.title
    if args.subtitle is not None:
        state["subtitle"] = args.subtitle
    if args.title or args.subtitle is not None:
        save_state(state)
        out = build_html(state)
        print(f"档案已更新 → {out}")
        return

    if args.show or not state["sections"]:
        print(json.dumps(state, ensure_ascii=False, indent=1))
        if state["sections"]:
            print(f"\n产物:{build_html(state)}")


if __name__ == "__main__":
    main()
