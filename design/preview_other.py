"""预览生成器：为报告 / 生涯 / 排行榜三张图生成效果图。

用途：改版时肉眼对比效果，不依赖 AstrBot 运行时。
运行：py astrbot_plugin_cake_denia/design/preview_other.py [theme_preset]
输出：astrbot_plugin_cake_denia/design/render_out/preview_*.png
"""
import os
import sys

PREVIEW_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_PARENT = os.path.dirname(os.path.dirname(PREVIEW_DIR))  # 工作区根
TEST_DIR = os.path.join(PLUGIN_PARENT, 'test')

# 插件包需以 astrbot_plugin_cake_denia.<模块> 形式导入，先把父目录加入 sys.path
if PLUGIN_PARENT not in sys.path:
    sys.path.insert(0, PLUGIN_PARENT)

# 复用测试基建里的 astrbot / aiosqlite 桩，避免依赖真实运行时
if TEST_DIR not in sys.path:
    sys.path.insert(0, TEST_DIR)
import astrbot_stub  # noqa: E402
import aiosqlite_stub  # noqa: E402

astrbot_stub.install()
sys.modules['aiosqlite'] = aiosqlite_stub

from astrbot_plugin_cake_denia.preview_support import render_previews  # noqa: E402


def main():
    theme = sys.argv[1] if len(sys.argv) > 1 else 'white-1'
    backend = sys.argv[2] if len(sys.argv) > 2 else 'pil'
    out_dir = os.path.join(PREVIEW_DIR, 'render_out')
    for p in render_previews(theme, out_dir, backend):
        print(p)


if __name__ == '__main__':
    main()
