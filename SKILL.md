---
name: data-guide-agent
description: 引导式数据分析 Agent 的查数与交付实现层。双路径:仅问数(快查,一轮一层)与复杂分析(固定 6 节骨架 + 层间确认 + 报告型 HTML)。通识规则(节奏/口径红线/分流器/边界)以专家层 agents/data-guide-agent.md 为准,本文件只管"怎么查、怎么交付"。触发词:查数、看数据、经营分析、业绩、引导分析、data guide。
---

# data-guide-agent · 引导式数据分析(实现层)

数据底座:脱敏保单明细库(PostgreSQL `policy_detail`,72 万行,2024-11 ~ 2026-09)。
所有取数通过 `scripts/` 下的 CLI 完成,**不要自己手写 SQL 查库**(自由追问兜底除外,见「兜底」节)。

> **⚠️ 分层约定(先读这条)**:性格节奏、口径红线、入口分流器、职责边界等**通识规则在专家层** `agents/data-guide-agent.md`,本文件不再重复;手写 SQL 前必须回读专家层的口径红线。本文件只回答两个问题:**怎么查**(意图/CLI/下钻菜单/兜底 SQL)和**怎么交付**(档案/报告/演进表)。

## 路径 A:仅问数(快查)

分流器判为「仅问数」时的实现流程:复述槽位 → 补槽位 → 查数 → 出数即停。

### 槽位补全(给选项,不开放提问)

意图的必填槽位不齐时按顺序补:指标 → 期间 → 范围 → 维度。

**① 指标槽位(永远最先补)**:用户说「业绩/达成/经营情况」等模糊词时,先亮真实菜单:

```bash
python3 scripts/query.py --intent menu
```

把返回的菜单(按主题包分组、含指标 id/别名/单位)原样给用户挑;同一词对应多指标(如「价值」=VNB 或 NBM)时给 2~3 个选项。用户明确说了别名(「标保」「VNB」「APE」)时,直接从 `knowledge/metric_cards.yaml` 的 aliases 匹配执行,不必再亮菜单。达成率提醒话术:库里有规模指标但没有渠道任务目标数,达成率算不了,用「规模 + 同比 + 时间进度」替代,用户给目标数才能算真达成率。

**② 期间槽位**:

> ① 2026 考核年累(2025-11 起) ② 最近一个完整考核季(Q3:7~9月) ③ 最近自然月(2026-09) ④ 其他

期间 DSL:`2026YTD`(考核年累)/`2026Q3`(考核季)/`2026-09`(自然月)/`2026FY`(考核年全年)。
机构槽位:全公司 / 单家或多家(Branch_01/03/09/10/11/12/16)。
维度槽位(拆解用):branch / channel / product_category / single_premium_flag / participating_flag / value_product_flag / payment_frequency。

### 查数纪律(实现侧)

- **第一遍必须浅**:首轮只做「一个指标 + 一个维度 + 一个期间」的表层查询(通常 1 条 `single`/`compare`/`topn`),摆规模、结构、同比。
- **查询预算**:首轮 ≤ 2 条查询(菜单 + 1 条查数);此后每轮 ≤ 2 条,且必须等用户明确说"接着/继续/拆一下"才开下一轮。
- **指标/维度/话术从知识库取**:以 `knowledge/metric_cards.yaml`、`knowledge/theme_packs.yaml` 为准,不凭记忆编口径。
- **表图一次成型（仅分析模式）**:进入数据分析/模板模式后，每次查数必须带 `--format html`;禁止先出表再单独问"要不要出图"。
- **快查纯出数（2026-11-10 用户新规）**:仅问数路径**不带 `--format html`、不带 `--session`**，只用 CLI 默认的 markdown 文本输出，在聊天里转述；不落 HTML、不开档案。用户说"分析一下/出报告/整理成报告/全面看看"（即切换到数据分析）时，才带 `--format html` + `--session` 起档案；此前快查轮次在第一节 `--bridge` 里一句话追述，不补建。

### 出数即停(本轮终点)

