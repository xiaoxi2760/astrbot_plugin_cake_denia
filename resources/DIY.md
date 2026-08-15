# 🍰 娅娅插件 DIY 指南

本插件的大部分外观与内容都可以**不改一行代码**自定义。下面按"想改什么 → 改哪里 → 怎么改"说明。

> 通用规则：修改 JSON / txt 类文件后，在 AstrBot 管理面板 **重载插件** 即可生效。

---

## 一、改文案 → `resources/texts.py`

所有用户可见文案（喂蛋糕回复、帮喂、吃不下、LLM 人设、成就提示、报告、生涯评语、排行榜、帮助、各类提示）都集中在这里。

- 每个条目上方有注释说明用途和 `{占位符}` 的含义
- 列表型（如 `FEED_SUCCESS`）会随机取一条，**加一条就等于多一个随机回复**
- **双人格彩蛋**：娅娅一组（`FEED_SUCCESS` 等）+ 达妮娅一组（`BLACK_FEED_SUCCESS` 等）。达妮娅是**彩蛋**——无论选什么主题，每条喂蛋糕回复都有 20% 概率以达妮娅（容器/boss·虚质巨手方块）口吻出现，且**当天生成的日历图同步用达妮娅暗夜主题（black-1）渲染**、**该条不会触发 LLM 对话**；想关掉彩蛋，把 `BLACK_*` 列表清空即可（代码会自动回退到娅娅池）
- 例子：把 `FEED_SUCCESS` 里的某条改成你自己的话，或新增一条

```python
# 单块成功（娅娅，随机取一条）
FEED_SUCCESS = [
    "娅娅睁开半阖的眼睛，看了蛋糕一会儿：给我的？……嗯，那我收下了。",
    # ↑ 想改就改这里，或在这一行后加新的
]
```

---

## 二、改成就 → `resources/achievements.json`

成就定义在 JSON 数组里，每个成就一个对象：

```json
{"id": "cake_10", "name": "初尝甜蜜", "icon": "🍰", "desc": "累计喂满 10 块蛋糕", "type": "total_cakes", "threshold": 10}
```

| 字段 | 含义 |
| --- | --- |
| `id` | 成就唯一标识（英文，勿重复） |
| `name` | 成就名（展示用） |
| `icon` | 图标 emoji |
| `desc` | 描述 |
| `type` | 判定依据：`total_cakes` 累计蛋糕数 / `streak` 连续天数 / `max_daily` 单日最多 / `total_helped` 替喂总数 / `total_received` 被喂总数 |
| `threshold` | 达标阈值 |

操作：
- **加成就**：复制一条改字段
- **删成就**：删掉整行
- **改阈值/描述/图标**：改对应字段

> 已解锁的成就记录会保留，即使你之后删掉了该成就的定义。

---

## 三、改外观 → `resources/theme.json` 与 `resources/themes/`

日历外观由**主题**驱动，管理面板配置 `theme_preset` 选择：

| theme_preset | 主题 |
| --- | --- |
| `custom` | 用户自定义（读 `theme.json`） |
| `white-1` | 娅娅 · 泡泡初绽（默认） |
| `white-2` | 娅娅 · 马卡龙双层 |
| `black-1` | 达妮娅 · 暗夜泡泡 |
| `black-2` | 达妮娅 · 阿列夫之眼 |

> `black-1` / `black-2` 是「达妮娅」暗夜主题，仅决定日历配色，不影响回复口吻。达妮娅回复是**彩蛋**（20% 概率，与主题无关，触发时日历同步暗夜渲染）；想关掉彩蛋，把 `texts.py` 里的 `BLACK_*` 列表清空即可。

### 自定义主题（推荐）

1. 复制任意一个 `resources/themes/*.json` 内容到 `resources/theme.json`
2. 修改颜色 / 泡泡 / 光晕 / 开关
3. `theme_preset` 保持 `custom`，重载插件

### 主题结构

