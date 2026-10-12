"""HTML 版投喂报告：标题 + 投喂率旋钮进度条 + 正文气泡芯片。

高度随内容自适应（按文本行数估算行高），与 PIL 版视觉一致。
"""
import html as _html
import os
import re
import time

from ..resources.texts import ANALYSIS_HEADER
from . import base

_NUM_RE = re.compile(r'(\d[\d.,:%]*(?:\.\d+)?%?)')
_QUOTE_PREFIX = ('娅娅：', '达妮娅：', '年度评价：')

_CSS = '''
.pad { position:relative; z-index:1; padding:16px 34px 14px; }
.title { text-align:center; font-size:30px; font-weight:700; color:var(--title); }
.subtitle { text-align:center; font-size:15px; color:var(--subtitle); margin-top:2px; }
.underline { width:52px; height:5px; border-radius:3px; margin:7px auto 0;
  background:linear-gradient(90deg, var(--feed-top), var(--feed-bottom)); }
.rate { margin:18px 22px 0; }
.ratehead { display:flex; justify-content:space-between; font-size:16px; margin-bottom:7px; }
.ratehead .lab { color:var(--subtitle); }
.ratehead .val { color:var(--foot-text); font-weight:700; }
.track {
  height:18px; border-radius:9px; position:relative;
  background:var(--empty-bg); border:1px solid var(--empty-border);
}
.fill {
  height:100%; border-radius:9px; position:relative; min-width:0;
  background:linear-gradient(90deg, var(--feed-top), var(--feed-bottom));
  animation: grow .8s ease-out;
}
.fill::after {
  content:''; position:absolute; right:-2px; top:50%;
  width:20px; height:20px; border-radius:50%;
  transform:translateY(-50%);
  background:#fff; border:4px solid var(--feed-bottom);
  box-shadow:0 1px 5px rgba(0,0,0,.16);
}
@keyframes grow { from { width:0 !important; } }
.body { margin:20px 22px 0; text-align:center; }
.body p {
  width:fit-content; max-width:100%; margin:9px auto 0; padding:8px 20px;
  font-size:18px; color:var(--day-text); line-height:28px;
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 78%);
  border:1px solid color-mix(in srgb, var(--feed-border), var(--card-fill) 50%);
  border-radius:16px;
}
.body p.hero {
  font-size:20px; font-weight:600; padding:10px 24px;
  background:linear-gradient(90deg, color-mix(in srgb, var(--feed-top), var(--card-fill) 45%),
              color-mix(in srgb, var(--feed-bottom), var(--card-fill) 60%));
  border-color:color-mix(in srgb, var(--feed-border), var(--card-fill) 35%);
}
.body p.quote {
  text-align:left; border-left:4px solid var(--weekend);
  background:color-mix(in srgb, var(--feed-top), var(--card-fill) 62%);
}
.body p.tip {
  background:transparent; border:0; padding:2px 8px;
  color:var(--subtitle); font-size:15px; line-height:24px;
}
.dots { display:flex; justify-content:center; gap:11px; margin-top:16px; }
.dots i { width:5px; height:5px; border-radius:50%; }
.dots i:nth-child(1) { background:var(--badge); }
.dots i:nth-child(2) { background:var(--feed-border); }
.dots i:nth-child(3) { background:var(--empty-border); }
'''


def _rich(text):
    """转义并把数字段包上 <span class="num"> 高亮。"""
    esc = _html.escape(text)
    return _NUM_RE.sub(r'<span class="num">\1</span>', esc)


class HtmlAnalysisRenderer:

    def __init__(self, core, theme=None):
        self.core = core
        self.temp_dir = core.temp_dir
        theme = theme or {}
        self._bubbles = theme.get('bubbles', [])
        self._options = theme.get('options', {})
        self._show_bubbles = bool(self._options.get('show_bubbles', True))
        self._css_vars = base.theme_css_vars(theme)

    def render(self, user_name, target_period, analysis_result,
               checkin_rate=0.0, system_name='蛋糕'):
        W = 750
        CARD_PAD = 28
        inner_w = W - 34 * 2 - CARD_PAD * 2

        # 估算正文高度：按每字符宽度 ~19px（CJK）粗略折行
        paragraphs = []      # (html, kind, 行数)
        body_h = 0
        kind = 'normal'
        for raw in analysis_result.split('\n'):
            line = raw.strip()
            if not line:
                body_h += 10
                kind = 'normal'
                continue
            if line.startswith(_QUOTE_PREFIX):
                kind = 'quote'
            elif line.startswith('小贴士：'):
                kind = 'tip'
            n = max(1, -(-sum(19 if ord(c) > 0xFF else 10 for c in line) // max(inner_w, 1)))
            paragraphs.append((line, kind, n))
            line_h = 28 if kind != 'tip' else 24
            body_h += n * line_h + 18
            kind = 'normal' if kind == 'hero' else kind
        # 首个非空行视为主打行
        for i, (line, k, n) in enumerate(paragraphs):
            if k == 'normal':
                paragraphs[i] = (line, 'hero', n)
                break

        header_h = 150 + 8          # 标题 + 副标题 + 下划线
        rate_h = 18 + 7 + 20 + 18
        card_h = header_h + rate_h + body_h + 40
        H = card_h + 34 * 2

        rate_pct = max(0.0, min(1.0, float(checkin_rate or 0)))
        paras = ''.join(
            f'<p class="{k}">{_rich(t)}</p>' for t, k, _n in paragraphs)

        inner = (
            '<div class="card">'
            '<div class="wash"></div>'
            '<div class="pad">'
            f'<div class="title">{_html.escape(ANALYSIS_HEADER.format(period=target_period, name=user_name))}</div>'
            f'<div class="subtitle">{_html.escape(f"{target_period}的投喂报告")}</div>'
            '<div class="underline"></div>'
            '<div class="rate">'
            '<div class="ratehead"><span class="lab">本月投喂率</span>'
            f'<span class="val">{rate_pct:.0%}</span></div>'
            '<div class="track">'
            f'<div class="fill" style="width:{rate_pct * 100:.1f}%"></div>'
            '</div></div>'
            f'<div class="body">{paras}</div>'
            '<div class="dots"><i></i><i></i><i></i></div>'
            '</div></div>'
        )

        ts = int(time.time())
        html_path = os.path.join(self.temp_dir, f"analysis_{ts}.html")
        out_png = os.path.join(self.temp_dir, f"analysis_{ts}.png")
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