给「一句观察 + 2~3 个并列选项」,三种话术轮换:下钻("要不要按渠道拆一下")/ 关联("可结合 VNB 看价值含量")/ 数据观察+建议(指出结果里的具体事实再给方向)。选项必须带"各自能回答什么问题",给完就结束本轮,留退路("先到这儿也可以")。

## 下钻菜单(用户点了名,才往下走一层)

这张表**不是流水线,是菜单**。一次只走一层,走完立刻停下再报菜单。

| 层 | 用户可能想知道的 | 用什么 | 判断标准 |
|---|---|---|---|
| 1 表层盘子 | 规模多大、结构什么样、同比如何 | `single` / `compare` / `topn`(一个维度) | 一轮只上一个维度;必做的第一遍 |
| 2 期间定位 | 缺口集中在哪几个月 | `trend` / 月度同比 | 缺口 100% 集中在少数月时,直接说"断在 X~Y 月" |
| 3 维度归因 | 哪个渠道/机构拖的 | `compare --dim channel/branch` + 分维度同比 | 同幅下跌 = 共性驱动;单点下跌 = 执行问题 |
| 4 品类×缴费 | 断在哪条产品线 | `compare --dim product_category` 再交叉 `single_premium_flag` | 算出每条线占总缺口%,锁定 90%+ 的那一两格 |
| 4.5 产品去留 | 「卖不动」还是「没得卖」 | 按 `product_name` 双期对照:上年有本期归零 / 本期新增 / 两年都在 | 接棒率 < 50% 且归零个数成批(≫5)→ 产品断档,不是流速问题 |
| 5 量价拆分 | 件数掉了还是件均掉了 | APE + `SUM(if_count)` | 件数掉 = 获客/出单环节;件均掉 = 大单客户流失/高件均产品退场 |
| 6 大单验证 | 是不是大单断供 | 保单级 `SUM(if_ape) >= 100000` 计数 | 大单件数跌幅 > 整体件数跌幅,且大单占比反升 → 确认大单断供 |

> **第 4.5 层是最锋利的一招**:2026-11-07 实测,7-8 月缺口 -1.32 亿,前四层只能说到"储蓄类期缴掉了",产品去留一看——61 个产品同期归零(合计 1.73 亿)、新品只接住 5,416 万(接棒率 31%)。结论从"业务不行"翻成"没得卖"。
> 注意:`product_name` 是脱敏代号,**必须请业务按代号回填真实产品名**,否则结论无法落地。

**⚠️ 反面案例(别重犯)**:2026-11-07 用户只问「各渠道业绩达成」,AI 连走 11 轮攒出 11 节档案才交出去,用户全程没有介入机会。正确的第一轮:一条 `compare --dim channel` → 一句结论 → 3 个选项 → 停。

**层间承接**:层与层之间必须有数字承接(如"上节 -32,704 万里,本节这条线占 99.2%"),禁止两张口径不同却并列的孤立表;下钻越深表越细,但结论条永远只写一句话。

## 路径 B:复杂分析(模板模式)

分流器判为「复杂分析」(信号词:分析/归因/拆解/报告/复盘/经营分析/全面看看/怎么回事)时走本路径。**先一句话告知并允许纠正**:"我按完整分析模板来做(6 节骨架,逐节确认);只要个快数的话告诉我。"

### 固定骨架(保证输出稳定)

骨架定义在 `knowledge/analysis_template.yaml`(可配置),默认 6 节:

1. **执行摘要**(最后回填:一句总论 + 至多 3 个关键数)
2. **表层盘子**(必备节;规模 + 同比 + 结构)
3. **期间定位**(缺口断在哪几个月)
4. **维度归因**(渠道/机构,谁拖的)
5. **产品线定位**(可选节;品类×缴费,必要时进产品去留;缺口在期间层已 100% 解释时可跳过)
6. **结论与候选解释**(必备节;断在哪/多深/什么形态 + 需业务确认的候选原因)

### 层间确认(模板定结构,用户定节奏)

