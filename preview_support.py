"""预览支撑：用样例数据驱动报告/生涯/排行榜三张图的渲染，供设计改版时肉眼比对。

不依赖 AstrBot 运行时（只用 Pillow），改完 cake_core 的渲染函数后
直接运行 design/preview_other.py 即可看到新效果。
"""
import os
import tempfile
import types

from PIL import Image, ImageDraw

from .theme import load_theme
from .render_common import ThemePalette
from .resources import texts


def _make_core(theme_preset, temp_dir, backend='pil'):
    """构造一个只保留渲染所需能力的 CakeCore 替身（绕开 AstrBot / 数据库依赖）。

    自动把 CakeCore 的所有方法绑定过来，新增辅助函数无需再手动登记。
    backend='html' 时接入 HTML 渲染器（Playwright + 系统 Chrome）。
    """
    import inspect
    from . import cake_core
    raw_theme = load_theme(theme_preset)
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    core = types.SimpleNamespace()
    core.theme = raw_theme
    core.palette = ThemePalette(raw_theme)
    core.temp_dir = temp_dir
    # 预览直接用插件自带字体（正式运行时由 CakeCore._init_fonts 解析）
    font_path = os.path.join(plugin_dir, 'resources', 'fonts', 'font.ttf')
    core.font_path = font_path if os.path.exists(font_path) else None
    core._emoji_font = None
    core._emoji_path = None
    # 预览也走系统 emoji 字体候选，保证 🍰 等图标与线上渲染一致
    for ep in (os.path.join(plugin_dir, 'resources', 'fonts', 'emoji.ttf'),
               os.path.join(plugin_dir, 'emoji.ttf'),
               'C:/Windows/Fonts/seguiemj.ttf',
               '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'):
        if ep and os.path.exists(ep):
            core._emoji_path = ep
            break
    core._plugin_dir = plugin_dir
    core.texts = texts

    cls = cake_core.CakeCore
    for name in dir(cls):
        raw = inspect.getattr_static(cls, name)
        if isinstance(raw, staticmethod):
            setattr(core, name, raw.__func__)
        elif inspect.isfunction(raw):
            setattr(core, name, raw.__get__(core, cls))

    # HTML 后端（四类图共用 calendar 模块的浏览器单例）
    if backend == 'html':
        from .render_html.ranking import HtmlRankingRenderer
        from .render_html.analysis import HtmlAnalysisRenderer
        from .render_html.career import HtmlCareerRenderer
        core._html_renderers = {
            'ranking': HtmlRankingRenderer(core, raw_theme),
            'analysis': HtmlAnalysisRenderer(core, raw_theme),
            'career': HtmlCareerRenderer(core, raw_theme),
        }
    else:
        core._html_renderers = {}
    core.render_backend = 'html' if backend == 'html' else 'pil'
    core._get_html_renderer = lambda kind: (core._html_renderers or {}).get(kind)
    core._close_html_browser_on_error = lambda: None
    return core


def _fake_avatar(path, color=(240, 150, 180)):
    img = Image.new('RGB', (160, 160), color)
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 140, 140), fill=(255, 255, 255))
    img.save(path)
    return path


def _export(src, dst):
    """把渲染产物复制到目标路径（临时目录与输出目录可能跨盘，不能用 os.replace）。"""
    import shutil
    shutil.copyfile(src, dst)
    return dst


def render_previews(theme_preset, out_dir, backend='pil'):
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='cake_preview_')
    core = _make_core(theme_preset, tmp, backend)
    suffix = '' if backend == 'pil' else '_html'
    t = texts
    out = []

    # ---- 报告图 ----
    report = (
        f"{t.MONTHLY_TOP.format(total_days=18, total_cakes=46)}\n"
        f"{t.MONTHLY_PEAK_GE3.format(day=17, count=5)}\n"
        f"{t.MONTHLY_STREAK_GE7.format(n=9)}\n"
        f"{t.MONTHLY_RATE.format(rate='60.0%')}\n\n"
        f"{t.MONTHLY_YAYA_GE07}{t.MONTHLY_TIP}"
    )
    p = core._create_analysis_image('小明', '2026年10月', report, 0.6, "蛋糕")
    dst = os.path.join(out_dir, f'preview_报告{suffix}_{theme_preset}.png')
    _export(p, dst)
    out.append(dst)

    # ---- 生涯图 ----
    stats = {
        'summary_comment': '娅娅的好朋友',
        'first_date_str': '2026-03-14', 'total_span_days': 216,
        'total_count': 128, 'total_days': 96, 'active_ratio': 44.4,
        'daily_avg': 0.59,
        'max_day_count': 5, 'max_day_date': '2026-09-17',
        'max_month_count': 46, 'max_month_str': '2026-10',
        'min_month_count': 3, 'min_month_str': '2026-04',
        'rest_period_str': t.CAREER_REST_GAP.format(start='2026-06-02', days=11),
        'sage_comment': t.CAREER_SAGE_LOW,
        'status_day': 2,
        'status_comment': t.CAREER_STATUS_LE3.format(days=2),
    }
    p = core._create_career_image('小明', stats, "娅娅")
    dst = os.path.join(out_dir, f'preview_生涯{suffix}_{theme_preset}.png')
    _export(p, dst)
    out.append(dst)

    # ---- 排行榜图 ----
    names = ['小明', '夜见', '星河', '泡泡', '白露', '洛雪', '深空', '拾光',
             '晚风', '浮黎', '羽', '司夏', '流萤', '铃兰']
    # 成就数：制造有/无/多为三种情况，便于肉眼验证徽章渲染
    ach = {f'u{i}': (i % 5) for i in range(14)}

    def rank(pairs, offset=0):
        # 模拟 main.py 的 enrich：为每行追加 ach_map 值
        return [(i + 1, f'u{offset + i}', n, c, ach.get(f'u{offset + i}', 0))
                for i, (n, c) in enumerate(pairs)]

    today_self = rank(list(zip(names[:6], [5, 4, 3, 3, 2, 1])))
    today_recv = rank(list(zip(names[6:12], [7, 3, 2, 2, 1, 1])), 6)
    today_help = rank(list(zip(names[3:9], [4, 4, 3, 2, 2, 1])), 3)
    month_self = rank(list(zip(names[:10], [46, 38, 33, 29, 25, 22, 19, 17, 14, 11])))
    month_recv = rank(list(zip(names[4:14], [62, 51, 44, 40, 33, 28, 24, 20, 17, 13])), 4)
    month_help = rank(list(zip(names[2:12], [31, 27, 24, 20, 18, 15, 12, 10, 8, 6])), 2)

    av_dir = os.path.join(tmp, 'avatars')
    os.makedirs(av_dir, exist_ok=True)
    for i in range(14):
        _fake_avatar(os.path.join(av_dir, f'u{i}.png'),
                     (230, 160 + i * 5 % 80, 180 + i * 7 % 60))
    # HTML 渲染器通过 core.avatar_cache_dir 定位头像
    core.avatar_cache_dir = av_dir

    p = core._create_three_column_ranking_image(
        today_self, today_recv, today_help,
        month_self, month_recv, month_help,
        2026, 10, 1, 2, "🍰", av_dir, ach, max_rows=10)
    dst = os.path.join(out_dir, f'preview_排行榜{suffix}_{theme_preset}.png')
    _export(p, dst)
    out.append(dst)

    return out


if __name__ == '__main__':
    _here = os.path.dirname(os.path.abspath(__file__))
    for f in render_previews('white-1', os.path.join(_here, 'design', 'render_out')):
        print(f)
