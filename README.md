# astrbot_plugin_cake_denia

今天你给娅娅喂小蛋糕了吗？发送 🍰（或「蛋糕」）就可以给鸣潮达妮娅（娅娅）喂一块小蛋糕！

一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架设计的趣味喂蛋糕插件。

## 功能

- 🍰 / 蛋糕 喂蛋糕（连发计数，`🍰🍰🍰` = 3 块），娅娅撒娇回应 + 自动生成粉色日历图
- 🍰 @某人 替别人喂蛋糕
- 🍰日历：查看娅娅本月日历（粉色系图片）
- 🍰报告 / 🍰分析 [月|年]：娅娅投喂分析报告
- 🍰生涯：投喂生涯档案
- 🍰补签 DD [次数]：补签某天
- 🍰榜 [页码]：排行榜（自己喂/被喂/替喂 × 今日/本月，含成就徽章）
- 🍰成就：查看成就墙
- 🍰重置榜单：管理员重置今日计数（可@他人）
- 🍰帮助：查看帮助

## 安装

将插件目录 `astrbot_plugin_cake_denia` 放入 AstrBot 的 `data/plugins/`，在管理面板「插件管理」中启用；或将插件目录打包为 zip 后在「插件管理」页面上传安装。

## 使用

| 指令 | 说明 |
| --- | --- |
| `🍰` / `蛋糕` | 给娅娅喂一块小蛋糕 |
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
| group_whitelist | list | [] | 群白名单，不填全群可用 |
| user_blacklist | list | [] | 用户黑名单 |
| day_start_time | string | 00:00 | 每天开始时间 |
| auto_delete_last_month_data | bool | true | 自动清理旧数据 |
| daily_max_checkins | int | 0 | 每日最多喂蛋糕数，0 无限制 |
| monthly_max_checkins | int | 0 | 每月最多喂蛋糕数，0 无限制 |
| ranking_display_count | int | 10 | 排行每页人数 |
| llm_enabled | bool | true | LLM 对话总开关 |
| llm_trigger_probability | float | 0.3 | LLM 触发概率 |
| llm_daily_min_cakes | int | 3 | 当日喂满几块才可触发 LLM |
| llm_daily_limit | int | 5 | 全群每日 LLM 触发上限 |

## 依赖

无第三方依赖（AstrBot 自带 aiosqlite 与 Pillow）。将娅娅立绘图命名为 `denia.png` 放入插件目录，排行榜图顶部会自动显示。

## 致谢

基于 [astrbot_plugin_deer_check v3](https://github.com/DITF16/astrbot_plugin_deer_check)（DITF16&Foolllll）改造：单系统化，并新增成就系统与 LLM 概率对话。