- 每节走完出数后**仍要停**:默认动作"继续下一节",用户可跳节(如跳过产品线定位)或提前收尾(直接回填摘要出报告)。
- 骨架只是结构固定,**不解除**专家层的节奏纪律:禁止一口气把 6 节全跑完再交。
- 每节仍用 `--session` 写进过程档案,节标题尽量含骨架槽位的匹配关键词(表层/期间/维度/产品/结论),便于报告脚本对号入座。

### 双产物交付

- **过程档案**(内部留痕):session 机制照常用,产物 `output/<日期>_<session>_分析档案.html`。
- **报告型 HTML**(对外交付):分析走完(或用户提前收尾)时调用:

```bash
python3 scripts/final_report.py --session <id> --title "个险渠道价值专题分析" \
  --subtitle "2026 考核年累 · 承保口径" \
  --summary "一句总论" --summary-points "关键数1|关键数2|关键数3"
```

产物 `output/<日期>_<session>_经营分析报告.html`:封面 + 执行摘要 + 按骨架排序的章节 + 末附「分析路径」小字。
**自动回退**:必备节缺失或渲染异常时,脚本自动回退为档案模式(退出码 2),把档案路径给用户并说明原因。

## 意图清单与调用

| 意图 | 必填槽位 | CLI 示例(快查不带 `--format html`;分析模式统一带) |
|---|---|---|
| 指标菜单 menu | (无) | `query.py --intent menu`(纯文本;未定指标时的第一步) |
| 单指标查询 single | metric, period | `query.py --intent single --metric ape --period 2026YTD --format html` |
| 多机构/多组对比 compare | metric, period, (dim) | `query.py --intent compare --metric vnb --period 2026YTD --dim branch --format html` |
| 趋势分析 trend | metric, period | `query.py --intent trend --metric fyp --period 2026YTD --format html` |
| 同比/环比 yoy | metric, period | `query.py --intent yoy --metric std_premium --period 2026YTD --format html` ⚠️ 只出全公司汇总,不支持 `--dim`;分维度同比走 §兜底 的双期 CASE 模板 |
| 结构占比 share | metric, period, dim | `query.py --intent share --metric fyp --period 2026YTD --dim channel --format html` |
| 排名 TOP N topn | metric, period, dim | `query.py --intent topn --metric ape --period 2026YTD --dim branch --n 5 --format html` |
| 口径问答 koujing | metric | `query.py --intent koujing --metric nbm`(纯文本,无产物) |

可选参数:`--branch Branch_01`(或逗号分隔多家)、`--channel 银保`、`--caliber sm`(受理口径)、`--format json`(机读)、`--chart line|bar|pie|none`、`--out 路径`。
**档案参数(仅分析模式,进入后每轮都带)**:`--session <会话id>`、`--section-title "本节标题"`、`--bridge "与上一节的衔接说明"`。

**执行方式**:用 Bash 运行 `python3 <skill目录>/scripts/query.py ...`。依赖:psycopg、pyyaml;首次运行先跑 `scripts/doctor.py` 自检。

> **⚠️ 必须先 `cd <skill目录>` 再执行(踩过坑)**:`config.yaml` 的 `output.dir` 是 `./output`,session 状态也存在 `./output/.sessions/` 下——**两者都相对当前工作目录**。在别的目录跑会静默新建一套 `./output/`:同一个 `--session` 却"从第 1 节重新开始"。
> 已跑岔的补救:把新目录 `.sessions/<id>.json` 里的 `sections` 合并进 skill 目录的同名状态文件,再 `save_state()` + `build_html()`(两行都要调),最后删掉多出来的 `./output/`。

> **⚠️ Python 解释器选择(踩过坑)**:系统 `python3` 常缺 pyyaml/psycopg,报 `ModuleNotFoundError: No module named 'yaml'` 时**不要** pip install 污染系统环境,改用专用 venv:
> ```bash
> python3 -m venv ~/.venvs/dga && ~/.venvs/dga/bin/pip install "psycopg[binary]" pyyaml
> ~/.venvs/dga/bin/python scripts/query.py ...
> ```
> 判断顺序:`python3 scripts/doctor.py` 通过 → 直接用;报缺包 → 换上面的 venv 解释器重跑。

