"""HTML 版日历渲染：HTML/CSS + Playwright + 系统 Chrome，与设计稿 A1 一致。

配色、泡泡、光晕与开关由主题驱动：预设见 resources/themes/（娅娅/达妮娅），
用户自定义见 resources/theme.json。
依赖：playwright（pip 安装）+ 系统 Chrome（channel='chrome'，失败回退捆绑 chromium）。
渲染失败由上层降级到 PIL。
"""
import calendar
import concurrent.futures
import html
import os
import threading
import time
from datetime import date
from pathlib import Path

from ..resources.texts import CALENDAR_SUMMARY

# ---------------------------------------------------------------- 浏览器复用
# Playwright Sync API 与 greenlet 线程绑定：asyncio.to_thread 的线程池可能把同一
# browser 实例交给不同线程复用 → "无法切换到不同的线程"。这里把所有 Playwright 渲染
# 汇聚到单线程执行器，保证浏览器实例始终被同一线程访问，复用提速与线程安全兼得。
_RENDER_EXECUTOR = None
_render_executor_lock = threading.Lock()
_render_lock = threading.Lock()
_browser = None
_playwright = None


def _get_render_executor():
    """返回渲染专用单线程执行器；被 shutdown（插件停用/热重载）后惰性重建。"""
    global _RENDER_EXECUTOR
    with _render_executor_lock:
        if _RENDER_EXECUTOR is None or getattr(_RENDER_EXECUTOR, '_shutdown', False):
            _RENDER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix='cake-html-render')
        return _RENDER_EXECUTOR


def _submit_render_task(fn, *args):
    """把 Playwright 任务提交到单线程执行器（若执行器已被 shutdown 则先重建）。"""
    try:
        return _get_render_executor().submit(fn, *args)
    except RuntimeError:
        with _render_executor_lock:
            _RENDER_EXECUTOR = None
        return _get_render_executor().submit(fn, *args)


def _close_browser():
    global _browser, _playwright
    with _render_lock:
        if _browser is not None:
            try:
                _browser.close()
            except Exception:
                pass
            _browser = None
        if _playwright is not None:
            try:
                _playwright.stop()
            except Exception:
                pass
            _playwright = None


def _get_browser(launch_args):
    """返回可用的浏览器实例；调用方必须持有 _render_lock。"""
    global _browser, _playwright
    if _browser is not None:
        try:
            if _browser.is_connected():
                return _browser
        except Exception:
            pass
        _browser = None
    if _playwright is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
    try:
        _browser = _playwright.chromium.launch(channel='chrome', args=launch_args)
    except Exception:
        _browser = _playwright.chromium.launch(args=launch_args)
    return _browser


def _render_playwright(launch_args, html_path, out_png):
    """在单线程执行器内执行截图（必须在 _RENDER_EXECUTOR 线程调用）。"""
    with _render_lock:
        browser = _get_browser(launch_args)
        page = browser.new_page(viewport={'width': 600, 'height': 540},
                                device_scale_factor=2)
        try:
            page.goto(Path(html_path).resolve().as_uri())
            page.wait_for_timeout(300)
            page.screenshot(path=out_png)
        finally:
            page.close()
    return out_png


def _shutdown_html_renderer():
    """插件卸载时回收浏览器并关闭渲染线程；之后再次渲染会惰性重建执行器。"""
    global _RENDER_EXECUTOR
    with _render_executor_lock:
        ex = _RENDER_EXECUTOR
    if ex is not None:
        try:
            ex.submit(_close_browser).result(timeout=30)
        except Exception:
            pass
        try:
            ex.shutdown(wait=True)
        except Exception:
            pass
    with _render_executor_lock:
        _RENDER_EXECUTOR = None

