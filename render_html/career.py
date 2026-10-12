"""HTML 版生涯档案：顶部指标三宫格 + 五个分区卡片。

长句由浏览器自动换行，天然不会出现 PIL 版的溢出截断问题。
"""
import html as _html
import os
import re
import time

from ..resources.texts import (
    CAREER_TITLE, CAREER_FEEDER, CAREER_QUOTE, CAREER_SECTIONS, CAREER_FIRST,
    CAREER_AVG_DAILY, CAREER_AVG_INTERVAL, CAREER_AVG_ZERO, CAREER_TOTAL,
    CAREER_DAYS, CAREER_MAX_DAY, CAREER_MAX_MONTH, CAREER_MIN_MONTH, CAREER_REST,
    CAREER_STATUS, CAREER_COMMENT_WRAP,
)
from . import base

_NUM_RE = re.compile(r'(\d[\d.,:%]*(?:\.\d+)?%?)')

_CSS = '''
.pad { position:relative; z-index:1; padding:18px 26px 16px; }
.title { text-align:center; font-size:34px; font-weight:700; color:var(--title); }
.subtitle { text-align:center; font-size:17px; color:var(--subtitle); margin-top:4px; }
.quotewrap { text-align:center; margin-top:8px; }
.quote {
  display:inline-block; padding:5px 22px; font-size:20px; font-weight:600;
  color:var(--weekend);
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 62%);
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 35%);
  border-radius:999px;
}
.kpis { display:flex; gap:14px; margin:16px 0 6px; }
.kpi {
  flex:1 1 0; text-align:center; padding:14px 0;
  background:linear-gradient(180deg, color-mix(in srgb, var(--feed-top), var(--card-fill) 55%),
              color-mix(in srgb, var(--feed-bottom), var(--card-fill) 75%));
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 40%);
  border-radius:18px;
  box-shadow:0 4px 10px rgba(180,120,150,.14);
}
.kpi .num { font-size:32px; font-weight:700; color:var(--foot-text); line-height:1.1; }
.kpi .cap { font-size:14px; color:var(--subtitle); margin-top:3px; }
.sections { margin-top:6px; }
.sec {
  position:relative; margin:12px 0; padding:12px 16px 13px 20px;
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 93%);
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 35%);
  border-radius:18px;
  box-shadow:0 4px 10px rgba(180,120,150,.10);
}
.sec h3 {
  display:flex; align-items:center; gap:9px;
  font-size:20px; font-weight:600; color:var(--weekend);
  border-bottom:1px solid color-mix(in srgb, var(--empty-border), var(--card-fill) 20%);
  padding-bottom:9px; margin-bottom:9px;
}
.sec h3::before {
  content:''; width:15px; height:15px; border-radius:6px; flex:0 0 auto;
  background:linear-gradient(160deg, var(--feed-top), var(--feed-bottom));
}
.sec .row { display:flex; font-size:18px; line-height:30px; }
.sec .lab { flex:0 0 auto; color:var(--subtitle); }
.sec .val { color:var(--day-text); }
.sec .plain { font-size:18px; color:var(--day-text); line-height:30px; }
.sec .note { font-size:15px; color:var(--subtitle); line-height:24px; }
'''


def _rich(text):
    """转义并把数字段包上 <span class="num"> 高亮。"""
    return _NUM_RE.sub(r'<span class="num">\1</span>', _html.escape(text))