## 结果呈现(仅数据分析模式;快查只出文本)

> **适用范围**:本节全部规则只在数据分析/模板模式下生效。仅问数快查不产 HTML、不开 session,CLI 默认 markdown 输出直接在聊天里转述即可。

**两条硬要求:① 数据表和图表永远写在同一个产物里;② 同一次分析的所有轮次落在同一份档案里。**

### 1. 一条命令出全套

`query.py ... --format html` 同时输出:可转述的 markdown 表 + HTML 产物(结论条 → 图表/KPI 卡 → 数据表 → 折叠 SQL)。图表形态自动匹配:`trend`→折线、`share`→饼图、`compare`/`topn`/`yoy`→柱状、`single`→KPI 卡;`--chart` 可覆盖。

### 2. 同一份「分析档案」逐轮追加(默认做法)

**新问题就起一份新档案**:session id 只覆盖一次分析的一条追问链;起名建议 `YYYYMMDD-<主题>`。session 状态是持久文件(`output/.sessions/<id>.json`),**不准**把 "channel" 这种通用 id 反复用;误用先 `--reset` 再重起。

```bash
# 第 1 轮:起手规模
query.py --intent compare --metric std_premium --period 2026YTD --dim channel \
  --format html --session 20261107-渠道达成 --section-title "各渠道规模(起手)" \
  --bridge "先看盘子有多大、谁在拖"

# 第 2 轮:按产品类别拆 —— 追加为同一份档案的第 2 节
query.py --intent compare --metric std_premium --period 2026YTD --dim product_category \
  --format html --session 20261107-渠道达成 --section-title "按产品类别拆解" \
  --bridge "在上节 -9.3% 的缺口里,储蓄类贡献 -14.6%、保障类 +5.9%"
```

- 产物固定为 `output/<日期>_<session>_分析档案.html`,左侧粘性目录(点击跳转+滚动高亮)、节间衔接说明、每节结论条与回到目录;仅手机窄屏(≤640px)退回单列。
- **禁止**每轮 `--out` 出新文件;只有用户明确要"单独给我一份"时才省略 `--session`。
- 手动/兜底章节用 `scripts/session_report.py --session <id> --append-section <json|文件|->` 追加;`--show` 看结构,`--reset` 清空。
- **⚠️ 手工改档案的坑**:直接操作 `load_state()` 的 `sections` 后,`save_state()` 只落 JSON、不重建 HTML——必须紧接着显式 `build_html(state)`:
  ```python
  from session_report import load_state, save_state, build_html
  st = load_state("20261107-主题")
  st["sections"][i]["headline"] = "..."
  save_state(st); build_html(st)              # 两行都要
  ```
- **改口径后回头统一旧节**:后轮推翻前轮措辞时,必须回去把旧句也改掉;同一份档案前后矛盾 = 演示翻车。

### 3. 回复里的「关联」:演进表

第一轮不给演进表(只有一行没意义)——直接给结论 + 明细 + 2~3 个下钻选项。第二轮起,聊天回复先给演进表,再给本轮新表重点行,最后给产物路径。演进表固定四列:

| 轮次 | 问的是什么 | 结论(带数) | 相对上一轮 |

新表尽量带**衔接列**(如"占上节缺口 %""贡献度"),不出现口径不同却并列的孤立表。

### 4. 自由查询/兜底场景的产物

手写 SQL 的结果仍须表图进同一份档案:用 `chart.py` 手工模式(`--table-header` + `--table-rows`,行内逗号分隔、行间 `|` 分隔,`--type none` 只出表),或 `session_report.py --append-section`。禁止只有图没有数的 HTML,禁止绕开档案另开文件。

### 5. 彩蛋简报

