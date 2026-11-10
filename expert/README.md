# Data Guide Agent（问数向导）

引导式数据分析专家：面向脱敏保单明细库（72 万行），指标菜单引导选定口径，逐层下钻归因，表图一体累积成多轮分析档案。

## 类型

Agent 型（单个 AI 专家）

## 功能

- **引导三层链**：主题包推荐 → 菜单式槽位补全（指标/期间/机构/维度）→ 教练式追问（出数即停，给 2~3 个并列下钻选项）
- **8 类查询意图**：menu / single / compare / trend / yoy / share / topn / koujing，参数化模板 SQL，演示稳定
- **表图一体分析档案**：同一次分析的多轮追问累积进同一份 HTML（左侧粘性目录、点击跳转、滚动高亮），`--session` 串联
- **口径红线内置**：考核年制、承保 if_ 默认、小基数同比不引用、未完整月单列、大单保单级聚合
- **数据底座**：PostgreSQL `policy_detail`（约 72 万行脱敏保单明细，2024-11 ~ 2026-09），指标知识库 9 指标 / 7 维度 / 6 主题包（`skills/data-guide-agent/knowledge/`）

## 使用示例

- 帮我看下截止目前个险渠道的业绩情况
- 本季度标保同比为什么掉了？帮我逐层归因
- 按渠道对比一下 VNB，看看谁的价值含量高

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 依赖与配置

- Python 3 + `psycopg` + `pyyaml`（建议装入专用 venv `~/.venvs/dga`，避免污染系统解释器）
- 数据库连接配置分层：`skills/data-guide-agent/config.yaml` 入库（口令留空），本机差异写 `config.local.yaml` 或用环境变量 `DGA_DB_HOST / DGA_DB_PASSWORD` 覆盖
- ⚠️ 本包内 `config.local.yaml` 含演示库只读口令，**分享前请删除**

## 安装

将专家包目录放到专家目录下：

```
~/.workbuddy/plugins/marketplaces/my-experts/plugins/data-guide-agent/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```

## 打包分享

```bash
python3 scripts/package_expert.py <expert-dir>
```

## 版本管理

源代码（不含 `config.local.yaml`、`output/` 产物）托管在私有仓库：`https://github.com/Hooorris/data-guide-agent`
