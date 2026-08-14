"""用 HTML/CSS + 系统 Chrome (Playwright) 渲染日历设计方案。

用法：py design/make_calendar_html.py
输出：design/render_out/ 目录下多张 PNG（不入库）
"""
import calendar
from pathlib import Path

# 渲染输出：脚本所在目录的 render_out/（不入库，见 .gitignore）
OUT_DIR = Path(__file__).resolve().parent / 'render_out'
OUT_DIR.mkdir(parents=True, exist_ok=True)

YEAR, MONTH = 2026, 8
USER_NAME = '测试员'
CHECKIN = {1: 1, 3: 2, 5: 1, 6: 3, 10: 1, 12: 2, 14: 1, 15: 1, 20: 1, 25: 2, 28: 1}
TODAY = 15
TOTAL_CAKES = sum(CHECKIN.values())
WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

# (left, top, size, delay, opacity, fill, glow) 泡泡参数，fill=主色 glow=投影色
BUBBLES_A1 = [
    (18, 30, 54, 0, .92, '#f2708f', 'rgba(242,112,143,.45)'),     # 左上大 · 玫粉
    (500, 22, 34, .8, .88, '#c99be6', 'rgba(201,155,230,.4)'),    # 右上中 · 淡紫
    (548, 420, 64, 1.6, .85, '#f78fb4', 'rgba(247,143,180,.45)'),  # 右下大 · 亮粉
    (36, 440, 40, 2.4, .9, '#f5b8a0', 'rgba(245,184,160,.4)'),    # 左下中 · 蜜桃
    (250, 12, 22, .4, .8, '#f48fb1', 'rgba(244,143,177,.4)'),     # 顶部小 · 樱粉
    (430, 120, 26, 1.2, .75, '#d7a7e8', 'rgba(215,167,232,.35)'),  # 中部小 · 薰衣草
    (120, 470, 30, 1.8, .85, '#f28ba5', 'rgba(242,139,165,.4)'),   # 下方中 · 桃粉
    (468, 330, 20, 2.8, .7, '#f7b6d0', 'rgba(247,182,208,.35)'),   # 右下小 · 浅粉
    (300, 480, 24, .9, .8, '#c9a3e8', 'rgba(201,163,232,.35)'),   # 底中 · 紫
    (60, 200, 30, 2.1, .78, '#f5a9bc', 'rgba(245,169,188,.4)'),   # 左中 · 粉
]


def cells_html():
    cal = calendar.monthcalendar(YEAR, MONTH)
    rows = []
    for week in cal:
        cells = []
        for day in week:
            if day == 0:
                cells.append('<div class="day empty"></div>')
                continue
            cls = 'day'
            if day in CHECKIN:
                cls += ' feed'
            if day == TODAY:
                cls += ' today'
            badge = f'<span class="badge">{CHECKIN[day]}</span>' if CHECKIN.get(day, 0) > 1 else ''
            cake = '<div class="cake">🍰</div>' if day in CHECKIN else ''
            cells.append(
                f'<div class="{cls}"><span class="num">{day}</span>{cake}{badge}</div>')
        rows.append('<div class="week">' + ''.join(cells) + '</div>')
    return '\n'.join(rows)


def bubbles_html(specs):
    out = []
    for (left, top, size, delay, opacity, fill, glow) in specs:
        out.append(
            f'<div class="bubble" style="left:{left}px;top:{top}px;'
            f'width:{size}px;height:{size}px;opacity:{opacity};'
            f'--fill:{fill};--glow:{glow};'
            f'animation-delay:{delay}s"></div>')
    return '\n'.join(out)


def page_html(css, bubbles=()):
    return f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }}
html, body {{ width: 600px; height: 540px; overflow: hidden; }}
body {{ position: relative; }}
{css}
</style></head><body>
<div class="scene">
  {bubbles_html(bubbles)}
  <div class="card">
    <div class="title">{USER_NAME}的投喂日历</div>
    <div class="subtitle">{YEAR}年{MONTH}月</div>
    <div class="weekbar">
      {''.join(f'<span>{d}</span>' for d in WEEKDAYS)}
    </div>
    <div class="grid">{cells_html()}</div>
    <div class="foot">本月投喂娅娅 {len(CHECKIN)} 天，共 {TOTAL_CAKES} 块蛋糕</div>
  </div>