class HtmlCareerRenderer:

    def __init__(self, core, theme=None):
        self.core = core
        self.temp_dir = core.temp_dir
        theme = theme or {}
        self._bubbles = theme.get('bubbles', [])
        self._options = theme.get('options', {})
        self._show_bubbles = bool(self._options.get('show_bubbles', True))
        self._css_vars = base.theme_css_vars(theme)

    @staticmethod
    def _sections(stats):
        """与 PIL 版口径一致：返回 [(标题, [(文本, 是否注释)])]。"""
        avg = (CAREER_AVG_DAILY.format(avg=f"{stats['daily_avg']:.2f}")
               if stats['daily_avg'] > 1 else
               CAREER_AVG_INTERVAL.format(interval=f"{1 / stats['daily_avg']:.1f}")
               if stats['daily_avg'] > 0 else CAREER_AVG_ZERO)

        peak = []
        if stats['max_day_count'] > 1:
            peak.append((CAREER_MAX_DAY.format(
                date=stats['max_day_date'], count=stats['max_day_count']), False))
        if stats['max_month_count'] > 0:
            peak.append((CAREER_MAX_MONTH.format(
                month=stats['max_month_str'], count=stats['max_month_count']), False))

        miss = [(CAREER_MIN_MONTH.format(month=stats['min_month_str'],
                                         count=stats['min_month_count']), False),
                (CAREER_REST.format(text=stats['rest_period_str']), False)]
        if stats['sage_comment']:
            miss.append((CAREER_COMMENT_WRAP.format(text=stats['sage_comment']), True))

        status = [(CAREER_STATUS.format(days=stats['status_day']), False)]
        if stats['status_comment']:
            status.append((CAREER_COMMENT_WRAP.format(text=stats['status_comment']), True))

        return [
            (CAREER_SECTIONS[0], [(CAREER_FIRST.format(
                date=stats['first_date_str'], days=stats['total_span_days']), False)]),
            (CAREER_SECTIONS[1], [
                (CAREER_TOTAL.format(count=stats['total_count']), False),
                (CAREER_DAYS.format(days=stats['total_days'],
                                    ratio=f"{stats['active_ratio']:.1f}"), False),
                (avg, False)]),
            (CAREER_SECTIONS[2], peak),
            (CAREER_SECTIONS[3], miss),
            (CAREER_SECTIONS[4], status),
        ]

    def render(self, user_name, stats, system_name='娅娅'):
        W = 800
        sections = self._sections(stats)

        kpis = [(str(stats['total_count']), '累计蛋糕'),
                (str(stats['total_days']), '投喂天数'),
                (f"{stats['daily_avg']:.2f}", '日均投喂')]
        kpi_html = ''.join(
            f'<div class="kpi"><div class="num">{_html.escape(v)}</div>'
            f'<div class="cap">{_html.escape(c)}</div></div>' for v, c in kpis)

        sec_html = []
        for title, rows in sections:
            body = ''
            for t, is_note in rows:
                if is_note:
                    body += f'<div class="note">{_html.escape(t)}</div>'
                elif '：' in t:
                    lab, val = t.split('：', 1)
                    body += (f'<div class="row"><span class="lab">'
                             f'{_html.escape(lab)}：</span>'
                             f'<span class="val">{_rich(val)}</span></div>')
                else:
                    body += f'<div class="plain">{_rich(t)}</div>'
            sec_html.append(
                f'<div class="sec"><h3>{_html.escape(title)}</h3>{body}</div>')

        inner = (
            '<div class="card">'
            '<div class="wash" style="height:170px"></div>'
            '<div class="pad">'
            f'<div class="title">{_html.escape(CAREER_TITLE)}</div>'
            f'<div class="subtitle">{_html.escape(CAREER_FEEDER.format(name=user_name))}</div>'
            '<div class="quotewrap">'
            f'<div class="quote">{_html.escape(CAREER_QUOTE.format(comment=stats["summary_comment"]))}</div>'
            '</div>'
            f'<div class="kpis">{kpi_html}</div>'
            f'<div class="sections">{"".join(sec_html)}</div>'
            '</div></div>'
        )

        # 高度：按各分区行数估算（长文本交由浏览器换行，额外留余量）
        head = 130 + 90
        sec_h = sum(52 + sum(24 if n else 30 for _t, n in rows) + 24
                    for _title, rows in sections)
        H = head + sec_h + 40

        ts = int(time.time())
        html_path = os.path.join(self.temp_dir, f"career_{ts}.html")
        out_png = os.path.join(self.temp_dir, f"career_{ts}.png")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(base.page_html(
                inner, W, H, self._css_vars,
                base.bubbles_html(self._bubbles, self._show_bubbles),
                extra_css=_CSS))
        try:
            base.submit_shot_auto(html_path, out_png, W, H)
            return out_png
        finally:
            try:
                if os.path.exists(html_path):
                    os.remove(html_path)
            except Exception:
                pass
