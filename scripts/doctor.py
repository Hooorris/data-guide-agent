#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py — 一键体检:依赖 / 配置 / 数据库 / 知识库 / 产物目录
换机器、换 harness、演示前,先跑一遍:
  python3 doctor.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_adapter import SKILL_ROOT, get_adapter, load_config, load_knowledge  # noqa: E402

OK, FAIL, WARN = "✅", "❌", "⚠️"
failures = 0


def check(label: str, fn):
    global failures
    try:
        msg = fn() or "ok"
        print(f"{OK} {label}: {msg}")
    except Exception as e:  # noqa: BLE001
        failures += 1
        print(f"{FAIL} {label}: {e}")


def check_deps():
    import psycopg, yaml  # noqa: F401
    return f"psycopg {psycopg.__version__}, pyyaml ok(python {sys.version.split()[0]})"


def check_config():
    cfg = load_config()
    ds = cfg["datasource"]
    return f"type={ds['type']}, host={ds.get('host')}:{ds.get('port')}, table={ds.get('table')}"


def check_db():
    cfg = load_config()
    adapter = get_adapter(cfg)
    n = adapter.row_count()
    expect = cfg["datasource"].get("verify_total_rows")
    anchor = adapter.anchor_date()
    msg = f"连通,{n:,} 行,数据锚点 {anchor}"
    if expect and n != expect:
        raise RuntimeError(f"行数 {n:,} ≠ 基准 {expect:,}(数据可能已变更)")
    return msg


def check_kb():
    mc = load_knowledge("metric_cards")
    tp = load_knowledge("theme_packs")
    metric_ids = {m["id"] for m in mc["metrics"]}
    dim_ids = set(mc["dims"])
    problems = []
    for m in mc["metrics"]:
        for d in m.get("dims", []):
            if d not in dim_ids:
                problems.append(f"指标 {m['id']} 引用未知维度 {d}")
        for r in m.get("related", []):
            if r not in metric_ids:
                problems.append(f"指标 {m['id']} 引用未知关联指标 {r}")
    for p in tp["packs"]:
        for mid in p.get("metrics", []):
            if mid not in metric_ids:
                problems.append(f"主题包 {p['id']} 引用未知指标 {mid}")
        for sd in p.get("special_defs", []):
            if sd not in mc.get("business_defs", {}):
                problems.append(f"主题包 {p['id']} 引用未知业务定义 {sd}")
    if problems:
        raise RuntimeError("; ".join(problems))
    return f"{len(metric_ids)} 个指标 / {len(dim_ids)} 个维度 / {len(tp['packs'])} 个主题包,交叉引用完整"


def check_chartjs():
    p = SKILL_ROOT / "assets" / "chart.umd.min.js"
    if not p.exists() or p.stat().st_size < 100_000:
        raise RuntimeError(f"Chart.js 缺失或过小: {p}")
    return f"{p.stat().st_size // 1024} KB(离线内嵌,无需 CDN)"


def check_output():
    import tempfile
    cfg = load_config()
    out = Path(cfg.get("output", {}).get("dir", "./output"))
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=out):
        pass
    return f"{out.resolve()} 可写"


def main():
    print(f"data-guide-agent doctor · skill 目录: {SKILL_ROOT}\n")
    check("Python 依赖", check_deps)
    check("配置文件", check_config)
    check("数据库", check_db)
    check("知识库", check_kb)
    check("Chart.js 资产", check_chartjs)
    check("产物目录", check_output)
    print()
    if failures:
        print(f"{FAIL} {failures} 项未通过,请先修复再演示。")
        sys.exit(1)
    print(f"{OK} 全部通过,可以开始引导式查数。")


if __name__ == "__main__":
    main()
