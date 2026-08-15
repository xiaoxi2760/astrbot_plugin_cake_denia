# 资源文件夹说明

插件从本目录加载文案、成就、主题、字体与娅娅立绘，**全部可自行 DIY，无需重新打包插件**。

## 目录结构

```
resources/
├── DIY.md              # 🍰 娅娅插件 DIY 指南（改文案/成就/主题/触发词）
├── texts.py            # 娅娅文案集中文件（改文案只改这一个文件）
├── achievements.json   # 成就定义（可增删成就、改图标/描述/阈值）
├── theme.json          # 自定义日历主题（theme_preset=custom 时生效）
├── themes/             # 预设主题（下拉菜单里可选）
│   ├── white-1.json      # 娅娅 · 泡泡初绽
│   ├── white-2.json      # 娅娅 · 马卡龙双层
│   ├── black-1.json      # 达妮娅 · 暗夜泡泡
│   └── black-2.json      # 达妮娅 · 阿列夫之眼
├── fonts/              # 字体目录（预留，需自行放入字体）
│   ├── font.ttf          # 中文字体（渲染日历/排行/报告/生涯图）
│   └── emoji.ttf         # emoji 字体（渲染 🍰🏆 等，可选）
└── denia.png           # 娅娅立绘（可选，放入后排行榜图顶部自动显示）
```

## 文案 texts.py

所有用户可见文案（喂蛋糕回复、LLM 人设、成就、报告、生涯、排行榜、帮助等）都集中在 `resources/texts.py`，按功能分区。改文案只改这个文件即可；**注意它是 Python 模块，修改后需要重载插件生效**。

**随机回复池**：`FEED_SUCCESS` / `FEED_MULTI` / `HELP_FEED` / `FEED_TOO_MANY` / `DAILY_LIMIT_REPLIES` 是列表，每条消息随机取一条——加一条 = 多一个随机回复。

**双人格彩蛋文案**：娅娅（慵懒温柔/口是心非）一组 + 达妮娅（容器真身/boss）一组。达妮娅是**彩蛋**：无论选什么主题，每条喂蛋糕/帮喂/吃不下/每日超限回复都有 20% 概率以达妮娅口吻出现，且**当天同时生成的日历图会用达妮娅暗夜主题（black-1）渲染**、**该条不会触发 LLM 对话**。想关掉彩蛋，把 `BLACK_*` 列表清空即可（代码会自动回退到娅娅池）。

## 成就 achievements.json

JSON 数组，每个成就一个对象：

```json
{"id": "cake_10", "name": "初尝甜蜜", "icon": "🍰", "desc": "累计喂满 10 块蛋糕", "type": "total_cakes", "threshold": 10}
```

- `type` 可选：`total_cakes`（累计蛋糕数）、`streak`（连续天数）、`max_daily`（单日最多）、`total_helped`（替喂总数）、`total_received`（被喂总数）
- 想加成就就复制一条改字段；想删成就就删整行；改阈值就改 `threshold`
- 修改后重载插件生效（已解锁的成就会保留）

## 主题 theme.json / themes/

日历外观由主题驱动，管理面板配置 `theme_preset` 下拉切换：

- `custom`：读 `theme.json`（用户自定义）
- `white-1`：娅娅 · 泡泡初绽（粉白梦幻，默认）
- `white-2`：娅娅 · 马卡龙双层（粉彩甜系）
- `black-1`：达妮娅 · 暗夜泡泡（深紫暗夜）
- `black-2`：达妮娅 · 阿列夫之眼（黑红神秘）

> `black-1` / `black-2` 仅决定日历暗夜配色，不影响回复口吻。达妮娅回复是**彩蛋**（20% 概率，与主题无关，触发时日历同步暗夜渲染），见上文文案说明。

主题结构：

- `colors`：日历配色（背景、卡片、标题、投喂日、徽章、页脚等），值支持 `#rrggbb` / `#rgb` / `rgb()` / `rgba()`
- `bubbles`：背景泡泡列表（`left`/`top`/`size`/`opacity`/`fill` 颜色），删空数组即无泡泡
- `glows`：PIL 背景光晕列表（`cx`/`cy`/`radius`/`color`/`strength`），空数组即无光晕
- `glow_top` / `glow_bottom`：HTML 场景两处光晕颜色
- `options.show_avatar` / `options.show_bubbles`：头像与泡泡显示开关

想自定义主题：复制任意预设到 `theme.json` 改颜色，再把 `theme_preset` 设为 `custom`。PIL 与 HTML 渲染均读取同一份主题。

## 字体下载

1. 下载一个**中文字体**（TTF 格式），重命名为 `font.ttf` 放入 `resources/fonts/`：
   - 阿里妈妈方圆体：https://www.alibabafonts.com/#/font （免费商用）
   - 思源黑体 Noto Sans SC：https://fonts.google.com/noto/specimen/Noto+Sans+SC
   - 微软雅黑（Windows 系统自带，一般无需下载）
2. （可选）下载 emoji 字体重命名为 `emoji.ttf` 放入同目录：
   - Noto Color Emoji：https://github.com/googlefonts/noto-emoji
   - Windows 系统自带 Segoe UI Emoji，无需下载

## 没有字体会怎样？

插件会自动尝试系统字体（微软雅黑/思源黑体/Noto Sans CJK 等）渲染；全部缺失时图片生成会降级为文字回复，打卡计数等核心功能不受影响。

## 娅娅立绘

将达妮娅立绘图（建议正方形 PNG）命名为 `denia.png` 放入 `resources/`，排行榜图顶部会自动显示。
