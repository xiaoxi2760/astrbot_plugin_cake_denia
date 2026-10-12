# astrbot_plugin_cake_denia

今天你喂娅娅小蛋糕了吗？发送 🍰（或「蛋糕」）就可以给鸣潮达妮娅（娅娅）喂一块小蛋糕！

一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架设计的趣味喂蛋糕插件。

## 功能

- 🍰 / 蛋糕 喂蛋糕（按完整触发词计数：`🍰🍰🍰` = 3 块、`蛋糕` = 1 块），娅娅随机回复 + 自动生成日历图
- 🎨 双人格随机回复：娅娅（日常学生版）为主，达妮娅（boss版）以 20% 概率作为彩蛋随机出现（与主题无关）
- 🍰 @某人 替别人喂蛋糕
- 🍰日历：查看娅娅本月日历（娅娅粉彩 / 达妮娅暗夜主题可选）
- 🍰报告 / 🍰分析 [月|年]：娅娅投喂分析报告
- 🍰生涯：投喂生涯档案
- 🍰补签 DD [次数]：补签某天
- 🍰榜 [页码]：排行榜（自己喂/被喂/替喂 × 今日/本月，含成就徽章）
- 🍰成就：查看成就墙
- 🍰重置榜单：管理员重置今日计数（可@他人）
- 💗 好感度联动：每天首次喂蛋糕时好感度 +1~5（需搭配 [Favour Lite](https://github.com/xiaoxi2760/astrbot_plugin_Favour_Lite)，详见下方「好感度联动」）
- 🍰帮助：查看帮助

## 效果预览

![娅娅投喂日历](assets/calendar-preview.png)

## 安装

将插件目录 `astrbot_plugin_cake_denia` 放入 AstrBot 的 `data/plugins/`，在管理面板「插件管理」中启用；或将插件目录打包为 zip 后在「插件管理」页面上传安装。

## 使用

| 指令 | 说明 |
| --- | --- |
| `🍰` / `蛋糕` | 给娅娅喂一块小蛋糕（`🍰🍰🍰`=3 块，`蛋糕`=1 块，单条上限见配置） |
| `🍰 @某人` | 替某人喂蛋糕 |
| `🍰日历` | 查看娅娅本月日历 |
| `🍰报告` / `🍰分析 [MM\|YYYY]` | 本月/指定月份或年份投喂报告 |
| `🍰生涯` | 投喂生涯档案 |
| `🍰补签 DD [次数]` | 补签某天 |
| `🍰榜 [页码]` | 查看排行榜 |
| `🍰成就` | 查看成就墙 |
| `🍰重置榜单` | 管理员重置今日计数 |
| `🍰帮助` | 查看帮助 |

## 配置

管理面板「插件管理 → 插件名 → 配置」：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| trigger_words | list | ["🍰", "蛋糕"] | 触发词（命令关键词），可自定义；按完整触发词计数，如改 `["🍬","糖果"]` 则 `🍬🍬`=2 块、`糖果`=1 块 |
| group_whitelist | list | [] | 群白名单，不填全群可用 |
| user_blacklist | list | [] | 用户黑名单 |
| day_start_time | string | 00:00 | 每天开始时间 |
| auto_delete_last_month_data | bool | false | 自动清理两个月前及更早的投喂记录（注意：不是删上月）。默认关闭以保留历史，生涯/年度报告需要历史数据 |
| daily_max_checkins | int | 0 | 每日最多喂蛋糕次数（每条消息算 1 次，含帮喂/补签），超出随机提示娅娅吃不下 |
| max_cakes_per_message | int | 3 | 单条消息最多喂蛋糕数，超出提示娅娅吃不下 |
| ranking_display_count | int | 10 | 排行每页人数 |
| llm_enabled | bool | true | LLM 对话总开关 |
| llm_trigger_probability | float | 0.3 | LLM 触发概率 |
| llm_daily_min_cakes | int | 3 | 当日喂满几块才可触发 LLM |
| llm_daily_limit | int | 5 | 全群每日 LLM 触发上限 |
| auto_download_font | bool | true | resources/fonts 无字体时自动下载默认字体（阿里妈妈方圆体 + emoji），失败回退系统字体 |
| font_download_url | string | GitHub Releases | 中文字体下载地址，自备字体时填自己的链接，留空用默认 |
| emoji_download_url | string | GitHub Releases | emoji 字体下载地址，Windows 系统自带 emoji 字体可不填 |
| render_backend | string | html | 渲染后端：`html`（HTML/CSS + Playwright + 系统 Chrome，**日历/排行榜/报告/生涯四类图均支持**，默认）或 `pil`（纯 Pillow 绘制，无额外依赖，效果略逊）。html 需要服务器安装 playwright 与 Chrome，未安装或渲染失败会**自动降级 pil**，不影响使用 |
| theme_preset | string | white-1 | 日历主题：`white-1`（娅娅·泡泡初绽，默认）/ `white-2`（娅娅·马卡龙双层）/ `black-1`（达妮娅·暗夜泡泡）/ `black-2`（达妮娅·阿列夫之眼）/ `custom`（resources/theme.json 自定义） |
| favour_daily_limit | bool | true | 好感度联动每日限制：开启时每天每个用户第一次获得蛋糕才 +1~5；关闭后每次喂蛋糕都加（用于测试好感度链路是否通畅） |

> 达妮娅（暗夜）是**彩蛋**：无论 `theme_preset` 选什么主题，喂蛋糕回复都有 20% 概率以「达妮娅」（boss版）口吻出现，且**当日历图同时生成时，那张日历也会用达妮娅暗夜主题（black-1）渲染**。触发达妮娅彩蛋时，该条回复**不会触发 LLM 对话**。想关掉彩蛋，把 `resources/texts.py` 里的 `BLACK_*` 列表清空即可。

## LLM 上下文

触发 LLM 对话时，会把本次投喂的真实数据喂给模型（本次投喂块数、当日累计、投喂者连续天数、生涯累计、当前时段），因此娅娅的回应会贴合当下情境而不是通用撒娇。人设提示固定在 `LLM_SYSTEM_PROMPT`，上下文模板是 `LLM_CONTEXT_TEMPLATE`（均位于 `resources/texts.py`，可直接改文案）。统计查询异常时自动降级为固定 prompt，不会影响投喂计数。

## 💗 好感度联动

喂蛋糕会顺带给用户涨好感度，**需要搭配好感度插件**。没装或没启用时喂蛋糕功能照常可用，只是不显示好感变动行。

> [!IMPORTANT]
> **联动请安装 [astrbot_plugin_Favour_Lite](https://github.com/xiaoxi2760/astrbot_plugin_Favour_Lite)（精简修改版），不要用原版 [Favour_Ultra](https://github.com/nuomicici/astrbot_plugin_Favour_Ultra)。**
>
> 本插件按**纯全局口径**写入：session 固定为 `global`，同一用户跨群 / 跨平台共享一份好感度。
> Favour_Lite 正是纯全局模式，两边口径一致；而原版 Favour_Ultra 是**会话隔离**的，
> 本插件写进 `global` 的那条记录不会被它自己的查询命中，表现为「蛋糕也喂了、好感提示也弹了，但查询和排名里看不到变化」。

| 项 | 说明 |
| --- | --- |
| 触发时机 | 每天每个用户**第一次**获得蛋糕时，好感度随机 **+1~5**，当天不再重复加 |
| 帮喂 | `🍰 @某人` 同样计入被帮喂用户的当日首喂判定 |
| 开关 | 配置 `favour_daily_limit`，默认 `true`；设为 `false` 则**每次**喂蛋糕都加，用来验证链路是否通畅 |
| 提示行 | 优先复用 Favour_Lite 的 `favour_change_line()`（`❤️/🖤：好感度±X  总好感：Y`），取不到时回退为 `（好感度 +N）` |
| 反向联动 | 在 Favour_Lite 里执行 `称号`，蛋糕生涯称号会作为称号显示来源之一 |

排查方式：日志里搜 `[联动好感度]` 可看到命中的插件、数据库路径与变化前后数值；搜 `联动好感度失败` 说明写入环节报错。

## 自动清理

插件启动与每天首次调用时各执行一次维护：

- `tmp/` 中超过 1 小时的临时图片/HTML
- `avatars/` 中超过 7 天未更新的 QQ 头像缓存（退群/改名用户不再残留）
- `metadata` 表中超过 3 天的日粒度占位键（`favour_first` / `daily_ops` / `llm_user` / `llm_count`，跨天后不可能再命中）

`checkin` / `help_record` / `achievements` 历史数据不受影响，仍由 `auto_delete_last_month_data` 控制。

## 依赖

无第三方依赖（AstrBot 自带 aiosqlite 与 Pillow）。

## 渲染后端

四类图（📅 日历 / 🏆 排行榜 / 📊 投喂报告 / 💗 生涯档案）共用同一个 `render_backend`：

| 后端 | 说明 | 依赖 |
| --- | --- | --- |
| `html`（默认） | HTML/CSS + Playwright + 系统 Chrome，2x 高清，卡片投影细腻，长文本自动换行 | 需 `pip install playwright` + 服务器装 Chrome |
| `pil` | 纯 Pillow 绘制，无额外依赖 | 无（AstrBot 自带 Pillow） |

**降级行为**：选 `html` 但服务器没装 playwright/Chrome 时，日志会记录错误并自动回落到 `pil`，功能完全不受影响。想要最好的效果就装一下：

```bash
pip install playwright
```

## 资源文件夹 `resources/`

- `resources/texts.py`：娅娅文案集中文件。**随机回复池**（喂蛋糕/帮喂/吃不下/每日超限）与**双人格文案**（娅娅 + 达妮娅彩蛋各一组）都在这里，改文案只改这一个文件（改完重载插件生效）
- `resources/fonts/font.ttf`：中文字体。**插件包不携带字体**（体积大），需自行下载放入；未放入时会自动尝试系统字体（微软雅黑/思源黑体/Noto Sans CJK），全部缺失时图片生成降级为文字回复，打卡计数不受影响。下载指引见 [resources/README.md](resources/README.md)

更多自定义（成就/主题/触发词）见 [resources/DIY.md](resources/DIY.md)。
