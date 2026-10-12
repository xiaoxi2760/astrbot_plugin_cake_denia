"""HTML 版排行榜渲染：HTML/CSS + Playwright + 系统 Chrome，与日历 HTML 后端一致。

复用 render_html.calendar 的浏览器单例与单线程执行器（Playwright Sync API
与 greenlet 线程绑定，必须在同一线程内使用同一 browser 实例）。

CSS 颜色统一走主题 CSS 变量（_theme_css_vars），与日历 / PIL 版视觉一致。
渲染失败由上层降级到 PIL。
"""
import html as _html
import os
import time
from datetime import date

from ..resources.texts import (
    RANKING_TITLE, RANKING_SUBTITLE, RANKING_TODAY, RANKING_MONTH,
    RANKING_COL_SELF, RANKING_COL_RECEIVED, RANKING_COL_HELP,
    RANKING_PAGE, RANKING_PAGE_LAST,
)
from . import base
from .calendar import _submit_render_task, _render_playwright  # noqa: F401  (兼容旧引用)


_CSS = '''
* { box-sizing: border-box; margin:0; padding:0; }
.scene {
  width:100%; height:100%;
  background:
    radial-gradient(ellipse at 18% 8%, var(--glow-top) 0%, rgba(255,255,255,0) 42%),
    radial-gradient(ellipse at 85% 90%, var(--glow-bottom) 0%, rgba(255,255,255,0) 45%),
    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 42%, var(--bg-bottom) 100%);
  padding: 18px 26px 14px;
  font-family: 'Microsoft YaHei','PingFang SC',sans-serif;
  color: var(--day-text);
}
.bubble {
  position:absolute; border-radius:50%;
  background: radial-gradient(circle at 30% 26%, rgba(255,255,255,.30) 0%,
              rgba(255,255,255,.10) 20%, rgba(255,255,255,0) 42%),
              radial-gradient(circle at 55% 60%, var(--fill) 0%,
              color-mix(in srgb, var(--fill), white 22%) 72%, rgba(255,255,255,.25) 100%);
  border: 1.5px solid color-mix(in srgb, var(--fill), white 40%);
  box-shadow: inset 0 0 14px rgba(255,255,255,.30), 0 3px 12px rgba(0,0,0,.10);
  animation: drift 5.5s ease-in-out infinite;
}
@keyframes drift { 0%,100%{transform:translateY(0) translateX(0)} 50%{transform:translateY(-7px) translateX(3px)} }
.card {
  position:relative; height:100%;
  background: var(--card-fill);
  border:1px solid var(--card-border); border-radius:26px;
  box-shadow: 0 14px 30px rgba(180,120,150,.18), 0 2px 6px rgba(180,120,150,.10);
  padding: 18px 20px 14px;
  display:flex; flex-direction:column;
}
.wash {
  position:absolute; top:0; left:0; right:0; height:130px; z-index:0; pointer-events:none;
  border-radius:inherit; border-bottom-left-radius:0; border-bottom-right-radius:0;
  background: linear-gradient(180deg, color-mix(in srgb, var(--feed-top), transparent 64%) 0%,
              color-mix(in srgb, var(--feed-top), transparent 100%) 100%);
}
.title { position:relative; z-index:1; text-align:center; font-size:25px; font-weight:700;
  color:var(--title); letter-spacing:1px; }
.title::before { content:'🍰 '; }
.title::after  { content:' 🍰'; }
.subtitle { position:relative; z-index:1; text-align:center; font-size:13px;
  color:var(--subtitle); margin:2px 0 8px; }
.sec { position:relative; z-index:1; text-align:center; margin: 8px 0 8px; }
.sec span {
  display:inline-block; padding:3px 24px; border-radius:999px;
  font-size:15px; font-weight:600; color:var(--weekend);
  background:linear-gradient(90deg, color-mix(in srgb, var(--feed-top), var(--card-fill) 45%),
              color-mix(in srgb, var(--feed-bottom), var(--card-fill) 68%));
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 30%);
}
.group { display:flex; gap:12px; flex:0 0 auto; margin-bottom:10px; position:relative; z-index:1; }
.col {
  flex:1 1 0; min-width:0;
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 96.5%);
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 40%);
  border-radius:16px;
  box-shadow:0 5px 14px rgba(180,120,150,.13);
  padding: 10px 10px 10px;
}
.coltitle { text-align:center; margin-bottom:6px; }
.coltitle span {
  display:inline-block; padding:2px 16px; border-radius:999px;
  font-size:14px; color:var(--subtitle);
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 72%);
}
.row { display:flex; align-items:center; gap:7px; height:42px; padding:0 3px;
  border-bottom:1px solid color-mix(in srgb, var(--empty-border), var(--card-fill) 15%); }
.row:last-child { border-bottom:0; }
.rank { width:24px; height:24px; border-radius:50%; flex:0 0 auto;
  display:inline-flex; align-items:center; justify-content:center;
  font-size:13px; font-weight:700; color:var(--subtitle); }
.rank.m1 { background:linear-gradient(160deg,#ffd56e,#eca83a); color:#fff;
  box-shadow:0 2px 5px rgba(236,168,58,.45); }
.rank.m2 { background:linear-gradient(160deg,#e4ecf5,#b0c0d2); color:#fff;
  box-shadow:0 2px 5px rgba(150,168,190,.4); }
.rank.m3 { background:linear-gradient(160deg,#f0c294,#cb8d5a); color:#fff;
  box-shadow:0 2px 5px rgba(203,141,90,.4); }
.avatar {
  width:34px; height:34px; border-radius:50%; object-fit:cover; flex:0 0 auto;
  border:2px solid rgba(255,255,255,.95); box-shadow:0 1px 4px rgba(0,0,0,.18);
  background:var(--feed-top);
}
.avatar.ph { display:flex; align-items:center; justify-content:center; font-size:13px; color:var(--subtitle); }
.name { flex:1 1 auto; min-width:0; font-size:15px; color:var(--day-text);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.badge {
  flex:0 0 auto; padding:1px 7px; border-radius:9px;
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 70%);
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 55%);
  color: var(--foot-text); font-size:12px; font-weight:600;
}
.count { flex:0 0 auto; font-size:15px; font-weight:700; color:var(--badge); min-width:26px; text-align:right; }
.empty { text-align:center; font-size:13px; color:var(--subtitle); padding:10px 0; }
.foot { text-align:center; font-size:12px; color:var(--subtitle); margin-top:10px;
        padding-bottom:6px; flex:0 0 auto; position:relative; z-index:1; }
'''