当一轮分析(2 次以上查询)覆盖某机构多个指标后,主动提议:
> "要不要我把这段分析整理成一份机构简报?(演示版)"
用户同意后调用 `python3 scripts/report_teaser.py --branch Branch_01 --period 2026YTD`,说明这是演示版彩蛋。

## 口径实现要点(红线在专家层,这里只记实现注意)

- 完整口径红线(考核年制/承保默认/小基数/未完整月/精度/大单保单级聚合)见专家层 `agents/data-guide-agent.md`,手写 SQL 前必读。
- `query.py` 已内置:NBM/标保率只算个险/银保/经代且 SUM/SUM 现算;万元除 10000;未完整月标注。
- 小基数真实案例(手写 SQL 时参照):2026-09 只统计到 9/10,上年 9/1~9/10 合计仅 449.62 万,算出「同比 +417%」纯属基数效应;应改用上年 9 月整月(2,771.13 万)做可比参照。
- 大单定义:business_defs 见 `knowledge/metric_cards.yaml`;保单级聚合(`GROUP BY policy_no` 后 `SUM(if_ape) >= 100000`),表是「一行 = 保单 × 产品」,按行判断会把大单拆小漏掉。

## 兜底

- **指标不认识/没指定**:先 `query.py --intent menu` 亮菜单;反查口径用 `query.py --intent koujing --metric <最接近的指标>`,或查 metric_cards.yaml 的 aliases。永远不要用默认指标顶替用户选择。
- **查询报错**:先原样转述错误,检查指标 id / 维度 id / period 格式;不要静默改参数重试超过 1 次。
- **自由追问超出 8 类意图**(如"列出 APE 前 10 的保单明细"):可手写只读 SELECT,必须守专家层全部口径红线、带 LIMIT(≤100)、只用 policy_detail,结果注明"此为自由查询"。
- **分维度同比**(`yoy` 不支持 `--dim` 的标准兜底):双期 CASE 聚合,一条 SQL 出「本期/上年同期/差额」,口径与 `query.py` 一致(`万元` → `SUM(col)/10000`;`derived` → 用 `formula_if` 现算),维度列名对照 metric_cards.yaml 的 `dims`:
  ```sql
  SELECT channel_name AS dim,
         ROUND(SUM(CASE WHEN trans_date BETWEEN '<本期起>' AND '<本期止>' THEN if_ape ELSE 0 END)/10000.0, 2) AS cur,
         ROUND(SUM(CASE WHEN trans_date BETWEEN '<上年起>' AND '<上年止>' THEN if_ape ELSE 0 END)/10000.0, 2) AS prev
  FROM policy_detail
  WHERE (trans_date BETWEEN '<本期起>' AND '<本期止>')
     OR (trans_date BETWEEN '<上年起>' AND '<上年止>')
  GROUP BY channel_name ORDER BY cur DESC NULLS LAST LIMIT 100
  ```
  上年窗口 = 本期起止各减一年(2/29 退化为 2/28),不要用 `-365 天`。
- **分维度 × 月度矩阵**(`trend` 只出总量):把 `SUBSTR(trans_date,1,7)` 加进 GROUP BY;本期/上年分两条 SQL 各取一次(每条守 LIMIT ≤100),在 Python 里按月份下标对齐。
- **量价拆分**(件数 vs 件均):同条件下另取 `SUM(if_count)`,件均 = APE(万元)/件数;件数掉 = 获客环节,件均掉 = 大单客户流失,别混为一谈。

## 配置与移植

`config.yaml`:数据库连接(支持 `DGA_DB_*` 环境变量覆盖)、产物目录(默认 `./output`)、演示模式开关(`proactive_menu`)。
复杂分析骨架:`knowledge/analysis_template.yaml`(章节顺序/必备节/匹配关键词/摘要关键数上限),改它即可调模板,不用动代码。
换数据源:在 `scripts/db_adapter.py` 注册新适配器,改 `datasource.type`。
体检:`python3 scripts/doctor.py` 一键检查依赖/连接/知识库/产物目录。
