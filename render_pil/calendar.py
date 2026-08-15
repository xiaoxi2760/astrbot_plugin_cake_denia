"""PIL 版日历渲染：复刻设计稿 A1 泡泡初绽（无第三方依赖）。

配色、泡泡、光晕与开关由主题驱动：预设见 resources/themes/（娅娅/达妮娅），
用户自定义见 resources/theme.json。
"""
import calendar
import os
import time
from datetime import date
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..resources.texts import CALENDAR_SUMMARY
from ..theme import parse_color

WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

# 日历网格布局
LEFT = 46
TOP = 110
CELL_W = 67
CELL_H = 68
GAP = 6

# 卡片区域与投影（布局固定，不随主题变）
CARD_BOX = (26, 16, 574, 526)
CARD_SHADOW = (190, 120, 160, 110)


class PilCalendarRenderer:

    def __init__(self, core, theme=None):
        self.core = core
        self.temp_dir = core.temp_dir
        self.font_path = core.font_path
        self.emoji_path = getattr(core, '_emoji_path', None)
        theme = theme or {}
        colors = theme.get('colors', {})
        options = theme.get('options', {})
        self._show_avatar = bool(options.get('show_avatar', True))
        self._show_bubbles = bool(options.get('show_bubbles', True))
        c = lambda name, default: parse_color(colors.get(name), default)

        self._bg_stops = [
            (0.00, c('bg_top', (255, 246, 251))),
            (0.42, c('bg_mid', (255, 238, 244))),
            (1.00, c('bg_bottom', (255, 228, 239))),
        ]
        self._card_fill = c('card_fill', (255, 255, 255, 240))
        self._card_border = c('card_border', (243, 214, 228))
        self._title_color = c('title', (101, 67, 42))
        self._subtitle_color = c('subtitle', (178, 144, 158))
        self._weekday_color = c('weekday', (176, 138, 152))
        self._weekend_color = c('weekend', (219, 112, 147))
        self._day_color = c('day_text', (90, 70, 80))
        self._empty_bg = c('empty_bg', (252, 249, 250))
        self._empty_border = c('empty_border', (240, 232, 236))
        self._feed_top = c('feed_top', (255, 220, 236))
        self._feed_bottom = c('feed_bottom', (255, 200, 221))
        self._feed_border = c('feed_border', (246, 182, 207))
        self._today_bg = c('today_bg', (255, 240, 246))
        self._badge_color = c('badge', (233, 84, 107))
        self._foot_top = c('foot_top', (255, 227, 238))
        self._foot_bottom = c('foot_bottom', (255, 208, 226))
        self._foot_text = c('foot_text', (216, 71, 98))

        # 背景光晕：(cx, cy, radius, color, strength)
        self._glows = []
        for g in theme.get('glows', []):
            self._glows.append((
                int(g.get('cx', 0)),
                int(g.get('cy', 0)),
                int(g.get('radius', 100)),
                parse_color(g.get('color'), (255, 255, 255)),
                int(g.get('strength', 50)),
            ))

        # 彩色玻璃泡泡：(left, top, size, opacity, fill_rgb)
        self._bubbles = []
        for b in theme.get('bubbles', []):
            self._bubbles.append((
                int(b.get('left', 0)),
                int(b.get('top', 0)),
                int(b.get('size', 20)),
                float(b.get('opacity', 0.8)),
                parse_color(b.get('fill'), (240, 150, 180)),
            ))

    def _font(self, size):
        return ImageFont.truetype(self.font_path, size)

    def _emoji_font(self, size):
        if self.emoji_path:
            try:
                return ImageFont.truetype(self.emoji_path, size)
            except Exception:
                return None
        return None

    # ------------------------------------------------------------ 画布工具
    @staticmethod
    def _vgrad(w, h, stops):
        """竖直分段渐变。"""
        img = Image.new('RGB', (1, h))
        px = img.load()
        for y in range(h):
            k = y / (h - 1) if h > 1 else 0
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= k <= p1:
                    t = (k - p0) / (p1 - p0) if p1 > p0 else 0
                    px[0, y] = tuple(int(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
                    break
        return img.resize((w, h))

    @staticmethod
    def _hgrad(w, h, c0, c1):
        img = Image.new('RGB', (w, 1))
        px = img.load()
        for x in range(w):
            t = x / (w - 1) if w > 1 else 0
            px[x, 0] = tuple(int(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
        return img.resize((w, h))

    def _glow_layer(self, w, h):
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for cx, cy, radius, color, strength in self._glows:
            for rr in range(radius, 0, -4):
                a = int(strength * (1 - rr / radius))
                if a > 2:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                              outline=(color[0], color[1], color[2], a), width=3)
        return layer

    def _bubbles_layer(self, w, h):
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        for (x, y, size, opacity, fill) in self._bubbles:
            r = size / 2
            b = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(b)
            for rr in range(int(r), 0, -2):
                k = rr / r
                mix = int(255 * (1 - k) * 0.75)
                col = (min(255, fill[0] + mix), min(255, fill[1] + mix), min(255, fill[2] + mix))
                d.ellipse([r - rr, r - rr, r + rr, r + rr],
                          outline=(col[0], col[1], col[2], 255), width=2)
            # 玻璃高光（仿 CSS ::after / ::before）
            d.ellipse([size * 0.26, size * 0.20, size * 0.26 + size * 0.26, size * 0.20 + size * 0.17],
                      fill=(255, 255, 255, 235))
            sp = size * 0.10
            d.ellipse([size * 0.70, size * 0.66, size * 0.70 + sp, size * 0.66 + sp],
                      fill=(255, 255, 255, 140))
            # 整体不透明度（仅 alpha 通道）
            r_, g_, b_, a = b.split()
            a = a.point(lambda i: int(i * opacity))
            b = Image.merge('RGBA', (r_, g_, b_, a))
            layer.paste(b, (x, y), b)
        return layer

    def _card_shadow(self):
        sh = Image.new('RGBA', (self._W, self._H), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        d.rounded_rectangle([CARD_BOX[0], CARD_BOX[1] + 8, CARD_BOX[2], CARD_BOX[3] + 8],
                            radius=26, fill=CARD_SHADOW)
        return sh.filter(ImageFilter.GaussianBlur(14))

    def _draw_emoji_or_check(self, draw, cx, cy, efont, size):
        """投喂日标记：🍰 或（无 emoji 字体时）红色勾。"""
        if efont is not None:
            draw.text((cx, cy), '\U0001F370', font=efont, anchor='mm', embedded_color=True)
        else:
            draw.line([(cx - 9, cy - 14), (cx - 3, cy - 9), (cx + 9, cy - 24)],
                      fill=self._badge_color, width=3, joint='curve')

    def _draw_title(self, draw, title, fs):
        tw = draw.textlength(title, font=fs['title'])
        draw.text((self._W / 2, 42), title, font=fs['title'], fill=self._title_color, anchor='mm')
        ef = self._emoji_font(18)
        if ef is not None:
            draw.text((self._W / 2 - tw / 2 - 22, 42), '\U0001F370', font=ef,
                      anchor='mm', embedded_color=True)
            draw.text((self._W / 2 + tw / 2 + 22, 42), '\U0001F370', font=ef,
                      anchor='mm', embedded_color=True)

    def _draw_weekdays(self, draw, fs, cell_w):
        for i, d in enumerate(WEEKDAYS):
            draw.text((LEFT + i * (cell_w + GAP) + cell_w / 2, 94), d, font=fs['week'],
                      fill=self._weekday_color if i < 5 else self._weekend_color, anchor='mm')

    def _draw_day_cell(self, img, draw, fs, x, y, day, is_feed, is_today, count, efont,
                       cell_w, cell_h):
        box = [x, y, x + cell_w, y + cell_h]
        if is_feed:
            grad = self._vgrad(cell_w, cell_h, [(0, self._feed_top), (1, self._feed_bottom)]).convert('RGBA')
            mask = Image.new('L', (cell_w, cell_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, cell_w - 1, cell_h - 1], radius=10, fill=255)
            cell = Image.new('RGBA', (cell_w, cell_h), (0, 0, 0, 0))
            cell.paste(grad, (0, 0), mask)
            img.paste(cell, (x, y), cell)
            bw = 2 if is_today else 1
            draw.rounded_rectangle(box, radius=10,
                                   outline=self._weekend_color if is_today else self._feed_border,
                                   width=bw)
        elif is_today:
            draw.rounded_rectangle(box, radius=10, fill=self._today_bg,
                                   outline=self._weekend_color, width=2)
        else:
            draw.rounded_rectangle(box, radius=10, fill=self._empty_bg,
                                   outline=self._empty_border, width=1)
        draw.text((x + cell_w / 2, y + 18), str(day), font=fs['day'], fill=self._day_color, anchor='mm')
        if is_feed:
            self._draw_emoji_or_check(draw, x + cell_w / 2, y + cell_h - 15, efont, 17)
            if count > 1:
                badge_w = max(17, int(draw.textlength(str(count), font=fs['badge'])) + 6)
                bx1 = x + cell_w - 4
                draw.rounded_rectangle([bx1 - badge_w, y + 3, bx1, y + 20], radius=9,
                                       fill=self._badge_color)
                draw.text((bx1 - badge_w / 2, y + 11.5), str(count), font=fs['badge'],
                          fill=(255, 255, 255), anchor='mm')

    def _paste_avatar(self, img, avatar_path, xy, size=40):
        """左上角圆形 QQ 头像，缺失时忽略。"""
        if not avatar_path or not os.path.exists(avatar_path):
            return
        try:
            av = Image.open(avatar_path).convert('RGBA')
            av = av.resize((size, size))
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            out.paste(av, (0, 0), mask)
            # 白描边
            ring = ImageDraw.Draw(out)
            ring.ellipse([1, 1, size - 1, size - 1], outline=(255, 255, 255, 230), width=2)
            img.paste(out, xy, out)
        except Exception:
            pass

    def render(self, user_id, user_name, year, month, checkin_data, total_cakes,
               avatar_path=None, today=None):
        self._W, self._H = 600, 540
        if today is None:
            today = date.today().day if (date.today().year == year and date.today().month == month) else 0

        fs = {'title': self._font(25), 'sub': self._font(14), 'week': self._font(14),
              'day': self._font(16), 'badge': self._font(11), 'foot': self._font(16)}
        efont = self._emoji_font(17)

        # 网格行高自适应（5 行/6 行都放得下，避免 31 号越界）
        cal = calendar.monthcalendar(year, month)
        n_rows = len(cal)
        avail = 486 - 8 - TOP
        cell_h = (avail - (n_rows - 1) * GAP) // n_rows
        cell_w = CELL_W

        img = self._vgrad(self._W, self._H, self._bg_stops).convert('RGBA')
        img = Image.alpha_composite(img, self._glow_layer(self._W, self._H))
        if self._show_bubbles:
            img = Image.alpha_composite(img, self._bubbles_layer(self._W, self._H))
        img = Image.alpha_composite(img, self._card_shadow())

        card = Image.new('RGBA', (self._W, self._H), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle(CARD_BOX, radius=26, fill=self._card_fill)
        cd.rounded_rectangle(CARD_BOX, radius=26, outline=self._card_border, width=2)
        img = Image.alpha_composite(img, card)
        draw = ImageDraw.Draw(img)

        if self._show_avatar:
            # 56px 圆形头像（原 40px 偏小，QQ 头像细节看不清）
            self._paste_avatar(img, avatar_path, (32, 22), 56)
        self._draw_title(draw, f'{user_name}的投喂日历', fs)
        draw.text((self._W / 2, 68), f'{year}年{month}月', font=fs['sub'],
                  fill=self._subtitle_color, anchor='mm')
        self._draw_weekdays(draw, fs, cell_w)

        for r, week in enumerate(cal):
            for i, day in enumerate(week):
                if day == 0:
                    continue
                x = LEFT + i * (cell_w + GAP)
                y = TOP + r * (cell_h + GAP)
                self._draw_day_cell(img, draw, fs, x, y, day,
                                    day in checkin_data, day == today,
                                    checkin_data.get(day, 0), efont, cell_w, cell_h)

        # 页脚胶囊
        foot_w, foot_h = 330, 28
        foot = self._hgrad(foot_w, foot_h, self._foot_top, self._foot_bottom).convert('RGBA')
        fmask = Image.new('L', (foot_w, foot_h), 0)
        ImageDraw.Draw(fmask).rounded_rectangle([0, 0, foot_w - 1, foot_h - 1], radius=14, fill=255)
        fcell = Image.new('RGBA', (foot_w, foot_h), (0, 0, 0, 0))
        fcell.paste(foot, (0, 0), fmask)
        img.paste(fcell, (self._W // 2 - foot_w // 2, 486), fcell)
        draw.text((self._W / 2, 500),
                  CALENDAR_SUMMARY.format(days=len(checkin_data), cakes=total_cakes),
                  font=fs['foot'], fill=self._foot_text, anchor='mm')

        file_path = os.path.join(self.temp_dir, f"cake_{user_id}_{int(time.time())}.png")
        img.convert('RGB').save(file_path, format='PNG')
        return file_path