</div>
</body></html>'''


# ---------------------------------------------------------------- 版1 泡泡初绽（精致泡泡版）
CSS1 = '''
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
    radial-gradient(ellipse at 18% 8%, rgba(255,255,255,.9) 0%, rgba(255,255,255,0) 42%),
    radial-gradient(ellipse at 85% 90%, rgba(255,214,234,.8) 0%, rgba(255,214,234,0) 45%),
    linear-gradient(180deg, #fff6fb 0%, #ffeef4 42%, #ffe4ef 100%);
  padding: 16px 26px 14px;
  position: relative;
}
/* ---- 彩色玻璃泡泡 ---- */
.bubble {
  position: absolute; border-radius: 50%;
  background:
    radial-gradient(circle at 30% 26%, rgba(255,255,255,.95) 0%, rgba(255,255,255,.30) 20%, rgba(255,255,255,0) 42%),
    radial-gradient(circle at 55% 60%, var(--fill) 0%, color-mix(in srgb, var(--fill), white 32%) 72%, rgba(255,255,255,.4) 100%);
  border: 1.5px solid color-mix(in srgb, var(--fill), white 62%);
  box-shadow:
    inset 0 0 14px rgba(255,255,255,.55),
    inset -4px -4px 10px rgba(219,112,147,.18),
    0 3px 12px var(--glow);
  animation: bubbleDrift 5.5s ease-in-out infinite;
}
.bubble::after {
  content: ''; position: absolute; left: 26%; top: 20%;
  width: 26%; height: 17%;
  border-radius: 50%;
  background: rgba(255,255,255,.95);
  transform: rotate(-28deg);
  filter: blur(0.5px);
}
.bubble::before {
  content: ''; position: absolute; right: 18%; bottom: 22%;
  width: 12%; height: 12%;
  border-radius: 50%;
  background: rgba(255,255,255,.55);
}
/* ---- 卡片 ---- */
.card {
  position: relative; z-index: 2;
  height: 100%;
  display: flex; flex-direction: column;
  background: rgba(255,255,255,.94);
  border: 1px solid #f3d6e4; border-radius: 26px;
  box-shadow: 0 14px 30px rgba(190,120,160,.28), 0 2px 6px rgba(190,120,160,.12);
  padding: 20px 20px 16px;
}
.title { text-align:center; font-size: 25px; font-weight: 700; color: #65432a; letter-spacing: 1px; }
.title::before { content:'🍰 '; }
.title::after { content:' 🍰'; }
.subtitle { text-align:center; font-size: 14px; color: #b2909e; margin: 2px 0 12px; }
.weekbar { display: grid; grid-template-columns: repeat(7,1fr); text-align:center; font-size:14px; color:#b08a98; margin-bottom:6px; }
.weekbar span:nth-child(n+6) { color: #db7093; font-weight:600; }
.grid { flex:1; display:flex; flex-direction:column; gap:6px; }
.week { flex:1; display:grid; grid-template-columns: repeat(7,1fr); gap:6px; }
.day {
  position: relative; border-radius: 10px; background: #fcf9fa;
  border: 1px solid #f0e8ec; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:1px; padding-top:2px;
}
.day .num { font-size: 16px; color: #5a464f; font-weight: 600; }
.day.feed {
  background: linear-gradient(180deg, #ffdcec 0%, #ffc8dd 100%);
  border: 1px solid #f6b6cf;
}
.day.feed.today { border: 2px solid #db7093; }
.day.today:not(.feed) { background: #fff0f6; border: 2px solid #db7093; }
.day.feed .cake { font-size: 17px; line-height: 1; animation: floaty 3s ease-in-out infinite; }
.day .badge {
  position:absolute; top:3px; right:4px; min-width:17px; height:17px; padding:0 3px;
  border-radius: 9px; background:#e9546b; color:#fff; font-size:11px; font-weight:700;
  display:flex; align-items:center; justify-content:center; line-height:1;
}
.foot {
  margin: 12px auto 0; padding: 7px 24px; border-radius: 14px;
  background: linear-gradient(90deg,#ffe3ee,#ffd0e2); color:#d84762;
  font-size: 16px; font-weight: 600; text-align:center;
}
'''

# ---------------------------------------------------------------- 版2 马卡龙双层
CSS2 = '''
.scene {
  width:100%; height:100%; background: linear-gradient(160deg,#fdeef4 0%,#fbdfeb 100%);
  padding: 14px 20px 12px; display:flex; flex-direction:column; position:relative;
}
.plate {
  flex:1; border-radius: 30px; background: linear-gradient(180deg,#ffe0ec,#f7c4d8);
  box-shadow: 0 16px 34px rgba(190,110,150,.30), inset 0 0 0 1px rgba(255,255,255,.5);
  padding: 10px; display:flex; flex-direction:column;
}
.card {
  flex:1; border-radius: 22px; background: rgba(255,255,255,.96);
  border:1px solid #f8d7e4; box-shadow: inset 0 1px 2px rgba(255,255,255,.8);
  padding: 18px 18px 14px; display:flex; flex-direction:column;
}
.title { text-align:center; font-size:25px; font-weight:800; color:#e23e63; }
.title::before { content:'🍰 '; }
.title::after { content:' 🍰'; }
.subtitle { text-align:center; font-size:14px; color:#cf91a6; margin:2px 0 10px; }
.weekbar { display:grid; grid-template-columns:repeat(7,1fr); text-align:center; font-size:14px; color:#b88a99; margin-bottom:6px; }
.weekbar span:nth-child(n+6){ color:#e23e63; font-weight:700; }
.grid { flex:1; display:flex; flex-direction:column; gap:6px; }
.week { flex:1; display:grid; grid-template-columns:repeat(7,1fr); gap:6px; }
.day {
  position:relative; border-radius:10px; background:#faf5f8; border:1px solid #efe3ea;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:1px;
}
.day .num { font-size:16px; color:#5a464f; font-weight:600; }
.day.feed {
  background: linear-gradient(180deg,#ffd0e2,#f7a9c8);
  border:2px solid #fff; box-shadow: 0 2px 5px rgba(190,90,130,.25);
}
.day.feed .cake { font-size:17px; }
.day.today.feed { box-shadow: 0 0 0 2px #db7093, 0 2px 5px rgba(190,90,130,.25); }
.day.today:not(.feed) { background:#fff0f6; border:2px solid #db7093; }
.day .badge {
  position:absolute; top:4px; right:4px; min-width:19px; height:19px; padding:0 4px;
  border-radius:10px; background:#fff; color:#e23e63; font-size:12px; font-weight:800;
  display:flex; align-items:center; justify-content:center; box-shadow:0 1px 3px rgba(190,90,130,.3);
}
.foot {
  margin:12px auto 0; padding:7px 26px; border-radius:16px;
  background:linear-gradient(90deg,#ffe3ee,#f9c3d8); border:1px solid #f6b7cf;
  color:#d84762; font-size:16px; font-weight:700; text-align:center;
}
'''

# ---------------------------------------------------------------- 版3 柔雾珠光
CSS3 = '''
.scene {
  width:100%; height:100%; background: linear-gradient(180deg,#fffbfd 0%,#fdf0f5 55%,#f9e8f0 100%);
  padding: 22px 30px 16px; display:flex; flex-direction:column;
}
.card {
  flex:1; border-radius: 32px; background: rgba(255,255,255,.82);
  border:1px solid rgba(246,232,240,.9);
  box-shadow: 0 8px 24px rgba(190,140,170,.14), 0 1px 3px rgba(190,140,170,.08);
  padding: 26px 22px 18px; display:flex; flex-direction:column;
}
.title { text-align:center; font-size:24px; font-weight:600; color:#8c6a7e; letter-spacing:2px; }
.subtitle { text-align:center; font-size:13px; color:#b7a0ad; margin:4px 0 14px; letter-spacing:4px; }
.weekbar { display:grid; grid-template-columns:repeat(7,1fr); text-align:center; font-size:13px; color:#bfa4b0; margin-bottom:8px; }
.weekbar span:nth-child(n+6){ color:#db7093; font-weight:600; }
.grid { flex:1; display:flex; flex-direction:column; gap:5px; }
.week { flex:1; display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
.day {
  position:relative; border-radius:12px; background:#fcfafb; border:1px solid #f5edf2;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px;
}
.day .num { font-size:15px; color:#7d6670; }
.day.feed { background:#ffeef5; border:1px solid #f7d0e0; }
.day.feed .cake { font-size:15px; filter: saturate(0.9); }
.day.today:not(.feed) { background:#fff5f9; border:1px solid #e9546b; }
.day.feed.today { box-shadow: 0 0 0 1px #e9546b; }
.day .badge {
  position:absolute; top:2px; right:3px; font-size:11px; color:#e9546b; font-weight:700;
}
.foot { text-align:center; margin-top:14px; font-size:15px; color:#8c6a7e; font-weight:600; }
'''

# ---------------------------------------------------------------- 版4 糖果彩带
CSS4 = '''
.scene {
  width:100%; height:100%; background:#fff7fa; padding:14px 22px 14px; display:flex; flex-direction:column;
}
.ribbon {
  height:9px; border-radius:9px; margin-bottom:12px;
  background: linear-gradient(90deg,#ffb3c6,#ff8fab,#f4a261,#e9c46a,#a3d9a5,#7ec8e3,#c6a9e8);
}
.card {
  flex:1; border-radius:20px; background:#fff; border:1px solid #f3e0e8;
  box-shadow:0 10px 24px rgba(210,150,180,.18); padding:16px 16px 12px; display:flex; flex-direction:column;
}
.title { text-align:center; font-size:23px; font-weight:800; background:linear-gradient(90deg,#e9546b,#db7093,#c779d0); -webkit-background-clip:text; background-clip:text; color:transparent; }
.title::before { content:'🍰 '; }
.title::after { content:' 🍰'; }
.subtitle { text-align:center; font-size:13px; color:#c28b9d; margin:2px 0 10px; }
.weekbar { display:grid; grid-template-columns:repeat(7,1fr); text-align:center; font-size:13px; color:#b58d9a; margin-bottom:6px; }
.weekbar span:nth-child(n+6){ color:#e9546b; font-weight:700; }
.grid { flex:1; display:flex; flex-direction:column; gap:6px; }
.week { flex:1; display:grid; grid-template-columns:repeat(7,1fr); gap:6px; }
.day {
  position:relative; border-radius:12px; background:#fcf7f9; border:1px solid #f0e4ea;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:1px;
}
.day .num { font-size:16px; color:#6b5260; font-weight:600; }
.day.feed {
  background: linear-gradient(135deg,#ffd3e2,#ffb3c9);
  border:1px solid #f49ab8;
}
.day.feed .cake { font-size:16px; }
.day.today.feed { border:2px solid #e9546b; }
.day.today:not(.feed) { background:#fff0f6; border:2px solid #e9546b; }
.day .badge {
  position:absolute; top:3px; right:3px; min-width:16px; height:16px; padding:0 3px;
  border-radius:8px; background:#e9546b; color:#fff; font-size:10px; font-weight:800;
  display:flex; align-items:center; justify-content:center;
}
.foot {
  margin:12px auto 0; padding:6px 22px; border-radius:20px;
  background:linear-gradient(90deg,#ffd3e2,#f4a9c0); color:#d13c58; font-size:15px; font-weight:700; text-align:center;
}
'''


DESIGNS = [
    ('A1-泡泡初绽-v3', CSS1, BUBBLES_A1),
    ('A2-马卡龙双层', CSS2, ()),
    ('A3-柔雾珠光', CSS3, ()),
    ('A4-糖果彩带', CSS4, ()),
]


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome')
        for name, css, bubbles in DESIGNS:
            html = page_html(css, bubbles)
            path = OUT_DIR / f'{name}.html'
            path.write_text(html, encoding='utf-8')
            out_png = OUT_DIR / f'{name}.png'
            page = browser.new_page(viewport={'width': 600, 'height': 540},
                                    device_scale_factor=2)
            page.goto(path.as_uri())
            page.wait_for_timeout(500)
            page.screenshot(path=str(out_png))
            page.close()
            print('渲染完成:', out_png.name)
        browser.close()
    print('全部完成 →', OUT_DIR)


if __name__ == '__main__':
    main()