# ---------------------------------------------------------------- CSS（颜色走 CSS 变量）
_CSS = '''
@keyframes floaty {
  0%,100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-5px) rotate(2deg); }
}
@keyframes bubbleDrift {
  0%,100% { transform: translateY(0) translateX(0); }
  50% { transform: translateY(-7px) translateX(3px); }
}
.scene {
  width: 100%; height: 100%;
  background:
    radial-gradient(ellipse at 18% 8%, var(--glow-top) 0%, rgba(255,255,255,0) 42%),
    radial-gradient(ellipse at 85% 90%, var(--glow-bottom) 0%, rgba(255,255,255,0) 45%),
    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 42%, var(--bg-bottom) 100%);
  padding: 16px 26px 14px;
  position: relative;
}
.bubble {
  position: absolute; border-radius: 50%;
  background:
    radial-gradient(circle at 30% 26%, rgba(255,255,255,.30) 0%, rgba(255,255,255,.10) 20%, rgba(255,255,255,0) 42%),
    radial-gradient(circle at 55% 60%, var(--fill) 0%, color-mix(in srgb, var(--fill), white 22%) 72%, rgba(255,255,255,.25) 100%);
  border: 1.5px solid color-mix(in srgb, var(--fill), white 40%);
  box-shadow:
    inset 0 0 14px rgba(255,255,255,.30),
    inset -4px -4px 10px rgba(0,0,0,.18),
    0 3px 12px color-mix(in srgb, var(--fill), transparent 45%);
  animation: bubbleDrift 5.5s ease-in-out infinite;
}
.bubble::after {
  content: ''; position: absolute; left: 26%; top: 20%;
  width: 26%; height: 17%;
  border-radius: 50%;
  background: rgba(255,255,255,.75);
  transform: rotate(-28deg);
  filter: blur(0.5px);
}
.bubble::before {
  content: ''; position: absolute; right: 18%; bottom: 22%;
  width: 12%; height: 12%;
  border-radius: 50%;
  background: rgba(255,255,255,.45);
}
.avatar {
  position: absolute; z-index: 3;
  left: 35px; top: 25px;
  width: 56px; height: 56px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid rgba(255,255,255,.95);
  box-shadow: 0 2px 8px rgba(0,0,0,.30);
}
.card {
  position: relative; z-index: 2;
  height: 100%;
  display: flex; flex-direction: column;
  background: var(--card-fill);
  border: 1px solid var(--card-border); border-radius: 26px;
  box-shadow: 0 14px 30px rgba(0,0,0,.25), 0 2px 6px rgba(0,0,0,.12);
  padding: 20px 20px 16px;
}
.title { text-align:center; font-size: 25px; font-weight: 700; color: var(--title); letter-spacing: 1px; }
.title::before { content:'🍰 '; }
.title::after { content:' 🍰'; }
.subtitle { text-align:center; font-size: 14px; color: var(--subtitle); margin: 2px 0 12px; }
.weekbar { display: grid; grid-template-columns: repeat(7,1fr); text-align:center; font-size:14px; color: var(--weekday); margin-bottom:6px; }
.weekbar span:nth-child(n+6) { color: var(--weekend); font-weight:600; }
.grid { flex:1; display:flex; flex-direction:column; gap:6px; }
.week { flex:1; display:grid; grid-template-columns: repeat(7,1fr); gap:6px; }
.day {
  position: relative; border-radius: 10px; background: var(--empty-bg);
  border: 1px solid var(--empty-border); display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:1px; padding-top:2px;
}
.day .num { font-size: 16px; color: var(--day-text); font-weight: 600; }
.day.feed {
  background: linear-gradient(180deg, var(--feed-top) 0%, var(--feed-bottom) 100%);
  border: 1px solid var(--feed-border);
}
.day.feed.today { border: 2px solid var(--weekend); }
.day.today:not(.feed) { background: var(--today-bg); border: 2px solid var(--weekend); }
.day.feed .cake { font-size: 17px; line-height: 1; animation: floaty 3s ease-in-out infinite; }
.day .badge {
  position:absolute; top:3px; right:4px; min-width:17px; height:17px; padding:0 3px;
  border-radius: 9px; background: var(--badge); color:#fff; font-size:11px; font-weight:700;
  display:flex; align-items:center; justify-content:center; line-height:1;
}
.foot {
  margin: 12px auto 0; padding: 7px 24px; border-radius: 14px;
  background: linear-gradient(90deg, var(--foot-top), var(--foot-bottom)); color: var(--foot-text);
  font-size: 16px; font-weight: 600; text-align:center;
}
'''

WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']


