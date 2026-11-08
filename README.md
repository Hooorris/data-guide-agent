# data-guide-agent

引导式数据分析 Agent(通用 Skill,跨 AI harness 可用)。
通过对话识别意图、菜单式引导用户补全输入、执行参数化模板查询、教练式追问推进分析;
彩蛋路径可一键生成机构经营简报(演示版)。

## 快速开始

```bash
# 0. 配好本机差异:新建 config.local.yaml 填口令/地址(见「配置分层」,该文件不入库)
#    也可以直接 export DGA_DB_HOST=... DGA_DB_PASSWORD=...

# 1. 装依赖(二选一,按你的环境)
pip install "psycopg[binary]" pyyaml

# 2. 体检(依赖/数据库/知识库/产物目录)
python3 scripts/doctor.py

# 3. 试一条查询
python3 scripts/query.py --intent menu                     # 先看指标库有哪些指标
python3 scripts/query.py --intent single --metric ape --period 2026YTD

# 4. 多轮追问:带同一个 --session,累积进同一份分析档案
python3 scripts/query.py --intent compare --metric std_premium --period 2026YTD \
  --dim channel --format html --session channel-2026ytd --section-title "各渠道规模(起手)"
```

在任意支持 Agent Skills 的 harness(WorkBuddy / Claude Code 等)中加载本目录即可使用;
引导编排逻辑全部在 `SKILL.md`。

## 目录结构

```
data-guide-agent/
├── SKILL.md              # 引导编排指令(意图/槽位/三层引导链/口径红线/兜底)
├── config.yaml           # 连接/产物/演示开关(结构入库,口令留空)
├── config.local.yaml     # 本机私有覆盖:口令、内网地址(不入 git)
├── knowledge/
│   ├── metric_cards.yaml # 指标卡片:定义/口径/别名/SQL 规则/可下钻维度/追问话术
│   └── theme_packs.yaml  # 6 大主题包 → 指标集(引导链最上游)
├── scripts/
│   ├── db_adapter.py     # 数据源适配层(默认 postgres,可注册其他库)
│   ├── query.py          # 参数化模板查询 CLI(menu + 7 意图,--format html 出表图一体产物)
│   ├── session_report.py # 分析档案:同一会话多轮追加进同一份 HTML(目录导航 + 节间衔接)
│   ├── chart.py          # 表图一体渲染(单页 HTML / 多节累积文档,内嵌 Chart.js 离线可用)
│   ├── report_teaser.py  # 彩蛋简报(一页 HTML,标注演示版)
│   └── doctor.py         # 一键体检
├── assets/
│   └── chart.umd.min.js  # 本地 Chart.js(离线)
└── README.md
```

## 配置(config.yaml)

| 键 | 说明 |
|---|---|
| `datasource.type` | 数据源适配器名(默认 `postgres`,可扩展) |
| `datasource.host/port/name/user/password` | 数据库连接;可用环境变量 `DGA_DB_*` 覆盖 |
| `datasource.table` | 业务事实表名 |
| `output.dir` | 产物目录(默认 `./output`,相对当前工作目录) |
| `demo.proactive_menu` | 演示模式:true = 开场主动亮主题菜单 |
| `time.anchor` | 时间锚点,`auto` = 取 MAX(trans_date) |

环境变量覆盖(便于不改文件切换环境):
`DGA_DB_TYPE / DGA_DB_HOST / DGA_DB_PORT / DGA_DB_NAME / DGA_DB_USER / DGA_DB_PASSWORD / DGA_TABLE / DGA_OUTPUT_DIR / DGA_PROACTIVE_MENU`

### 配置分层(口令不入库)

优先级:**环境变量 `DGA_DB_*` > `config.local.yaml` > `config.yaml`**

- `config.yaml` 入库,只放结构与默认值,`datasource.password` 留空
- `config.local.yaml` 不入库(`.gitignore` 已排除),只写本机差异:口令、内网 host、个人路径
- 换台机器/换个人:`cp` 一份仓库 → 建 `config.local.yaml` 填本机差异 → 跑 `doctor.py`

```yaml
# config.local.yaml 示例
datasource:
  host: "10.0.0.12"
  password: "***"
```

## 接入其他数据库

1. 在 `scripts/db_adapter.py` 继承 `DataSourceAdapter`,实现 `connect()/execute()/anchor_date()/row_count()`
2. 在 `REGISTRY` 注册,如 `REGISTRY["duckdb"] = DuckdbAdapter`
3. `config.yaml` 的 `datasource.type` 改为 `duckdb`
4. `python3 scripts/doctor.py` 验证

注意:查询模板针对 `policy_detail` 的列结构(考核年制、if_/sm_ 双口径);
换业务库时需同步调整 `knowledge/metric_cards.yaml` 的列映射。

## 维护约定

- **新增指标**:在 `metric_cards.yaml` 追加卡片(query.py 自动可查),主题包按需引用;doctor 会校验交叉引用
- **新增主题包**:在 `theme_packs.yaml` 追加,指标 id 必须在 metric_cards 中存在
- **口径变更**:先改 metric_cards(单一事实源),SQL 模板从卡片生成,不要直接改 query.py 里的表达式
- **产物约定**:一次分析的每一轮追问都写进同一份「分析档案」(`--session`),不要每轮新开文件;
  每节用 `--bridge` 说明与上一节的衔接,回复里用「轮次/问法/结论/相对上一轮」四列演进表串起来