```json
{
  "colors": {          // 日历配色
    "bg_top": "#fff6fb",   // 背景上
    "bg_mid": "#ffeef4",   // 背景中
    "bg_bottom": "#ffe4ef",// 背景下
    "card_fill": "rgba(255,255,255,0.94)", // 卡片填充
    "card_border": "#f3d6e4",
    "title": "#65432a",    // 标题
    "subtitle": "#b2909e", // 副标题
    "weekday": "#b08a98",  // 星期
    "weekend": "#db7093",  // 周末/今天强调
    "day_text": "#5a464f", // 日期数字
    "empty_bg": "#fcf9fa", // 未投喂日背景
    "empty_border": "#f0e8ec",
    "feed_top": "#ffdcec", // 投喂日渐变上
    "feed_bottom": "#ffc8dd", // 投喂日渐变下
    "feed_border": "#f6b6cf",
    "today_bg": "#fff0f6", // 今天背景
    "badge": "#e9546b",    // 块数徽章
    "foot_top": "#ffe3ee", // 页脚渐变上
    "foot_bottom": "#ffd0e2", // 页脚渐变下
    "foot_text": "#d84762" // 页脚文字
  },
  "glows": [   // PIL 背景光晕（空数组 = 无光晕）
    {"cx": 110, "cy": 45, "radius": 150, "color": "#ffffff", "strength": 70}
  ],
  "glow_top": "rgba(255,255,255,0.9)",      // HTML 场景光晕（上）
  "glow_bottom": "rgba(255,214,234,0.8)",   // HTML 场景光晕（下）
  "bubbles": [  // 背景泡泡（空数组 = 无泡泡）
    {"left": 18, "top": 30, "size": 54, "opacity": 0.92, "fill": "#f2708f"}
  ],
  "options": {
    "show_avatar": true,   // 是否显示左上角 QQ 头像
    "show_bubbles": true   // 是否显示泡泡
  }
}
```

- 颜色值支持 `#rrggbb` / `#rgb` / `rgb(r,g,b)` / `rgba(r,g,b,a)`
- 想加泡泡：往 `bubbles` 数组加一条（left/top 是位置，size 大小，opacity 不透明度 0~1，fill 主色）
- 想加自己的主题预设：在 `resources/themes/` 新建 `你的名字.json`，然后在 `_conf_schema.json` 的 `theme_preset.options` 里加上 `"你的名字"`（或直接用 custom 读 theme.json）

---

## 四、改命令关键词 → 配置 `trigger_words`

默认触发词是 `["🍰", "蛋糕"]`，可在管理面板配置里改成任意词（建议单字符或短词）。

- 改成 `["🍬", "糖果"]` 后，命令变为：`🍬`（喂）、`🍬日历`、`🍬榜`、`🍬补签 5` 等
- 喂蛋糕**按完整触发词计数**：`🍰🍰`=2 块、`蛋糕`=1 块、`🍰蛋糕`=2 块；消息开头只有触发词的部分字符（如单独一个「蛋」）会被静默忽略，不算喂蛋糕

---

## 五、其他可配置项

| 配置项 | 说明 |
| --- | --- |
| `render_backend` | 日历渲染后端：`pil`（无额外依赖）/ `html`（Playwright+Chrome，效果更精细，失败自动降级 pil） |
| `daily_max_checkins` | 每日最多喂蛋糕**次数**（每条消息算 1 次，含帮喂/补签），0 = 无限制 |
| `max_cakes_per_message` | 单条消息最多喂蛋糕数（超出提示娅娅吃不下） |
| `llm_enabled` 等 | LLM 概率对话开关、概率、触发下限、每日上限 |
| `group_whitelist` / `user_blacklist` | 群白名单 / 用户黑名单 |
| `day_start_time` | 每天开始时间（凌晨几点前算前一天） |

---

## 六、字体与立绘

| 文件 | 说明 |
| --- | --- |
| `resources/fonts/font.ttf` | 中文字体（渲染日历/排行/报告/生涯图）。插件不携带字体，需自行放入；缺失时自动尝试系统字体（微软雅黑/思源黑体等） |
| `resources/fonts/emoji.ttf` | emoji 字体（渲染 🍰🏆 等），可选；Windows 自带 Segoe UI Emoji |
| `resources/denia.png` | 娅娅立绘（正方形 PNG），放入后排行榜图顶部自动显示 |

---

## 七、自定义成就 / 主题 / 文案后如何生效

1. 修改对应文件
2. AstrBot 管理面板 → 插件管理 → 本插件 → **重载**（或重启 AstrBot）
3. 完成

> 提示：`texts.py`、`theme.json`、`achievements.json` 修改后重载即生效；`render_backend`、`trigger_words`、`theme_preset` 是配置项，改配置保存即可。