class HtmlCalendarRenderer:

    def __init__(self, core, theme=None):
        self.core = core
        self.temp_dir = core.temp_dir
        theme = theme or {}
        self._colors = theme.get('colors', {})
        self._options = theme.get('options', {})
        self._bubbles = theme.get('bubbles', [])
        self._show_avatar = bool(self._options.get('show_avatar', True))
        self._show_bubbles = bool(self._options.get('show_bubbles', True))
        self._css_vars = self._theme_css_vars()

    def _theme_css_vars(self) -> str:
        c = self._colors
        defs = {
            'glow-top': c.get('glow_top', 'rgba(255,255,255,0.9)'),
            'glow-bottom': c.get('glow_bottom', 'rgba(255,214,234,0.8)'),
            'bg-top': c.get('bg_top', '#fff6fb'),
            'bg-mid': c.get('bg_mid', '#ffeef4'),
            'bg-bottom': c.get('bg_bottom', '#ffe4ef'),
            'card-fill': c.get('card_fill', 'rgba(255,255,255,0.94)'),
            'card-border': c.get('card_border', '#f3d6e4'),
            'title': c.get('title', '#65432a'),
            'subtitle': c.get('subtitle', '#b2909e'),
            'weekday': c.get('weekday', '#b08a98'),
            'weekend': c.get('weekend', '#db7093'),
            'day-text': c.get('day_text', '#5a464f'),
            'empty-bg': c.get('empty_bg', '#fcf9fa'),
            'empty-border': c.get('empty_border', '#f0e8ec'),
            'feed-top': c.get('feed_top', '#ffdcec'),
            'feed-bottom': c.get('feed_bottom', '#ffc8dd'),
            'feed-border': c.get('feed_border', '#f6b6cf'),
            'today-bg': c.get('today_bg', '#fff0f6'),
            'badge': c.get('badge', '#e9546b'),
            'foot-top': c.get('foot_top', '#ffe3ee'),
            'foot-bottom': c.get('foot_bottom', '#ffd0e2'),
            'foot-text': c.get('foot_text', '#d84762'),
        }
        return ':root{' + ';'.join(f'--{k}:{v}' for k, v in defs.items()) + ';}'

    def _bubbles_html(self):
        parts = []
        for i, b in enumerate(self._bubbles):
            left = int(b.get('left', 0))
            top = int(b.get('top', 0))
            size = int(b.get('size', 20))
            opacity = float(b.get('opacity', 0.8))
            fill = b.get('fill', '#f48fb1')
            delay = (i * 0.4) % 3
            parts.append(
                f'<div class="bubble" style="left:{left}px;top:{top}px;'
                f'width:{size}px;height:{size}px;opacity:{opacity};'
                f'--fill:{fill};animation-delay:{delay}s"></div>')
        return '\n'.join(parts)

    def _page_html(self, user_name, year, month, checkin_data, total_cakes, today, avatar_path):
        bubbles = self._bubbles_html() if self._show_bubbles else ''
        avatar = self._avatar_html(avatar_path) if self._show_avatar else ''
        cells = self._cells_html(year, month, checkin_data, today)
        return f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }}
html, body {{ width: 600px; height: 540px; overflow: hidden; }}
body {{ position: relative; }}
{self._css_vars}
{_CSS}
</style></head><body>
<div class="scene">
  {bubbles}
  {avatar}
  <div class="card">
    <div class="title">{html.escape(user_name)}的投喂日历</div>
    <div class="subtitle">{year}年{month}月</div>
    <div class="weekbar">{''.join(f'<span>{d}</span>' for d in WEEKDAYS)}</div>
    <div class="grid">{cells}</div>
    <div class="foot">{CALENDAR_SUMMARY.format(days=len(checkin_data), cakes=total_cakes)}</div>
  </div>
</div>
</body></html>'''

    @staticmethod
    def _avatar_html(avatar_path):
        if not avatar_path or not os.path.exists(avatar_path):
            return ''
        uri = Path(avatar_path).resolve().as_uri()
        return f'<img class="avatar" src="{uri}" alt="">'

    @staticmethod
    def _cells_html(year, month, checkin_data, today):
        cal = calendar.monthcalendar(year, month)
        rows = []
        for week in cal:
            cells = []
            for day in week:
                if day == 0:
                    cells.append('<div class="day empty"></div>')
                    continue
                cls = 'day'
                if day in checkin_data:
                    cls += ' feed'
                if day == today:
                    cls += ' today'
                badge = (f'<span class="badge">{checkin_data[day]}</span>'
                         if checkin_data.get(day, 0) > 1 else '')
                cake = '<div class="cake">🍰</div>' if day in checkin_data else ''
                cells.append(
                    f'<div class="{cls}"><span class="num">{day}</span>{cake}{badge}</div>')
            rows.append('<div class="week">' + ''.join(cells) + '</div>')
        return '\n'.join(rows)

    def render(self, user_id, user_name, year, month, checkin_data, total_cakes,
               avatar_path=None, today=None):
        if today is None:
            today = date.today().day if (date.today().year == year and date.today().month == month) else 0
        ts = int(time.time())
        html_path = os.path.join(self.temp_dir, f"cake_{user_id}_{ts}.html")
        out_png = os.path.join(self.temp_dir, f"cake_{user_id}_{ts}.png")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(self._page_html(user_name, year, month, checkin_data, total_cakes,
                                    today, avatar_path))
        # 容器内以 root 运行时 Chromium 需 --no-sandbox；非 root 环境（本机/普通用户）不加
        is_root = getattr(os, 'geteuid', lambda: 1)() == 0
        launch_args = ['--no-sandbox'] if is_root else []
        try:
            _submit_render_task(
                _render_playwright, launch_args, html_path, out_png).result(timeout=120)
            return out_png
        except Exception:
            # 浏览器可能已崩溃，重置以便下次重建（在渲染线程内执行，避免跨线程）
            try:
                _submit_render_task(_close_browser).result(timeout=30)
            except Exception:
                pass
            raise
        finally:
            try:
                if os.path.exists(html_path):
                    os.remove(html_path)
            except Exception:
                pass
