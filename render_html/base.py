"""HTML 渲染公共基元：截图执行、CSS 变量、主题场景样式。

三个 HTML 渲染器（calendar / ranking / analysis / career）共用：
- 浏览器单例与单线程执行器（在 calendar 模块中维护，这里只做转发）
- 主题 CSS 变量
- 背景光晕/泡泡/玻璃卡片的 CSS

设计约束（来自 calendar 模块的注释）：Playwright Sync API 与 greenlet 线程绑定，
必须把所有渲染汇聚到单线程执行器，否则同一 browser 实例跨线程复用会报
「无法切换到不同的线程」。
"""
import os
from pathlib import Path

from .calendar import _submit_render_task, _render_lock, _get_browser


def shot(html_path, out_png, width, height, scale=2, timeout_launch_args=None):
    """把 HTML 文件截图为 PNG。

    必须在 _submit_render_task 的单线程执行器内执行（内部已带线程锁）。
    """
    args = timeout_launch_args if timeout_launch_args is not None else (
        ['--no-sandbox'] if getattr(os, 'geteuid', lambda: 1)() == 0 else [])
    with _render_lock:
        browser = _get_browser(args)
        page = browser.new_page(viewport={'width': width, 'height': height},
                                device_scale_factor=scale)
        try:
            page.goto(Path(html_path).resolve().as_uri())
            page.wait_for_timeout(300)
            page.screenshot(path=out_png)
        finally:
            page.close()
    return out_png


def submit_shot(html_path, out_png, width, height, scale=2, timeout=120):
    """提交截图任务到单线程执行器并等待结果。"""
    args = ['--no-sandbox'] if getattr(os, 'geteuid', lambda: 1)() == 0 else []
    return _submit_render_task(
        shot, args, html_path, out_png, width, height, scale).result(timeout=timeout)


def shot_auto(html_path, out_png, width, min_height=0, scale=2):
    """截图并按实际内容高度自适应（读取 .scene 的真实高度，避免估算不足被裁切）。

    注意：不能读 body.scrollHeight —— html/body 被 CSS 固定为 min_height，
    量到的会是视口高度而非内容高度，导致图被拉伸出大片空白。

    必须在 _submit_render_task 的单线程执行器内执行（内部已带线程锁）。
    """
    args = ['--no-sandbox'] if getattr(os, 'geteuid', lambda: 1)() == 0 else []
    with _render_lock:
        browser = _get_browser(args)
        # 先用较大高度打开，量出真实内容高，再按真实高度重截
        probe_h = max(int(min_height) * 3, int(min_height) + 2000)
        page = browser.new_page(viewport={'width': width, 'height': probe_h},
                                device_scale_factor=scale)
        try:
            page.goto(Path(html_path).resolve().as_uri())
            page.wait_for_timeout(300)
            # 量 .card（真实内容容器）的高度：它由内容撑开，不受视口影响
            actual = page.evaluate(
                "() => { const c = document.querySelector('.card');"
                " return c ? Math.ceil(c.getBoundingClientRect().height) : 0; }")
            if not actual:
                actual = page.evaluate(
                    "() => { const s = document.querySelector('.scene');"
                    " return s ? Math.ceil(s.scrollHeight) : 0; }")
            height = max(int(actual or 0), int(min_height))
            if height != probe_h:
                page.set_viewport_size({'width': width, 'height': height})
                page.wait_for_timeout(120)
            page.screenshot(path=out_png)
        finally:
            page.close()
    return out_png


def submit_shot_auto(html_path, out_png, width, min_height=0, scale=2, timeout=120):
    """提交自适应高度截图任务到单线程执行器并等待结果。"""
    return _submit_render_task(
        shot_auto, html_path, out_png, width, min_height, scale).result(timeout=timeout)


def theme_css_vars(theme):
    """从主题 dict 生成 CSS 变量块（与日历渲染器共用同一映射）。"""
    from .calendar import HtmlCalendarRenderer

    theme = theme or {}

    class _Stub:
        # HtmlCalendarRenderer.__init__ 需要 core.temp_dir；仅调用 CSS 变量方法
        temp_dir = '.'

    # 主题必须作为第二个参数传入，否则渲染器会退化为空主题默认值
    return HtmlCalendarRenderer(_Stub(), theme)._theme_css_vars()


