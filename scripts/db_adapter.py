#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
db_adapter.py — 数据源适配层

所有取数都经过适配器接口,业务脚本不直接关心数据库类型。
切换数据源 = 在 config.yaml 改 datasource.type + 在这里注册同名实现。

新增数据源步骤:
  1. 继承 DataSourceAdapter,实现 connect()/execute()/anchor_date()/quote_rules()
  2. 在 REGISTRY 注册:REGISTRY["sqlite"] = SqliteAdapter
  3. config.yaml 里 datasource.type 改成 "sqlite"
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_ROOT / "config.yaml"
LOCAL_CONFIG_PATH = SKILL_ROOT / "config.local.yaml"


class DataSourceAdapter:
    """数据源适配器接口。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.table = cfg.get("table", "policy_detail")

    def connect(self):
        raise NotImplementedError

    def execute(self, sql: str, params: tuple = ()):  # -> (columns, rows)
        raise NotImplementedError

    def anchor_date(self) -> str:
        """时间锚点:'今天'的日期串 YYYY-MM-DD。auto = 取 MAX(trans_date)。"""
        anchor = (self.cfg.get("anchor") or "auto")
        if anchor != "auto":
            return anchor
        _, rows = self.execute(f"SELECT MAX(trans_date) FROM {self.table}")
        return rows[0][0]

    def row_count(self) -> int:
        _, rows = self.execute(f"SELECT COUNT(*) FROM {self.table}")
        return int(rows[0][0])


class PostgresAdapter(DataSourceAdapter):
    def connect(self):
        import psycopg  # 延迟导入:只用其他数据源时无需安装 psycopg
        return psycopg.connect(
            host=self.cfg["host"],
            port=int(self.cfg.get("port", 5432)),
            dbname=self.cfg["name"],
            user=self.cfg["user"],
            password=self.cfg["password"],
            sslmode=self.cfg.get("sslmode", "prefer"),
            connect_timeout=int(self.cfg.get("connect_timeout", 10)),
        )

    def execute(self, sql: str, params: tuple = ()):
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description]
                return cols, cur.fetchall()
        finally:
            conn.close()


REGISTRY = {
    "postgres": PostgresAdapter,
}


def _apply_env_overrides(cfg: dict) -> dict:
    """环境变量优先,方便 harness 不改文件也能指到别的库。"""
    ds = cfg.setdefault("datasource", {})
    mapping = {
        "DGA_DB_TYPE": ("datasource", "type"),
        "DGA_DB_HOST": ("datasource", "host"),
        "DGA_DB_PORT": ("datasource", "port"),
        "DGA_DB_NAME": ("datasource", "name"),
        "DGA_DB_USER": ("datasource", "user"),
        "DGA_DB_PASSWORD": ("datasource", "password"),
        "DGA_TABLE": ("datasource", "table"),
        "DGA_OUTPUT_DIR": ("output", "dir"),
        "DGA_PROACTIVE_MENU": ("demo", "proactive_menu"),
    }
    for env, (sec, key) in mapping.items():
        if os.environ.get(env) not in (None, ""):
            cfg.setdefault(sec, {})[key] = os.environ[env]
    _ = ds
    return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    """override 递归覆盖 base(用于 config.local.yaml 覆盖 config.yaml)。"""
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"缺少配置文件: {CONFIG_PATH}(见 README 配置说明)")
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    # 本机差异(口令/端口/路径)放 config.local.yaml,不入 git;同名键覆盖 config.yaml。
    if LOCAL_CONFIG_PATH.exists():
        local = yaml.safe_load(LOCAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        cfg = _deep_merge(cfg, local)
    cfg = _apply_env_overrides(cfg)
    # time.anchor 提升到 datasource 层,方便适配器读取
    cfg["datasource"]["anchor"] = cfg.get("time", {}).get("anchor", "auto")
    return cfg


def get_adapter(cfg: dict | None = None) -> DataSourceAdapter:
    cfg = cfg or load_config()
    ds = cfg["datasource"]
    ds_type = ds.get("type", "postgres")
    if ds_type not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise SystemExit(f"未知数据源类型 '{ds_type}'(已注册: {known})。"
                         f"如需接入新库,请在 db_adapter.py 的 REGISTRY 注册实现。")
    return REGISTRY[ds_type](ds)


def load_knowledge(name: str) -> dict:
    """读取 knowledge/ 下的 yaml(metric_cards / theme_packs)。"""
    p = SKILL_ROOT / "knowledge" / f"{name}.yaml"
    if not p.exists():
        raise SystemExit(f"知识库文件缺失: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))
