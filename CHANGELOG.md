# 更新日志

## 未发布

### 修复

- **别人 @ 机器人发 🍰 被记成「替机器人送蛋糕」**：`_get_at_targets()` 把消息里所有 `at` 段都当成替喂目标，只有 `@全体成员` 被排除。别人按习惯 @ 一下机器人再发 🍰，本意是「正常喂」，却被记成「某人替机器人送蛋糕」——替喂榜多出一条，机器人还成了被喂对象白刷一份好感度
  - 修法：收集机器人的各种 id 写法（`event.get_self_id()` 与 `message_obj.self_id` 取并集，各平台字段不统一，宁可多滤不可漏）并从替喂目标中排除
  - 顺带修：同一个人被重复 @ 时不再把蛋糕数累加多次（`ON CONFLICT` 每循环加一次），改为按人先去重
  - 取不到 `self_id` 的平台（如 webchat）保持不过滤，只求不崩不过度过滤

## 1.1.0 (2026-10-12)

### 新增

- **渲染模块化拆分**：`render_html/` 拆分为 `base` / `calendar` / `career` / `ranking` / `analysis` 五个模块，共用逻辑收敛到 `render_common.py`，新增 `preview_support.py` 统一预览支持
- **README 好感度联动章节**：说明联动机制、触发时机、`favour_daily_limit` 开关与排查方式，并补上配置表里此前缺失的 `favour_daily_limit`

### 修复

- **主题色透明度解析 bug**：PIL 后端卡片发灰的根源，修复后颜色恢复正常
- **好感度联动找不到 Favour_Lite**：`_find_favour_plugin()` 原先只按 metadata name 精确匹配 `astrbot_plugin_Favour_Ultra`，而 Favour_Lite 的注册名是 `astrbot_plugin_Favour_Lite`，导致装 Lite 时联动被静默跳过（查找返回 `None`，连日志都不报）。现同时接受两个名字，对原版 Ultra 用户保持兼容

### 变更

- **渲染全面精修**：HTML/Chrome 与纯 Pillow 双后端的日历、排行榜、报告、生涯四类图统一换新玻璃质感
- `theme.py`、`_conf_schema.json`、`resources/texts.py` 同步更新