# ---------------------------------------------------------------- 共用 CSS
BASE_CSS = '''
* { box-sizing: border-box; margin:0; padding:0; }
body { position:relative; font-family:'Microsoft YaHei','PingFang SC',sans-serif; }
.scene {
  width:100%;
  background:
    radial-gradient(ellipse at 18% 8%, var(--glow-top) 0%, rgba(255,255,255,0) 42%),
    radial-gradient(ellipse at 85% 90%, var(--glow-bottom) 0%, rgba(255,255,255,0) 45%),
    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 42%, var(--bg-bottom) 100%);
}
.bubble {
  position:absolute; border-radius:50%;
  background:
    radial-gradient(circle at 30% 26%, rgba(255,255,255,.30) 0%, rgba(255,255,255,.10) 20%, rgba(255,255,255,0) 42%),
    radial-gradient(circle at 55% 60%, var(--fill) 0%, color-mix(in srgb, var(--fill), white 22%) 72%, rgba(255,255,255,.25) 100%);
  border:1.5px solid color-mix(in srgb, var(--fill), white 40%);
  box-shadow: inset 0 0 14px rgba(255,255,255,.30), inset -4px -4px 10px rgba(0,0,0,.12),
              0 3px 12px color-mix(in srgb, var(--fill), transparent 45%);
  animation: drift 5.5s ease-in-out infinite;
}
@keyframes drift { 0%,100%{transform:translateY(0) translateX(0)} 50%{transform:translateY(-7px) translateX(3px)} }
.card {
  position:relative; z-index:2;
  background: var(--card-fill);
  border:1px solid var(--card-border); border-radius:26px;
  box-shadow: 0 14px 30px rgba(180,120,150,.18), 0 2px 6px rgba(180,120,150,.10);
  padding:20px 22px 16px;
  display:flex; flex-direction:column;
}
.wash {
  position:absolute; top:0; left:0; right:0; height:120px; z-index:0; pointer-events:none;
  border-radius:inherit; border-bottom-left-radius:0; border-bottom-right-radius:0;
  background: linear-gradient(180deg, color-mix(in srgb, var(--feed-top), transparent 62%) 0%,
              color-mix(in srgb, var(--feed-top), transparent 100%) 100%);
}
.num { color: var(--foot-text); font-weight:700; }
.panel {
  background: rgba(255,255,255,.86);
  border:1px solid var(--empty-border); border-radius:16px;
  box-shadow: 0 4px 12px rgba(180,120,150,.10);
}
.avatar {
  width:34px; height:34px; border-radius:50%; object-fit:cover; flex:0 0 auto;
  border:2px solid rgba(255,255,255,.95); box-shadow:0 1px 4px rgba(0,0,0,.25);
  background:var(--feed-top);
}
.avatar.ph { display:flex; align-items:center; justify-content:center; font-size:13px; color:var(--subtitle); }
'''


def bubbles_html(bubbles, enabled=True):
    if not enabled:
        return ''
    parts = []
    for i, b in enumerate(bubbles):
        left = int(b.get('left', 0)); top = int(b.get('top', 0))
        size = int(b.get('size', 20)); opacity = float(b.get('opacity', 0.8))
        fill = b.get('fill', '#f48fb1'); delay = (i * 0.4) % 3
        parts.append(
            f'<div class="bubble" style="left:{left}px;top:{top}px;width:{size}px;'
            f'height:{size}px;opacity:{opacity};--fill:{fill};'
            f'animation-delay:{delay}s"></div>')
    return '\n'.join(parts)


def page_html(inner, width, height, css_vars, bubbles, extra_css=''):
    """组装完整 HTML 文档。

    html/body 不设固定高度，让 .card 由内容撑开，截图时按实测高度裁切
    （见 shot_auto）。width 固定以保证排版宽度稳定。
    extra_css 为各渲染器私有样式（追加在 BASE_CSS 之后，可覆盖）。
    """
    return (
        '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><style>'
        f'html,body{{width:{width}px;overflow:hidden;margin:0;padding:0}}'
        f'{css_vars}{BASE_CSS}{extra_css}</style></head><body>'
        f'<div class="scene">{bubbles}{inner}</div></body></html>'
    )


def avatar_img_html(path, cls='avatar'):
    """本地头像转 file:// URI；缺失返回空串。"""
    if path and os.path.exists(path):
        return f'<img class="{cls}" src="{Path(path).resolve().as_uri()}" alt="">'
    return ''