class HtmlRankingRenderer:
    """排行榜 HTML 渲染器，与 HtmlCalendarRenderer 同构。"""

    def __init__(self, core, theme=None):
        self.core = core
        self.temp_dir = core.temp_dir
        theme = theme or {}
        self._colors = theme.get('colors', {})
        self._options = theme.get('options', {})
        self._bubbles = theme.get('bubbles', [])
        self._show_bubbles = bool(self._options.get('show_bubbles', True))
        self._css_vars = self._theme_css_vars()

    def _theme_css_vars(self) -> str:
        # 复用日历渲染器的 CSS 变量映射，保证两处配色完全一致
        return base.theme_css_vars({
            'colors': self._colors, 'options': self._options})

    def _bubbles_html(self) -> str:
        parts = []
        for i, b in enumerate(self._bubbles):
            left = int(b.get('left', 0)); top = int(b.get('top', 0))
            size = int(b.get('size', 20)); opacity = float(b.get('opacity', 0.8))
            fill = b.get('fill', '#f48fb1'); delay = (i * 0.4) % 3
            parts.append(
                f'<div class="bubble" style="left:{left}px;top:{top}px;width:{size}px;'
                f'height:{size}px;opacity:{opacity};--fill:{fill};'
                f'animation-delay:{delay}s"></div>')
        return '\n'.join(parts)

    def _col_html(self, title, rows, max_rows):
        out = [f'<div class="col"><div class="coltitle"><span>'
               f'{_html.escape(title)}</span></div>']
        if not rows:
            out.append('<div class="empty">今天还没有人投喂哦</div>')
        for row in rows[:max_rows]:
            if not row or len(row) < 4:
                continue
            _rank, uid, nickname, count = row[0], row[1], row[2], row[3]
            ach = row[4] if len(row) > 4 else 0
            medal = f' m{_rank}' if _rank in (1, 2, 3) else ''
            out.append('<div class="row">')
            out.append(f'<span class="rank{medal}">{_html.escape(str(_rank))}</span>')
            out.append(self._avatar_html(uid))
            out.append(f'<span class="name">{_html.escape(str(nickname))}</span>')
            if ach > 0:
                out.append(f'<span class="badge">x{_html.escape(str(ach))}</span>')
            out.append(f'<span class="count">{_html.escape(str(count))}</span>')
            out.append('</div>')
        out.append('</div>')
        return '\n'.join(out)

    def _avatar_html(self, uid):
        if uid:
            path = os.path.join(self.core.avatar_cache_dir, f'{uid}.png')
            if os.path.exists(path):
                from pathlib import Path
                uri = Path(path).resolve().as_uri()
                return f'<img class="avatar" src="{uri}" alt="">'
        return '<div class="avatar ph">🍰</div>'

    def _page_html(self, groups, page, total_pages, year, month):
        body = []
        if self._show_bubbles:
            body.append(self._bubbles_html())
        body.append('<div class="card">')
        body.append('<div class="wash"></div>')
        body.append(f'<div class="title">{_html.escape(RANKING_TITLE.format(year=year, month=month))}</div>')
        body.append(f'<div class="subtitle">{_html.escape(RANKING_SUBTITLE)}</div>')
        for sec_title, cols in groups:
            body.append(f'<div class="sec"><span>{_html.escape(sec_title)}</span></div>')
            body.append('<div class="group">')
            for col_title, rows, max_rows in cols:
                body.append(self._col_html(col_title, rows, max_rows))
            body.append('</div>')
        foot = (RANKING_PAGE.format(page=page, total=total_pages, next=page + 1)
                if page < total_pages
                else RANKING_PAGE_LAST.format(page=page, total=total_pages))
        body.append(f'<div class="foot">{_html.escape(foot)}</div>')
        body.append('</div>')
        return (
            '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            '<style>html,body{width:900px;overflow:hidden}'
            'body{position:relative}'
            f'{self._css_vars}{_CSS}</style></head><body>'
            f'<div class="scene">{"".join(body)}</div></body></html>'
        )

    def render(self, today_self, today_received, today_helped,
               month_self, month_received, month_helped,
               year, month, page, total_pages, system_name='\U0001F370',
               avatar_dir=None, ach_map=None, max_rows=10):
        ach_map = ach_map or {}
        MAX_ROWS = max(int(max_rows), 1)

        def cap(data):
            return list(data)[:MAX_ROWS] if data else []

        today_sets = [cap(today_self), cap(today_received), cap(today_helped)]
        month_sets = [cap(month_self), cap(month_received), cap(month_helped)]
        today_h = max([len(s) for s in today_sets] + [1])
        month_h = max([len(s) for s in month_sets] + [1])

        cols_titles = [RANKING_COL_SELF, RANKING_COL_RECEIVED, RANKING_COL_HELP]
        groups = [
            (RANKING_TODAY, [(cols_titles[i], today_sets[i], today_h) for i in range(3)]),
            (RANKING_MONTH, [(cols_titles[i], month_sets[i], month_h) for i in range(3)]),
        ]

        # 高度：与 PIL 版一致（按各组实际行数）+ 页脚留白
        SEC_H, COL_HEAD, PAD, ROW_H = 34, 28, 18, 42
        group_h = SEC_H + COL_HEAD + today_h * ROW_H + PAD
        group_h2 = SEC_H + COL_HEAD + month_h * ROW_H + PAD
        H = 18 + 44 + 22 + group_h + 10 + group_h2 + 46
        W = 900

        ts = int(time.time())
        html_path = os.path.join(self.temp_dir, f"rank_{page}_{ts}.html")
        out_png = os.path.join(self.temp_dir, f"rank_{page}_{ts}.png")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(self._page_html(groups, page, total_pages, year, month))
        try:
            base.submit_shot_auto(html_path, out_png, W, H)
            return out_png
        finally:
            try:
                if os.path.exists(html_path):
                    os.remove(html_path)
            except Exception:
                pass
