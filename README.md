# 🍰 娅娅的小蛋糕（cake_denia）

一款为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 框架设计的**鸣潮达妮娅（娅娅）专属喂蛋糕插件**。

今天你给娅娅喂小蛋糕了吗？发送 🍰 就可以给娅娅喂一块小蛋糕！

## 命令

| 命令 | 功能 |
|---|---|
| `🍰` / `蛋糕`（可连发，`🍰🍰🍰`=3块） | 给娅娅喂小蛋糕 |
| `🍰 @某人` | 替某人喂娅娅蛋糕 |
| `🍰日历` | 查看娅娅本月日历（粉色系） |
| `🍰报告` / `🍰分析` [月/年] | 娅娅投喂分析报告 |
| `🍰生涯` | 投喂生涯档案 |
| `🍰补签 DD [次数]` | 补签某天 |
| `🍰榜` [页码] | 排行榜（自己喂/被喂/替喂 × 今日/本月，含成就徽章） |
| `🍰成就` | 查看成就墙 |
| `🍰重置榜单` | 管理员重置今日计数（可@他人） |
| `🍰帮助` | 帮助 |

## 特性

- **双系统文案**：全部回复为娅娅撒娇元气风
- **成就系统**：13 项成就（累计喂满 10/50/100/365/1000 块、连续 3/7/30 天、单日暴击、替喂/被喂），解锁瞬间提示，排行榜显示 🏆 徽章
- **LLM 概率对话**：当天喂满 3 块后，有概率（默认 30%）触发娅娅的 LLM 撒娇回复；每个用户每天最多 1 次，全群每天最多 5 次（可配置）
- **粉色主题图片**：日历/排行/报告/生涯图均为粉色蛋糕主题
- **娅娅立绘接口**：将娅娅图片命名为 `denia.png` 放入插件目录，日历图/排行图顶部自动使用（不放置则用 🍰 emoji）
- 每日/每月喂蛋糕上限、群白名单、用户黑名单、凌晨起始时间等均可配置

## 配置

| 配置项 | 默认 | 说明 |
|---|---|---|
| `group_whitelist` | 空 | 群白名单，不填全群可用 |
| `user_blacklist` | 空 | 用户黑名单 |
| `day_start_time` | `00:00` | 每天开始时间 |
| `auto_delete_last_month_data` | `true` | 自动清理旧数据 |
| `daily_max_checkins` / `monthly_max_checkins` | `0` | 每日/每月喂蛋糕上限，0 无限制 |
| `ranking_display_count` | `10` | 排行每页人数 |
| `llm_enabled` | `true` | LLM 对话总开关 |
| `llm_trigger_probability` | `0.3` | LLM 触发概率 |
| `llm_daily_min_cakes` | `3` | 当日喂满几块才可触发 LLM |
| `llm_daily_limit` | `5` | 全群每日 LLM 触发上限 |

## 安装

在 AstrBot 插件管理页面上传 zip 安装（将 `cake_denia/` 目录打包为 zip）。

## 数据

数据库位于 `data/plugin_data/cake_denia/`（`yaya_cake.db`），包含：
- `checkin`：喂蛋糕记录（user_id, group_id, checkin_date, cake_count）
- `help_record`：帮喂记录
- `achievements`：成就解锁记录
- `metadata`：LLM 触发计数等

## 致谢

基于 [astrbot_plugin_deer_check v3](https://github.com/DITF16/astrbot_plugin_deer_check)（DITF16&Foolllll）改造，单系统化并新增成就与 LLM 对话。
