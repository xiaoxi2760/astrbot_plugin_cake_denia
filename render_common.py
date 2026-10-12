"""渲染公共基元：渐变、光晕、玻璃泡泡、卡片投影。

日历（render_pil/calendar.py）与报告/生涯/排行榜三张图共用同一套视觉语言，
保证四张图在同一主题下是一套设计，而不是各自为政的硬编码配色。

所有颜色一律经 theme.parse_color 解析，支持 #rgb / #rrggbb / rgb() / rgba()。
"""
import os
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .theme import parse_color


class ThemePalette:
    """从主题 dict 解析出的调色板，缺字段时回退到日历默认粉彩。"""

    # 日历字段 → 通用语义名的别名，让非日历图也能取到合适的颜色
    ALIAS = {
        'accent': 'badge',
        'accent_text': 'foot_text',
        'panel_bg': 'card_fill',
        'panel_border': 'card_border',
        'strong': 'weekend',
        'muted': 'subtitle',
        'faint': 'weekday',
        'body': 'day_text',
    }

    def __init__(self, theme=None):
        theme = theme or {}
        colors = theme.get('colors', {})
        options = theme.get('options', {})
        self.name = theme.get('name', '')
        self.show_bubbles = bool(options.get('show_bubbles', True))
        self.show_avatar = bool(options.get('show_avatar', True))
        self._c = dict(colors)

        self.bg_top = parse_color(colors.get('bg_top'), (255, 246, 251))
        self.bg_mid = parse_color(colors.get('bg_mid'), (255, 238, 244))
        self.bg_bottom = parse_color(colors.get('bg_bottom'), (255, 228, 239))
        self.card_fill = parse_color(colors.get('card_fill'), (255, 255, 255, 240))
        self.card_border = parse_color(colors.get('card_border'), (243, 214, 228))
        self.title = parse_color(colors.get('title'), (101, 67, 42))
        self.subtitle = parse_color(colors.get('subtitle'), (178, 144, 158))
        self.weekday = parse_color(colors.get('weekday'), (176, 138, 152))
        self.weekend = parse_color(colors.get('weekend'), (219, 112, 147))
        self.body = parse_color(colors.get('day_text'), (90, 70, 80))
        self.empty_bg = parse_color(colors.get('empty_bg'), (252, 249, 250))
        self.empty_border = parse_color(colors.get('empty_border'), (240, 232, 236))
        self.feed_top = parse_color(colors.get('feed_top'), (255, 220, 236))
        self.feed_bottom = parse_color(colors.get('feed_bottom'), (255, 200, 221))
        self.feed_border = parse_color(colors.get('feed_border'), (246, 182, 207))
        self.today_bg = parse_color(colors.get('today_bg'), (255, 240, 246))
        self.accent = parse_color(colors.get('badge'), (233, 84, 107))
        self.accent_text = parse_color(colors.get('foot_text'), (216, 71, 98))
        self.foot_top = parse_color(colors.get('foot_top'), (255, 227, 238))
        self.foot_bottom = parse_color(colors.get('foot_bottom'), (255, 208, 226))

        self.glows = []
        for g in theme.get('glows', []):
            self.glows.append((
                int(g.get('cx', 0)), int(g.get('cy', 0)), int(g.get('radius', 100)),
                parse_color(g.get('color'), (255, 255, 255)),
                int(g.get('strength', 50)),
            ))

        self.bubbles = []
        for b in theme.get('bubbles', []):
            self.bubbles.append((
                int(b.get('left', 0)), int(b.get('top', 0)), int(b.get('size', 20)),
                float(b.get('opacity', 0.8)),
                parse_color(b.get('fill'), (240, 150, 180)),
            ))

    def get(self, name, default):
        """按语义名取色，未知名字回退 default。"""
        name = self.ALIAS.get(name, name)
        val = self._c.get(name)
        if val is None:
            return default
        return parse_color(val, default)

    def rgba(self, color, alpha):
        """给 RGB(A) 颜色套上指定透明度。"""
        if len(color) >= 4:
            return (color[0], color[1], color[2], int(alpha))
        return (color[0], color[1], color[2], int(alpha))


