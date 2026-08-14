# 资源文件夹说明

插件从本目录加载字体与娅娅立绘，**全部可自行替换，无需重新打包插件**。

## 目录结构

```
resources/
├── fonts/        # 字体目录（预留，需自行放入字体）
│   ├── font.ttf      # 中文字体（渲染日历/排行/报告/生涯图）
│   └── emoji.ttf     # emoji 字体（渲染 🍰🏆 等，可选）
└── denia.png     # 娅娅立绘（可选，放入后排行榜图顶部自动显示）
```

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