# ------------------------------------------------------------ 渐变
def vgrad(w, h, stops):
    """竖直分段渐变。stops = [(pos, (r,g,b)), ...]"""
    img = Image.new('RGB', (1, h))
    px = img.load()
    for y in range(h):
        k = y / (h - 1) if h > 1 else 0
        c = stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= k <= p1:
                t = (k - p0) / (p1 - p0) if p1 > p0 else 0
                c = tuple(int(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
                break
        px[0, y] = c
    return img.resize((w, h))


def hgrad(w, h, c0, c1):
    """水平渐变。"""
    img = Image.new('RGB', (w, 1))
    px = img.load()
    for x in range(w):
        t = x / (w - 1) if w > 1 else 0
        px[x, 0] = tuple(int(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
    return img.resize((w, h))


# ------------------------------------------------------------ 装饰层
def glow_layer(w, h, glows):
    """柔和径向光晕层：小图画实心圆 + 高斯模糊再放大（同心圆环会有色带）。"""
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sw, sh = max(w // 4, 1), max(h // 4, 1)
    for cx, cy, radius, color, strength in glows:
        small = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
        r = max(radius // 4, 2)
        px, py = cx // 4, cy // 4
        ImageDraw.Draw(small).ellipse(
            [px - r, py - r, px + r, py + r],
            fill=(color[0], color[1], color[2], max(int(strength), 1)))
        small = small.filter(ImageFilter.GaussianBlur(r * 0.6))
        layer = Image.alpha_composite(layer, small.resize((w, h), Image.BILINEAR))
    return layer


def _glass_ball(size, fill):
    """单颗玻璃泡泡：径向渐变球体 + 亮环 + 左上高光 + 右下小反光。

    渐变先在小图上以同心实心圆画好再放大，避免逐环描边的台阶感。
    """
    SS = 4
    S = size * SS
    R = max(size, 24)
    half = R / 2
    grad = Image.new('RGBA', (R, R), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(int(half), 0, -1):
        t = (1 - i / half) * 0.22          # 中心接近本色，向外渐亮
        c = (int(fill[0] + (255 - fill[0]) * t),
             int(fill[1] + (255 - fill[1]) * t),
             int(fill[2] + (255 - fill[2]) * t))
        gd.ellipse([half - i, half - i, half + i, half + i], fill=c + (255,))
    grad = grad.resize((S, S), Image.BICUBIC)

    ball = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ball.paste(grad, (0, 0), grad)

    # 右下内阴影（仿 CSS inset 阴影）
    sh = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    sw_ = max(S // 7, SS * 2)
    off = S * 0.06
    ImageDraw.Draw(sh).ellipse(
        [sw_ / 2 - off, sw_ / 2 - off, S - sw_ / 2 - off, S - sw_ / 2 - off],
        outline=(70, 35, 55, 60), width=sw_)
    sh = sh.filter(ImageFilter.GaussianBlur(S * 0.05))
    ball = Image.alpha_composite(ball, sh)

    d = ImageDraw.Draw(ball)
    lw = max(S // 32, SS)                  # 外缘亮环（仿 1.5px border）
    rim = tuple(min(255, int(c + (255 - c) * 0.45)) for c in fill[:3])
    d.ellipse([lw // 2, lw // 2, S - lw // 2 - 1, S - lw // 2 - 1],
              outline=rim + (235,), width=lw)
    d.ellipse([S * 0.24, S * 0.18, S * 0.52, S * 0.37], fill=(255, 255, 255, 225))
    sp = S * 0.09
    d.ellipse([S * 0.68, S * 0.64, S * 0.68 + sp, S * 0.64 + sp],
              fill=(255, 255, 255, 150))
    return ball.resize((size, size), Image.LANCZOS)


def bubble_layer(w, h, bubbles):
    """彩色玻璃泡泡层：超采样玻璃球（渐变球体 + 双高光）。"""
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for (x, y, size, opacity, fill) in bubbles:
        size = max(int(size), 8)
        ball = _glass_ball(size, fill)
        if opacity < 1.0:
            r_, g_, b_, a = ball.split()
            a = a.point(lambda i: int(i * opacity))
            ball = Image.merge('RGBA', (r_, g_, b_, a))
        layer.alpha_composite(ball, dest=(int(x), int(y)))
    return layer


def darken(color, factor=0.55, alpha=None):
    """按比例加深颜色（用于派生投影/描边等深色锚点）。"""
    if len(color) >= 4 and alpha is None:
        alpha = color[3]
    r, g, b = color[0], color[1], color[2]
    return (int(r * factor), int(g * factor), int(b * factor),
            alpha if alpha is not None else 255)


def rounded_card_layer(w, h, box, radius=26, fill=(255, 255, 255, 240),
                       border=(243, 214, 228), border_w=2, shadow=True,
                       shadow_color=(190, 120, 160, 110), shadow_blur=14,
                       shadow_offset=8, shadow_alpha=140, shadow_spread=1.18):
    """圆角卡片（含投影）作为 RGBA 层返回，供 alpha_composite。

    shadow_spread > 1 时投影随卡片尺寸放大（HTML box-shadow 的观感），
    shadow_alpha 默认提高，让浅色主题下投影仍能形成深度层次。
    """
    if shadow:
        dx, dy = box[2] - box[0], box[3] - box[1]
        spread = shadow_spread
        off_x = shadow_offset * spread
        off_y = shadow_offset
        blur = max(int(shadow_blur * spread), 6)
        sc = shadow_color
        if len(sc) >= 4:
            sc = (sc[0], sc[1], sc[2], shadow_alpha)
        sh = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        d.rounded_rectangle(
            [box[0], box[1] + off_y, box[2], box[3] + off_y],
            radius=radius, fill=sc)
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
    else:
        sh = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle(box, radius=radius, fill=fill)
    if border_w > 0 and len(border) >= 3:
        cd.rounded_rectangle(box, radius=radius, outline=border, width=border_w)
    return Image.alpha_composite(sh, card)


def scene(w, h, palette, card_box=None, card_radius=26, card_shadow=True,
          card_fill=None, card_border=None, **card_kwargs):
    """构建统一背景：渐变 + 光晕 + 泡泡 + 玻璃卡片，返回 RGBA Image。

    card_kwargs 透传给 rounded_card_layer（shadow_alpha / shadow_spread 等）。
    """
    img = vgrad(w, h, [(0.00, palette.bg_top),
                       (0.42, palette.bg_mid),
                       (1.00, palette.bg_bottom)]).convert('RGBA')
    img = Image.alpha_composite(img, glow_layer(w, h, palette.glows))
    if palette.show_bubbles:
        img = Image.alpha_composite(img, bubble_layer(w, h, palette.bubbles))
    if card_box is not None:
        defaults = {}
        if 'shadow_color' in card_kwargs:
            defaults['shadow_color'] = darken(palette.weekend, 0.45, 0)
        defaults.update(card_kwargs)
        img = Image.alpha_composite(img, rounded_card_layer(
            w, h, card_box, radius=card_radius,
            fill=card_fill if card_fill is not None else palette.card_fill,
            border=card_border if card_border is not None else palette.card_border,
            shadow=card_shadow, **defaults))
    return img


def pill(w, h, c0, c1, radius):
    """胶囊/页脚条：水平渐变 + 圆角遮罩。"""
    grad = hgrad(w, h, c0, c1).convert('RGBA')
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def paste_avatar(img, avatar_path, xy, size=40, ring=(255, 255, 255, 230)):
    """把头像裁成带白描边的圆形贴到图上，缺失/失败时静默跳过。"""
    if not avatar_path or not os.path.exists(avatar_path):
        return
    try:
        av = Image.open(avatar_path).convert('RGBA').resize((size, size))
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(av, (0, 0), mask)
        ImageDraw.Draw(out).ellipse([1, 1, size - 1, size - 1], outline=ring, width=2)
        img.alpha_composite(out, dest=(int(xy[0]), int(xy[1])))
    except Exception:
        pass


# ------------------------------------------------------------ 精修小件
def tint(color, ratio):
    """把颜色向白色提亮 ratio（0~1），仿 CSS color-mix(in srgb, c, white x%)。"""
    r, g, b = color[0], color[1], color[2]
    return (int(r + (255 - r) * ratio),
            int(g + (255 - g) * ratio),
            int(b + (255 - b) * ratio))


def mix(c0, c1, t):
    """线性混色 c0 → c1（t=0 返回 c0，t=1 返回 c1）。"""
    return (int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t))


def top_wash(w, h, box, radius, color, height, max_alpha=90):
    """卡片顶部同色系渐变洗层（向下淡出），已按圆角矩形裁剪。

    用于给白卡顶部垫一层柔和的主题色，让标题区不显得空。
    """
    height = min(int(height), box[3] - box[1])
    grad = Image.new('RGBA', (1, height), (0, 0, 0, 0))
    for y in range(height):
        k = 1 - y / height if height > 1 else 0
        grad.putpixel((0, y), (color[0], color[1], color[2], int(max_alpha * k)))
    grad = grad.resize((box[2] - box[0], height))

    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    layer.paste(grad, (box[0], box[1]))
    full = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    full.paste(layer, (0, 0), mask)
    return full


_NUM_SPLIT = re.compile(r'(\d[\d.,:%]*(?:\.\d+)?%?)')


def number_runs(text):
    """把文本按「数字段 / 其他」切分为 [(片段, 是否数字)]，数字段单独上色。"""
    return [(p, bool(_NUM_SPLIT.fullmatch(p))) for p in _NUM_SPLIT.split(text) if p]


def runs_width(draw, runs, base_font, num_font):
    """顺序绘制前先量总宽（number_runs 的配套测量）。"""
    return sum(draw.textlength(t, font=num_font if is_num else base_font)
               for t, is_num in runs)
