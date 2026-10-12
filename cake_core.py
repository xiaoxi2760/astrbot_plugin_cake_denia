"""cake_core：今天你喂娅娅小蛋糕了吗 —— 图片渲染与数据查询核心。

粉色系主题、🍰 蛋糕标记、娅娅文案，双渲染后端（PIL / HTML）。
"""
import aiosqlite
import calendar
import os
import io
import re
import time
import asyncio
from datetime import date, datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from astrbot.api import logger

from . import render_common as rc

from .resources.texts import (
    CALENDAR_EMPTY, CALENDAR_ERROR, CALENDAR_FONT_MISSING,
    CALENDAR_SERVER_FONT_MISSING, CALENDAR_UNKNOWN_ERROR,
    MONTHLY_TOP, MONTHLY_PEAK_GE3, MONTHLY_PEAK_2,
    MONTHLY_STREAK_GE7, MONTHLY_STREAK_GE4, MONTHLY_STREAK_GE2, MONTHLY_RATE,
    MONTHLY_YAYA_GE13, MONTHLY_YAYA_GE07, MONTHLY_YAYA_GE04,
    MONTHLY_YAYA_GE01, MONTHLY_YAYA_LOW, MONTHLY_TIP,
    YEARLY_TOP, YEARLY_MAX_MONTH, YEARLY_RATE_GT25, YEARLY_RATE_GT15,
    YEARLY_RATE_GT8, YEARLY_RATE_LOW, YEARLY_END, ANALYSIS_HEADER,
    CAREER_TITLE, CAREER_FEEDER, CAREER_QUOTE, CAREER_SECTIONS,
    CAREER_FIRST, CAREER_AVG_DAILY, CAREER_AVG_INTERVAL, CAREER_AVG_ZERO,
    CAREER_TOTAL, CAREER_DAYS, CAREER_MAX_DAY, CAREER_MAX_MONTH,
    CAREER_MIN_MONTH, CAREER_REST, CAREER_STATUS, CAREER_COMMENT_WRAP,
    RANKING_TITLE, RANKING_SUBTITLE, RANKING_TODAY, RANKING_MONTH,
    RANKING_COL_SELF, RANKING_COL_RECEIVED, RANKING_COL_HELP,
    RANKING_PAGE, RANKING_PAGE_LAST,
)

# 娅娅主题色（粉色系）
PINK = (255, 182, 193)        # 浅粉
PINK_DEEP = (219, 112, 147)   # 深粉
PINK_BG = (255, 240, 245)     # 极浅粉背景
PINK_LIGHT = (255, 228, 235)  # 浅粉分隔
CHOCO = (101, 67, 33)         # 巧克力棕（文字）
CAKE_RED = (233, 84, 107)     # 蛋糕红（计数/勾）
CAKE_EMOJI = "\U0001F370"     # 🍰


class CakeCore:

    # 系统回退中文字体（resources/fonts 与插件根目录均无字体时使用）
    SYSTEM_FONT_CANDIDATES = [
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]

    def __init__(self, font_path: str, db_path: str, temp_dir: str, render_backend: str = "html",
                 theme_preset: str = "custom", avatar_dir: str = ""):
        self._plugin_dir = os.path.dirname(font_path) if font_path else os.getcwd()
        self.font_path = None
        self.db_path = db_path
        self.temp_dir = temp_dir
        # 头像缓存目录（HTML 排行榜渲染器需要；为空则回落到 temp_dir）
        self.avatar_cache_dir = avatar_dir or temp_dir
        self._emoji_font = None
        self._init_fonts()
        # 渲染后端：html（Playwright + 系统 Chrome，默认）/ pil（纯 Pillow 无依赖）
        self.render_backend = render_backend if render_backend in ("pil", "html") else "html"
        # 日历主题：预设 white-1/white-2/black-1/black-2 或 custom（读 resources/theme.json）
        from .theme import load_theme
        self.theme_preset = theme_preset
        self.theme = load_theme(theme_preset)
        from .render_pil.calendar import PilCalendarRenderer
        self._pil_renderer = PilCalendarRenderer(self, self.theme)
        # 日历 / 排行榜 / 报告 / 生涯四类图共用同一后端选择，均支持 HTML 优先 + PIL 降级
        self._html_renderers = None
        if self.render_backend == "html":
            self._init_html_renderers()
        # 达妮娅（暗夜·black-1）彩蛋渲染器：懒加载，仅在彩蛋触发时使用
        self._dark_renderer = None
        # 达妮娅暗夜主题的 PIL 渲染器：HTML 后端失败降级时用（始终纯 PIL，不碰 Playwright）
        self._dark_pil_renderer = None

    def _init_html_renderers(self):
        """初始化四类图的 HTML 渲染器（缺失依赖时静默退回 PIL）。"""
        if self._html_renderers is not None:
            return
        renderers = {}
        try:
            from .render_html.calendar import HtmlCalendarRenderer
            renderers['calendar'] = HtmlCalendarRenderer(self, self.theme)
        except Exception as e:
            logger.error(f"HTML 日历渲染器初始化失败，将使用 PIL：{e}")
        try:
            from .render_html.ranking import HtmlRankingRenderer
            renderers['ranking'] = HtmlRankingRenderer(self, self.theme)
        except Exception as e:
            logger.error(f"HTML 排行榜渲染器初始化失败，将使用 PIL：{e}")
        try:
            from .render_html.analysis import HtmlAnalysisRenderer
            renderers['analysis'] = HtmlAnalysisRenderer(self, self.theme)
        except Exception as e:
            logger.error(f"HTML 报告渲染器初始化失败，将使用 PIL：{e}")
        try:
            from .render_html.career import HtmlCareerRenderer
            renderers['career'] = HtmlCareerRenderer(self, self.theme)
        except Exception as e:
            logger.error(f"HTML 生涯渲染器初始化失败，将使用 PIL：{e}")
        self._html_renderers = renderers

    def _get_html_renderer(self, kind):
        """取指定类型的 HTML 渲染器；未启用或不可用返回 None（调用方降级 PIL）。"""
        if self.render_backend != "html":
            return None
        if self._html_renderers is None:
            self._init_html_renderers()
        return self._html_renderers.get(kind)

    def _close_html_browser_on_error(self):
        """HTML 渲染异常时重置浏览器单例，避免坏实例被后续渲染复用。"""
        try:
            from .render_html.calendar import _close_browser
            _close_browser()
        except Exception:
            pass


    def _get_dark_renderer(self):
        """达妮娅暗夜渲染器：black-1 主题，用于达妮娅彩蛋日历（与配置主题无关）。"""
        if self._dark_renderer is None:
            from .theme import load_theme
            dark_theme = load_theme('black-1')
            from .render_pil.calendar import PilCalendarRenderer
            if self.render_backend == "html":
                from .render_html.calendar import HtmlCalendarRenderer
                self._dark_renderer = HtmlCalendarRenderer(self, dark_theme)
            else:
                self._dark_renderer = PilCalendarRenderer(self, dark_theme)
        return self._dark_renderer

    def _get_dark_pil_renderer(self):
        """达妮娅暗夜主题的 PIL 渲染器（HTML 后端降级专用，不触发 Playwright）。"""
        if self._dark_pil_renderer is None:
            from .theme import load_theme
            from .render_pil.calendar import PilCalendarRenderer
            self._dark_pil_renderer = PilCalendarRenderer(self, load_theme('black-1'))
        return self._dark_pil_renderer

    def _init_fonts(self):
        """扫描字体候选并初始化（可重复调用以重载下载后的字体）。"""
        self.font_path = None
        self._emoji_font = None
        # 中文字体候选：resources/fonts -> 插件根 -> 系统字体
        font_candidates = [
            os.path.join(self._plugin_dir, 'resources', 'fonts', 'font.ttf'),
            os.path.join(self._plugin_dir, 'font.ttf'),
        ] + self.SYSTEM_FONT_CANDIDATES
        for fp in font_candidates:
            if fp and os.path.exists(fp):
                try:
                    ImageFont.truetype(fp, 20)
                    self.font_path = fp
                    break
                except Exception:
                    continue
        # emoji 字体候选：resources/fonts -> 插件根 -> 系统
        emoji_candidates = [
            os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf'),
            os.path.join(self._plugin_dir, 'emoji.ttf'),
            'C:/Windows/Fonts/seguiemj.ttf',
            '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
            '/usr/share/fonts/noto/NotoColorEmoji.ttf',
        ]
        for ep in emoji_candidates:
            if os.path.exists(ep):
                try:
                    self._emoji_font = ImageFont.truetype(ep, 20)
                    self._emoji_path = ep
                    break
                except Exception:
                    continue

    # ------------------------------------------------------------ 字体自动下载
    def _download_file(self, url: str, dest: str) -> bool:
        """同步下载单个文件到目标路径，失败返回 False。"""
        import urllib.request
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data:
                return False
            with open(dest, 'wb') as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error(f"下载 {url} 失败: {e}")
            return False

    async def ensure_fonts(self, font_url: str = None, emoji_url: str = None) -> None:
        """resources/fonts 缺失时自动下载默认字体（失败静默，不阻塞使用）。

        Args:
            font_url: 中文字体下载地址，None 表示不下载。
            emoji_url: emoji 字体下载地址，None 表示不下载。
        """
        if font_url:
            target = os.path.join(self._plugin_dir, 'resources', 'fonts', 'font.ttf')
            if not os.path.exists(target):
                ok = await asyncio.to_thread(self._download_file, font_url, target)
                if ok:
                    logger.info("默认中文字体下载成功")
        if emoji_url and self._emoji_font is None:
            target = os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
            if not os.path.exists(target):
                ok = await asyncio.to_thread(self._download_file, emoji_url, target)
                if ok:
                    logger.info("默认 emoji 字体下载成功")
        if font_url or emoji_url:
            self._init_fonts()

    def _draw_text(self, draw, xy, text, font, fill, anchor=None):
        """逐字符绘制文本，emoji 用 emoji 字体，支持 embedded_color。"""
        if not any(ord(c) > 0xFFFF for c in text):
            draw.text(xy, text, font=font, fill=fill, anchor=anchor)
            return
        emoji_font = self._emoji_font
        try:
            size = getattr(font, 'size', 20) or 20
            ep = getattr(self, '_emoji_path', None) or os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
            if os.path.exists(ep):
                emoji_font = ImageFont.truetype(ep, size)
        except Exception:
            if emoji_font is None:
                draw.text(xy, text, font=font, fill=fill, anchor=anchor)
                return
        if anchor == "mm":
            total_w = 0
            for c in text:
                f = emoji_font if ord(c) > 0xFFFF else font
                total_w += draw.textlength(c, font=f)
            cx = xy[0] - total_w / 2
            for c in text:
                f = emoji_font if ord(c) > 0xFFFF else font
                if ord(c) > 0xFFFF:
                    draw.text((cx, xy[1]), c, font=f, fill=fill, anchor="mm", embedded_color=True)
                else:
                    draw.text((cx, xy[1]), c, font=f, fill=fill, anchor="mm")
                cx += draw.textlength(c, font=f)
        elif anchor == "mt":
            total_w = 0
            for c in text:
                f = emoji_font if ord(c) > 0xFFFF else font
                total_w += draw.textlength(c, font=f)
            cx = xy[0] - total_w / 2
            try:
                main_bb = draw.textbbox((0, 0), '中', font=font)
                main_top = main_bb[1]
            except Exception:
                main_top = 0
            for c in text:
                f = emoji_font if ord(c) > 0xFFFF else font
                if ord(c) > 0xFFFF:
                    e_bb = draw.textbbox((0, 0), c, font=f)
                    e_top = e_bb[1]
                    draw.text((cx, xy[1] + main_top - e_top), c, font=f, fill=fill, anchor="la", embedded_color=True)
                else:
                    draw.text((cx, xy[1]), c, font=f, fill=fill, anchor="lt")
                cx += draw.textlength(c, font=f)
        else:
            cx, cy = xy
            try:
                main_bb = draw.textbbox((0, 0), '中', font=font)
                main_top = main_bb[1]
            except Exception:
                main_top = 0
            for c in text:
                f = emoji_font if ord(c) > 0xFFFF else font
                if ord(c) > 0xFFFF:
                    e_bb = draw.textbbox((0, 0), c, font=f)
                    e_top = e_bb[1]
                    draw.text((cx, cy + main_top - e_top), c, font=f, fill=fill, anchor="la", embedded_color=True)
                else:
                    draw.text((cx, cy), c, font=f, fill=fill, anchor="la")
                cx += draw.textlength(c, font=f)

    async def _get_group_members(self, event, group_id: str) -> list:
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    members_info = await event.bot.api.call_action('get_group_member_list', group_id=int(group_id))
                    return members_info if members_info else []
            return []
        except Exception as e:
            logger.error(f"获取群成员列表失败: {e}")
            return []

    async def _get_user_name(self, event, user_id: str) -> str:
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    group_id = event.get_group_id()
                    if group_id:
                        member_info = await event.bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
                        nickname = member_info.get("card") or member_info.get("nickname")
                        return nickname.strip() or str(user_id)
                    else:
                        stranger_info = await event.bot.get_stranger_info(user_id=int(user_id))
                        return stranger_info.get("nickname") or str(user_id)
            return str(user_id)
        except Exception:
            return str(user_id)

    def _draw_denia_logo(self, img, draw, size=90, xy=None):
        """顶部娅娅图案：优先 resources/denia.png（或插件根 denia.png），否则大号 🍰 emoji。"""
        denia_png = None
        for cand in (os.path.join(self._plugin_dir, 'resources', 'denia.png'),
                     os.path.join(self._plugin_dir, 'denia.png')):
            if os.path.exists(cand):
                denia_png = cand
                break
        if denia_png:
            try:
                av = Image.open(denia_png).convert("RGBA")
                av = av.resize((size, size))
                mask = Image.new("L", (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
                av_rgba = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                av_rgba.paste(av, (0, 0), mask)
                img.paste(av_rgba, xy, av_rgba)
                return
            except Exception:
                pass
        try:
            ep = getattr(self, '_emoji_path', None) or os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
            if os.path.exists(ep):
                ef = ImageFont.truetype(ep, size)
                w = draw.textlength(CAKE_EMOJI, font=ef)
                # 无彩色 emoji 字体时用蛋糕红兜底（fill=(0,0,0,0) 会画成全透明）
                draw.text((xy[0] + size / 2 - w / 2, xy[1]), CAKE_EMOJI, font=ef,
                          fill=CAKE_RED, embedded_color=True)
        except Exception:
            pass

    async def _get_user_period_data(self, user_id: str, year: int, month: int) -> dict:
        period_data = {}
        target_month_str = f"{year}-{month:02d}"
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with (await conn.execute(
                    "SELECT checkin_date, cake_count FROM checkin WHERE user_id = ? AND strftime('%Y-%m', checkin_date) = ?",
                    (user_id, target_month_str)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        day = int(row[0].split('-')[2])
                        period_data[day] = row[1]
        except Exception as e:
            logger.error(f"查询用户 {user_id} 的 {year}年{month}月数据失败: {e}")
        return period_data

    async def _get_user_yearly_data(self, user_id: str, year: int) -> dict:
        yearly_data = {}
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with (await conn.execute(
                    "SELECT checkin_date, cake_count FROM checkin WHERE user_id = ? AND strftime('%Y', checkin_date) = ?",
                    (user_id, str(year))
                )) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        date_str = row[0]
                        _, month, day = date_str.split('-')
                        month = int(month)
                        day = int(day)
                        if month not in yearly_data:
                            yearly_data[month] = {}
                        yearly_data[month][day] = row[1]
        except Exception as e:
            logger.error(f"查询用户 {user_id} 的 {year}年数据失败: {e}")
        return yearly_data

    async def _generate_monthly_analysis_report(self, user_name: str, year: int, month: int, period_data: dict) -> tuple:
        if not period_data:
            return "", 0.0
        total_days = len(period_data)
        total_cakes = sum(period_data.values())
        max_day_num, max_day_count = max(period_data.items(), key=lambda x: x[1])
        sorted_days = sorted(period_data.keys())
        max_consecutive = 1
        current = 1
        for i in range(1, len(sorted_days)):
            if sorted_days[i] == sorted_days[i-1] + 1:
                current += 1
                max_consecutive = max(max_consecutive, current)
            else:
                current = 1
        days_in_month = calendar.monthrange(year, month)[1]
        today = date.today()
        analysis_days = today.day if year == today.year and month == today.month else days_in_month
        checkin_rate = total_days / analysis_days if analysis_days > 0 else 0
        freq_per_day = total_cakes / analysis_days if analysis_days > 0 else 0

        report = MONTHLY_TOP.format(total_days=total_days, total_cakes=total_cakes) + "\n"
        if max_day_count > 1:
            if max_day_count >= 3:
                report += MONTHLY_PEAK_GE3.format(day=max_day_num, count=max_day_count) + "\n"
            elif max_day_count == 2:
                report += MONTHLY_PEAK_2.format(day=max_day_num) + "\n"
        if max_consecutive >= 7:
            report += MONTHLY_STREAK_GE7.format(n=max_consecutive) + "\n"
        elif max_consecutive >= 4:
            report += MONTHLY_STREAK_GE4.format(n=max_consecutive) + "\n"
        elif max_consecutive >= 2:
            report += MONTHLY_STREAK_GE2.format(n=max_consecutive) + "\n"
        report += MONTHLY_RATE.format(rate=f"{checkin_rate:.1%}") + "\n\n"
        if freq_per_day >= 1.3:
            report += MONTHLY_YAYA_GE13
        elif freq_per_day >= 0.7:
            report += MONTHLY_YAYA_GE07
        elif freq_per_day >= 0.4:
            report += MONTHLY_YAYA_GE04
        elif freq_per_day >= 0.1:
            report += MONTHLY_YAYA_GE01
        else:
            report += MONTHLY_YAYA_LOW
        report += MONTHLY_TIP
        return report, checkin_rate

    async def _generate_yearly_analysis_report(self, user_name: str, year: int, yearly_data: dict) -> str:
        if not yearly_data:
            return ""
        total_months = len(yearly_data)
        total_days = sum(len(days) for days in yearly_data.values())
        total_cakes = sum(sum(days.values()) for days in yearly_data.values())
        max_month = max(yearly_data.items(), key=lambda x: sum(x[1].values()))
        max_month_num, max_data = max_month
        max_month_cakes = sum(max_data.values())
        report = YEARLY_TOP.format(months=total_months, days=total_days, cakes=total_cakes) + "\n"
        report += YEARLY_MAX_MONTH.format(month=max_month_num, cakes=max_month_cakes) + "\n\n"
        avg_per_month = total_cakes / max(total_months, 1)
        if avg_per_month > 25:
            report += YEARLY_RATE_GT25
        elif avg_per_month > 15:
            report += YEARLY_RATE_GT15
        elif avg_per_month > 8:
            report += YEARLY_RATE_GT8
        else:
            report += YEARLY_RATE_LOW
        report += YEARLY_END
        return report

    @staticmethod
    def _safe_file_component(name: str) -> str:
        """把昵称/期间变为安全的文件名片段，防止非法字符与路径穿越。"""
        safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
        safe = safe.strip().strip('.')
        return safe or 'unnamed'

    def _palette(self):
        """当前主题调色板（与日历渲染共用，保证四张图同一套设计语言）。"""
        from .render_common import ThemePalette
        p = getattr(self, '_theme_palette', None)
        if p is None:
            p = ThemePalette(getattr(self, 'theme', None))
            self._theme_palette = p
        return p

    def _wrap_lines(self, draw, text, font, max_w):
        """按像素宽度折行（中英文混排逐字符测量，避免长句溢出画布）。"""
        if not text:
            return ['']
        lines, cur = [], ''
        for ch in text:
            if ch == '\n':
                lines.append(cur)
                cur = ''
                continue
            probe = cur + ch
            if self._measure_text_width(draw, probe, font) > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = probe
        lines.append(cur)
        return lines

    def _create_analysis_image(self, user_name: str, target_period: str, analysis_result: str,
                               checkin_rate: float = 0.0, system_name: str = "蛋糕") -> str:
        """投喂报告图：白玻璃卡 + 主题色洗层 + 旋钮进度条 + 正文气泡芯片。

        render_backend=html 时优先 HTML/CSS + Chrome，失败自动降级 PIL。
        """
        html_renderer = self._get_html_renderer('analysis')
        if html_renderer is not None:
            try:
                return html_renderer.render(
                    user_name, target_period, analysis_result, checkin_rate, system_name)
            except Exception as e:
                logger.error(f"HTML 报告渲染失败，降级 PIL: {e}")
                self._close_html_browser_on_error()
        pal = self._palette()
        W, MARGIN = 750, 34
        CARD_W = W - MARGIN * 2
        CHIP_MAX_W = CARD_W - 72          # 芯片内文字可用宽度（两侧留白）
        f_title = ImageFont.truetype(self.font_path, 30)
        f_sub = ImageFont.truetype(self.font_path, 15)
        f_hero = ImageFont.truetype(self.font_path, 20)
        f_body = ImageFont.truetype(self.font_path, 18)
        f_lab = ImageFont.truetype(self.font_path, 16)
        f_tip = ImageFont.truetype(self.font_path, 15)

        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        card_rgb = pal.card_fill[:3]
        chip_fill = rc.mix(pal.feed_top, card_rgb, 0.78)
        chip_border = rc.mix(pal.feed_border, card_rgb, 0.5)

        # ---- 正文分行 + 分类（hero 首行 / quote 引语 / tip 贴士 / normal）----
        QUOTE_PREFIX = ('娅娅：', '达妮娅：', '年度评价：')
        blocks = []          # (kind, [折行后文本])
        kind = 'normal'
        for raw in analysis_result.split('\n'):
            line = raw.strip()
            if not line:
                blocks.append(('gap', []))
                kind = 'normal'
                continue
            if line.startswith(QUOTE_PREFIX):
                kind = 'quote'
            elif line.startswith('小贴士：'):
                kind = 'tip'
            font = {'hero': f_hero, 'quote': f_body, 'tip': f_tip}.get(kind, f_body)
            blocks.append((kind, self._wrap_lines(measure, line, font, CHIP_MAX_W)))
        for i, (k, lines) in enumerate(blocks):
            if k == 'normal':
                blocks[i] = ('hero', lines)
                break

        def block_font(k):
            return {'hero': f_hero, 'quote': f_body, 'tip': f_tip}.get(k, f_body)

        def block_h(k, lines):
            if k == 'gap':
                return 10
            font = block_font(k)
            vpad = 10 if k == 'hero' else (9 if k == 'quote' else 8)
            return len(lines) * (font.size + 10) + vpad * 2 + 9   # 尾随 9 = 块间距

        # ---- 布局高度：头部 100 + 进度条区 68 + 正文 + 底部收尾 26 ----
        TITLE_ZONE, RATE_ZONE, FOOTER_H = 100, 68, 26
        body_h = sum(block_h(k, ls) for k, ls in blocks)
        card_h = TITLE_ZONE + RATE_ZONE + body_h + FOOTER_H
        H = card_h + MARGIN * 2

        CARD_BOX = (MARGIN, MARGIN, W - MARGIN, MARGIN + card_h)
        img = rc.scene(W, H, pal, card_box=CARD_BOX, card_radius=26,
                       shadow_alpha=90, shadow_spread=1.25)
        img.alpha_composite(rc.top_wash(W, H, CARD_BOX, 26, pal.feed_top, 150, 80))
        draw = ImageDraw.Draw(img)

        # ---- 标题 + 副标题 + 渐变下划线 ----
        header_text = ANALYSIS_HEADER.format(period=target_period, name=user_name)
        self._draw_text(draw, (W / 2, MARGIN + 42), header_text,
                        font=f_title, fill=rc.darken(pal.title, 0.88), anchor='mm')
        self._draw_text(draw, (W / 2, MARGIN + 72), f'{target_period}的投喂报告',
                        font=f_sub, fill=pal.subtitle, anchor='mm')
        ul_w, ul_h = 52, 5
        img.alpha_composite(rc.pill(ul_w, ul_h, pal.feed_top, pal.feed_bottom, ul_h // 2),
                            dest=(int(W / 2 - ul_w / 2), MARGIN + 86))

        # ---- 投喂率：标签 + 圆角轨道 + 渐变填充 + 白色旋钮 ----
        rate_pct = max(0, min(1.0, float(checkin_rate or 0)))
        bar_w = CARD_W - 44
        bar_x = MARGIN + 22
        bar_y = MARGIN + TITLE_ZONE + 26
        bar_h = 18
        self._draw_text(draw, (bar_x, bar_y - 7), '本月投喂率', font=f_lab,
                        fill=pal.subtitle, anchor='ls')
        self._draw_text(draw, (bar_x + bar_w, bar_y - 7), f'{rate_pct:.0%}',
                        font=f_lab, fill=pal.accent_text, anchor='rs')
        track = rc.pill(bar_w, bar_h, pal.empty_bg, pal.empty_bg, bar_h // 2)
        img.alpha_composite(track, dest=(bar_x, bar_y))
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w - 1, bar_y + bar_h - 1],
                               radius=bar_h // 2, outline=pal.empty_border, width=1)
        filled_w = int(bar_w * rate_pct)
        if filled_w > bar_h:
            fill = rc.pill(filled_w, bar_h, pal.feed_top, pal.feed_bottom, bar_h // 2)
            img.alpha_composite(fill, dest=(bar_x, bar_y))
        if rate_pct > 0:
            kx = min(max(bar_x + filled_w, bar_x + bar_h // 2 + 2),
                     bar_x + bar_w - bar_h // 2 - 2)
            ky = bar_y + bar_h / 2
            draw.ellipse([kx - 11, ky - 11, kx + 11, ky + 11],
                         fill=(255, 255, 255), outline=pal.feed_bottom, width=4)

        # ---- 正文气泡芯片 ----
        body_top = MARGIN + TITLE_ZONE + RATE_ZONE
        y = body_top
        for kind, lines in blocks:
            if kind == 'gap':
                y += 10
                continue
            font = block_font(kind)
            line_h = font.size + 10
            vpad = 10 if kind == 'hero' else (9 if kind == 'quote' else 8)
            block_h_px = len(lines) * line_h + vpad * 2
            num_color = pal.accent_text
            if kind == 'tip':
                ty = y + vpad
                for ln in lines:
                    self._draw_text(draw, (W / 2, ty), ln, font=font,
                                    fill=pal.subtitle, anchor='mt')
                    ty += line_h
                y += block_h_px + 9
                continue
            runs_list = [rc.number_runs(ln) for ln in lines]
            w_max = max(rc.runs_width(draw, runs, font, font) for runs in runs_list)
            chip_w = min(w_max + 40, CARD_W - 16)
            cx0 = (W - chip_w) / 2
            box = [cx0, y, cx0 + chip_w, y + block_h_px]
            if kind == 'hero':
                grad = rc.pill(int(chip_w), int(block_h_px),
                               rc.mix(pal.feed_top, card_rgb, 0.45),
                               rc.mix(pal.feed_bottom, card_rgb, 0.6), 16)
                img.alpha_composite(grad, dest=(int(cx0), int(y)))
                draw.rounded_rectangle(box, radius=16,
                                       outline=rc.mix(pal.feed_border, card_rgb, 0.35), width=1)
            else:
                draw.rounded_rectangle(box, radius=16, fill=chip_fill + (255,),
                                       outline=chip_border + (255,), width=1)
            if kind == 'quote':
                draw.rounded_rectangle(
                    [box[0] + 12, box[1] + vpad + 2, box[0] + 16, box[3] - vpad - 2],
                    radius=2, fill=pal.accent + (255,))
            ty = y + vpad
            tx = W / 2 - w_max / 2
            for runs in runs_list:
                cx = tx
                for text, is_num in runs:
                    # 正文均为固定模板文案（无 emoji），直接逐段绘制以给数字换色
                    draw.text((cx, ty + line_h / 2), text, font=font,
                              fill=num_color if is_num else pal.body, anchor='lm')
                    cx += draw.textlength(text, font=font)
                ty += line_h
            y += block_h_px + 9

        # ---- 底部收尾三点 ----
        dot_y = MARGIN + card_h - 18
        for i, c in enumerate((pal.accent, pal.feed_border, pal.empty_border)):
            dx = W / 2 + (i - 1) * 14
            draw.ellipse([dx - 2.5, dot_y - 2.5, dx + 2.5, dot_y + 2.5],
                         fill=c + (255,))

        out_path = self._analysis_path(user_name, target_period)
        img.convert('RGB').save(out_path, format='PNG')
        return out_path

    def _analysis_path(self, user_name: str, target_period: str) -> str:
        safe_user = self._safe_file_component(user_name)
        safe_period = self._safe_file_component(target_period.replace('年', '_').replace('月', ''))
        return os.path.join(self.temp_dir,
                            f"analysis_{safe_user}_{safe_period}_{int(time.time())}.png")

    def _create_career_image(self, user_name: str, stats: dict, system_name: str = "娅娅") -> str:
        """生涯档案图：白玻璃卡 + 渐变 KPI 三宫格 + 图标分区卡 + 标签值对齐行。

        render_backend=html 时优先 HTML/CSS + Chrome，失败自动降级 PIL。
        """
        html_renderer = self._get_html_renderer('career')
        if html_renderer is not None:
            try:
                return html_renderer.render(user_name, stats, system_name)
            except Exception as e:
                logger.error(f"HTML 生涯渲染失败，降级 PIL: {e}")
                self._close_html_browser_on_error()
        pal = self._palette()
        W, MARGIN = 800, 40
        CARD_W = W - MARGIN * 2
        f_title = ImageFont.truetype(self.font_path, 34)
        f_sub = ImageFont.truetype(self.font_path, 17)
        f_quote = ImageFont.truetype(self.font_path, 20)
        f_sec = ImageFont.truetype(self.font_path, 20)
        f_body = ImageFont.truetype(self.font_path, 18)
        f_note = ImageFont.truetype(self.font_path, 15)
        f_kpi_num = ImageFont.truetype(self.font_path, 32)
        f_kpi_cap = ImageFont.truetype(self.font_path, 14)

        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        card_rgb = pal.card_fill[:3]

        # ---------- 组装分区内容（口径与 HTML 版一致）----------
        sections = []        # (标题, [(文本, 是否注释)])

        def add(title, items):
            sections.append((title, [(t, c) for t, c in items if t]))

        add(CAREER_SECTIONS[0], [(CAREER_FIRST.format(
            date=stats['first_date_str'], days=stats['total_span_days']), False)])

        avg_display = (CAREER_AVG_DAILY.format(avg=f"{stats['daily_avg']:.2f}")
                       if stats['daily_avg'] > 1 else
                       CAREER_AVG_INTERVAL.format(interval=f"{1 / stats['daily_avg']:.1f}")
                       if stats['daily_avg'] > 0 else CAREER_AVG_ZERO)
        add(CAREER_SECTIONS[1], [
            (CAREER_TOTAL.format(count=stats['total_count']), False),
            (CAREER_DAYS.format(days=stats['total_days'],
                                ratio=f"{stats['active_ratio']:.1f}"), False),
            (avg_display, False)])

        peak = []
        if stats['max_day_count'] > 1:
            peak.append((CAREER_MAX_DAY.format(
                date=stats['max_day_date'], count=stats['max_day_count']), False))
        if stats['max_month_count'] > 0:
            peak.append((CAREER_MAX_MONTH.format(
                month=stats['max_month_str'], count=stats['max_month_count']), False))
        add(CAREER_SECTIONS[2], peak)

        miss = [(CAREER_MIN_MONTH.format(month=stats['min_month_str'],
                                         count=stats['min_month_count']), False),
                (CAREER_REST.format(text=stats['rest_period_str']), False)]
        if stats['sage_comment']:
            miss.append((CAREER_COMMENT_WRAP.format(text=stats['sage_comment']), True))
        add(CAREER_SECTIONS[3], miss)

        status = [(CAREER_STATUS.format(days=stats['status_day']), False)]
        if stats['status_comment']:
            status.append((CAREER_COMMENT_WRAP.format(text=stats['status_comment']), True))
        add(CAREER_SECTIONS[4], status)

        # ---------- 度量：冒号行拆「标签/值」，值按区内最大标签宽对齐 ----------
        ROW_L = ROW_R = 26
        HEAD_H, KPI_H = 40, 108
        sec_layouts = []
        for title, rows in sections:
            lab_w = 0
            for text, is_note in rows:
                if not is_note and '：' in text:
                    lab_w = max(lab_w, measure.textlength(text.split('：', 1)[0] + '：',
                                                          font=f_body))
            val_x = ROW_L + int(lab_w) + 6
            items = []
            for text, is_note in rows:
                font = f_note if is_note else f_body
                lh = 24 if is_note else 30
                if not is_note and '：' in text:
                    label, value = text.split('：', 1)
                    avail = max(CARD_W - ROW_L - ROW_R - (val_x - ROW_L), 80)
                    vlines = self._wrap_lines(measure, value, font, avail)
                    items.append(('kv', label, vlines, font, lh))
                else:
                    lines = self._wrap_lines(measure, text, font, CARD_W - ROW_L - ROW_R)
                    items.append(('note' if is_note else 'plain', None, lines, font, lh))
            rows_h = sum(len(it[2]) * it[4] for it in items)
            sec_layouts.append((title, items, 12 + HEAD_H + rows_h + 14))

        # ---------- 总高度 ----------
        header_h = 148
        kpi_gap, sec_gap, card_pad_bottom = 20, 14, 8
        card_h = (header_h + KPI_H + kpi_gap
                  + sum(h for _t, _i, h in sec_layouts)
                  + sec_gap * (len(sec_layouts) - 1) + card_pad_bottom)
        H = card_h + MARGIN * 2

        CARD_BOX = (MARGIN, MARGIN, W - MARGIN, MARGIN + card_h)
        img = rc.scene(W, H, pal, card_box=CARD_BOX, card_radius=28,
                       shadow_alpha=95, shadow_spread=1.3)
        img.alpha_composite(rc.top_wash(W, H, CARD_BOX, 28, pal.feed_top, 170, 70))
        draw = ImageDraw.Draw(img)

        # ---------- 头部 ----------
        cx = W / 2
        self._draw_text(draw, (cx, MARGIN + 40), CAREER_TITLE, font=f_title,
                        fill=rc.darken(pal.title, 0.9), anchor='mm')
        self._draw_text(draw, (cx, MARGIN + 74), CAREER_FEEDER.format(name=user_name),
                        font=f_sub, fill=pal.subtitle, anchor='mm')
        quote_text = CAREER_QUOTE.format(comment=stats['summary_comment'])
        qw = measure.textlength(quote_text, font=f_quote)
        qp_w, qp_h = min(qw + 56, CARD_W - 30), 36
        qp_x, qp_y = (W - qp_w) / 2, MARGIN + 94
        draw.rounded_rectangle([qp_x, qp_y, qp_x + qp_w, qp_y + qp_h], radius=qp_h // 2,
                               fill=rc.mix(pal.feed_top, card_rgb, 0.62) + (255,),
                               outline=rc.mix(pal.feed_border, card_rgb, 0.35) + (255,), width=1)
        self._draw_text(draw, (W / 2, qp_y + qp_h / 2 + 1), quote_text, font=f_quote,
                        fill=rc.darken(pal.weekend, 0.85), anchor='mm')

        # ---------- 指标三宫格（竖直渐变卡）----------
        kpi_y = MARGIN + header_h
        kpis = [
            (str(stats['total_count']), '累计蛋糕'),
            (str(stats['total_days']), '投喂天数'),
            (f"{stats['daily_avg']:.2f}", '日均投喂'),
        ]
        gap = 14
        kw = (CARD_W - 24 * 2 - gap * 2) // 3
        kx = MARGIN + 24
        for cap_val, cap_name in kpis:
            box = (kx, kpi_y, kx + kw, kpi_y + KPI_H)
            grad = rc.pill(kw, KPI_H,
                           rc.mix(pal.feed_top, card_rgb, 0.55),
                           rc.mix(pal.feed_bottom, card_rgb, 0.75), 18)
            kmask = Image.new('L', (kw, KPI_H), 0)
            ImageDraw.Draw(kmask).rounded_rectangle(
                [0, 0, kw - 1, KPI_H - 1], radius=18, fill=255)
            klayer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            klayer.paste(grad, (kx, kpi_y), kmask)
            img.alpha_composite(klayer)
            draw.rounded_rectangle(box, radius=18,
                                   outline=rc.mix(pal.feed_border, card_rgb, 0.4) + (255,),
                                   width=1)
            self._draw_text(draw, (kx + kw / 2, kpi_y + KPI_H / 2 - 13), cap_val,
                            font=f_kpi_num, fill=pal.accent_text, anchor='mm')
            self._draw_text(draw, (kx + kw / 2, kpi_y + KPI_H / 2 + 25), cap_name,
                            font=f_kpi_cap, fill=pal.subtitle, anchor='mm')
            kx += kw + gap

        # ---------- 分区卡片（图标 + 标题 + 分隔线 + 对齐行）----------
        y = kpi_y + KPI_H + kpi_gap
        div_col = rc.mix(pal.empty_border, card_rgb, 0.2)
        for (title, items, sh) in sec_layouts:
            box = (MARGIN, y, W - MARGIN, y + sh)
            img.alpha_composite(rc.rounded_card_layer(
                W, H, box, radius=18,
                fill=rc.mix(pal.feed_top, card_rgb, 0.93) + (255,),
                border=rc.mix(pal.feed_border, card_rgb, 0.35), border_w=1,
                shadow=True, shadow_color=rc.darken(pal.weekend, 0.45, 0),
                shadow_blur=9, shadow_offset=3,
                shadow_alpha=70, shadow_spread=1.1))
            head_cy = y + 12 + HEAD_H / 2
            img.alpha_composite(rc.pill(16, 16, pal.feed_top, pal.feed_bottom, 6),
                                dest=(MARGIN + 22, int(head_cy - 8)))
            self._draw_text(draw, (MARGIN + 48, head_cy + 1), title, font=f_sec,
                            fill=rc.darken(pal.weekend, 0.85), anchor='lm')
            draw.line([(MARGIN + 22, y + 12 + HEAD_H),
                       (W - MARGIN - 22, y + 12 + HEAD_H)], fill=div_col, width=1)
            ry = y + 12 + HEAD_H + 10
            for kind, label, lines, font, lh in items:
                if kind == 'kv':
                    draw.text((MARGIN + ROW_L, ry + lh / 2), label + '：',
                              font=font, fill=pal.subtitle, anchor='lm')
                    tx = MARGIN + val_x
                    for vl in lines:
                        vruns = rc.number_runs(vl)
                        vcx = tx
                        for text, is_num in vruns:
                            draw.text((vcx, ry + lh / 2), text, font=font,
                                      fill=pal.accent_text if is_num else pal.body,
                                      anchor='lm')
                            vcx += draw.textlength(text, font=font)
                        ry += lh
                else:
                    fill_c = pal.subtitle if kind == 'note' else pal.body
                    for ln in lines:
                        if kind == 'plain':
                            lcx = MARGIN + ROW_L
                            for text, is_num in rc.number_runs(ln):
                                draw.text((lcx, ry + lh / 2), text, font=font,
                                          fill=pal.accent_text if is_num else fill_c,
                                          anchor='lm')
                                lcx += draw.textlength(text, font=font)
                        else:
                            draw.text((MARGIN + ROW_L, ry + lh / 2), ln,
                                      font=font, fill=fill_c, anchor='lm')
                        ry += lh
            y += sh + sec_gap

        file_path = os.path.join(self.temp_dir, f"career_{int(time.time())}.png")
        img.convert('RGB').save(file_path, format='PNG')
        return file_path

    def _measure_text_width(self, draw, text, font):
        total = 0.0
        emoji_font = None
        try:
            size = getattr(font, 'size', 16) or 16
            ep = getattr(self, '_emoji_path', None) or os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
            if os.path.exists(ep):
                emoji_font = ImageFont.truetype(ep, size)
        except Exception:
            pass
        for ch in text:
            if ord(ch) > 0xFFFF and emoji_font is not None:
                total += draw.textlength(ch, font=emoji_font)
            else:
                total += draw.textlength(ch, font=font)
        return total

    def _truncate_text(self, draw, text, font, max_w):
        cur = ""
        w = 0.0
        ellipsis = "…"
        ew = draw.textlength(ellipsis, font=font)
        emoji_font = None
        try:
            size = getattr(font, 'size', 16) or 16
            ep = getattr(self, '_emoji_path', None) or os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
            if os.path.exists(ep):
                emoji_font = ImageFont.truetype(ep, size)
        except Exception:
            pass
        for ch in text:
            f = emoji_font if (ord(ch) > 0xFFFF and emoji_font is not None) else font
            cw = draw.textlength(ch, font=f)
            if w + cw + ew > max_w:
                break
            cur += ch
            w += cw
        if cur != text:
            cur += ellipsis
        return cur

    def _emoji_available(self):
        if getattr(self, '_emoji_font', None) is not None:
            return True
        return os.path.exists(os.path.join(self._plugin_dir, 'resources', 'fonts', 'emoji.ttf'))

    def _draw_cake_emoji(self, draw, xy, font):
        """画 🍰：有彩色 emoji 字体用 embedded_color；否则退化为红色勾，避免全透明不可见。"""
        ep = getattr(self, '_emoji_path', None) or os.path.join(
            self._plugin_dir, 'resources', 'fonts', 'emoji.ttf')
        try:
            if ep and os.path.exists(ep):
                draw.text(xy, CAKE_EMOJI, font=font, fill=CAKE_RED, embedded_color=True,
                          anchor='mm')
                return True
        except Exception:
            pass
        return False

    def _download_avatar_sync(self, qq_id: str, save_path: str) -> bool:
        """同步下载 QQ 头像到临时文件（由调用方 to_thread 包装，避免阻塞事件循环）。"""
        import urllib.request
        url = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            if data:
                with open(save_path, 'wb') as f:
                    f.write(data)
                return True
        except Exception as e:
            logger.error(f"下载头像 {qq_id} 失败: {e}")
        return False

    async def _save_qq_avatar(self, event, user_id: str, dark: bool = False) -> str:
        """按平台与主题开关下载头像到临时文件，失败返回空串。

        仅 QQ 平台且当前渲染主题开启 show_avatar 时才下载；网络请求走 to_thread。
        """
        try:
            if event.get_platform_name() != "aiocqhttp":
                return ""
        except Exception:
            return ""
        renderer = self._get_dark_renderer() if dark else (self._get_html_renderer('calendar') or self._pil_renderer)
        if not getattr(renderer, '_show_avatar', True):
            return ""
        save_path = os.path.join(self.temp_dir, f"avatar_{user_id}.png")
        ok = await asyncio.to_thread(self._download_avatar_sync, user_id, save_path)
        return save_path if ok else ""

    async def _generate_and_send_calendar(self, event, user_id: str, user_name: str,
                                          db_path: str, adjusted_date_str: str = None,
                                          dark: bool = False):
        """生成日历图。dark=True 时用达妮娅暗夜主题（black-1）渲染。"""
        if adjusted_date_str:
            current_year = int(adjusted_date_str[:4])
            current_month = int(adjusted_date_str[5:7])
            current_month_str = adjusted_date_str[:7]
        else:
            current_year = date.today().year
            current_month = date.today().month
            current_month_str = date.today().strftime("%Y-%m")
        checkin_records = {}
        total_cakes_this_month = 0
        group_id = str(event.get_group_id() or '')
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    "SELECT checkin_date, cake_count FROM checkin WHERE user_id = ? AND group_id = ? AND strftime('%Y-%m', checkin_date) = ?",
                    (user_id, group_id, current_month_str)
                )) as cursor:
                    rows = await cursor.fetchall()
                for row in rows:
                    day = int(row[0].split('-')[2])
                    checkin_records[day] = checkin_records.get(day, 0) + row[1]
                    total_cakes_this_month += row[1]
                async with (await conn.execute(
                    "SELECT date, SUM(count) FROM help_record WHERE target_id = ? AND group_id = ? AND strftime('%Y-%m', date) = ? GROUP BY date",
                    (user_id, group_id, current_month_str)
                )) as cursor2:
                    help_rows = await cursor2.fetchall()
                for row in help_rows:
                    day = int(row[0].split('-')[2])
                    checkin_records[day] = checkin_records.get(day, 0) + row[1]
                    total_cakes_this_month += row[1]
                if not checkin_records:
                    return CALENDAR_EMPTY, None, False
        except Exception as e:
            logger.error(f"查询用户 {user_name} ({user_id}) 的月度数据失败: {e}")
            return CALENDAR_ERROR, None, True
        image_path = ""
        if self.render_backend == "pil" and not self.font_path:
            # PIL 后端未配置字体：降级为文字提示（resources/fonts 或系统字体均缺失）
            return CALENDAR_FONT_MISSING.format(
                days=len(checkin_records), cakes=total_cakes_this_month), None, False
        # 高亮「今天」也以调整日为准（day_start_time 非 00:00 时与入库日期差一天）。
        # 调整日跨月时渲染的是上一月，此时不标任何格子为今天。
        if adjusted_date_str:
            today = (int(adjusted_date_str[8:10])
                     if (current_year == int(adjusted_date_str[:4])
                         and current_month == int(adjusted_date_str[5:7])) else 0)
        else:
            today = (date.today().day if (current_year == date.today().year
                                          and current_month == date.today().month) else 0)
        avatar_path = await self._save_qq_avatar(event, user_id, dark)
        renderer = self._get_dark_renderer() if dark else (self._get_html_renderer('calendar') or self._pil_renderer)
        pil_fallback = self._get_dark_pil_renderer() if dark else self._pil_renderer
        try:
            image_path = await asyncio.to_thread(
                renderer.render,
                user_id, user_name, current_year, current_month,
                checkin_records, total_cakes_this_month, avatar_path, today)
            return None, image_path, False
        except FileNotFoundError:
            logger.error("字体文件未找到！无法生成日历图片。")
            return CALENDAR_SERVER_FONT_MISSING.format(
                days=len(checkin_records), cakes=total_cakes_this_month), None, False
        except Exception as e:
            if self.render_backend == "html":
                logger.error(f"HTML 日历渲染失败，降级 PIL: {e}")
                try:
                    image_path = await asyncio.to_thread(
                        pil_fallback.render,
                        user_id, user_name, current_year, current_month,
                        checkin_records, total_cakes_this_month, avatar_path, today)
                    return None, image_path, False
                except Exception as e2:
                    logger.error(f"PIL 日历渲染降级也失败: {e2}")
                    return CALENDAR_UNKNOWN_ERROR, None, True
            logger.error(f"生成或发送日历图片失败: {e}")
            return CALENDAR_UNKNOWN_ERROR, None, True
        finally:
            if avatar_path and os.path.exists(avatar_path):
                try:
                    os.remove(avatar_path)
                except Exception:
                    pass

    @staticmethod
    def _row_content_width(draw, avatar_w, nickname, nick_font, badge, badge_font):
        """计算一行「头像 + 昵称 + 徽章」的总宽度（整数像素）。

        抽出为纯函数便于单测：同一栏内，只要 avatar_w 相同，
        起始 x 就只取决于昵称+徽章宽度，不同行宽度不同会导致左右抖动。
        """
        w = avatar_w + (8 if avatar_w else 0)
        if nickname:
            w += draw.textlength(nickname, font=nick_font)
        if badge:
            w += 6 + draw.textlength(badge, font=badge_font) + 10
        return int(round(w))

    @staticmethod
    def _load_circle_avatar(avatar_dir, uid, size):
        """读取头像并裁成带白描边的圆形 RGBA；缺失或失败返回 None。"""
        if not avatar_dir or not uid:
            return None
        path = os.path.join(avatar_dir, f"{uid}.png")
        if not os.path.exists(path):
            return None
        try:
            av = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            out.paste(av, (0, 0), mask)
            # 白描边，和日历头像风格统一
            ImageDraw.Draw(out).ellipse([1, 1, size - 1, size - 1],
                                        outline=(255, 255, 255, 235), width=2)
            return out
        except Exception:
            return None

    def _create_three_column_ranking_image(self, today_self, today_received, today_helped,
                                           month_self, month_received, month_helped,
                                           year, month, page, total_pages, system_name="🍰",
                                           avatar_dir=None, ach_map=None, max_rows=10):
        """排行榜图：主题场景 + 白玻璃栏卡 + 前三名奖牌 + 行分隔线。

        render_backend=html 时优先用 HTML/CSS + Chrome 渲染（排版更整齐），
        失败自动降级到 PIL 实现。

        data_rows: (rank, uid, nickname, count, ach_count)
        max_rows: 每栏最多展示行数（默认 10，与 ranking_display_count 配置一致）。
        """
        ach_map = ach_map or {}
        # HTML 后端优先，失败降级 PIL
        html_renderer = self._get_html_renderer('ranking')
        if html_renderer is not None:
            try:
                return html_renderer.render(
                    today_self, today_received, today_helped,
                    month_self, month_received, month_helped,
                    year, month, page, total_pages, system_name,
                    avatar_dir, ach_map, max_rows)
            except Exception as e:
                logger.error(f"HTML 排行榜渲染失败，降级 PIL: {e}")
                self._close_html_browser_on_error()
        pal = self._palette()
        W, MARGIN, GAP = 900, 26, 14
        CARD_W = W - MARGIN * 2
        COL_W = (CARD_W - GAP * 2) // 3
        ROW_H, AV = 42, 34
        MAX_ROWS = max(int(max_rows), 1)

        f_big = ImageFont.truetype(self.font_path, 26)
        f_sub = ImageFont.truetype(self.font_path, 13)
        f_sec = ImageFont.truetype(self.font_path, 15)
        f_col = ImageFont.truetype(self.font_path, 14)
        f_row = ImageFont.truetype(self.font_path, 15)
        f_row_small = ImageFont.truetype(self.font_path, 12)
        f_rank = ImageFont.truetype(self.font_path, 13)
        f_count = ImageFont.truetype(self.font_path, 15)
        f_page = ImageFont.truetype(self.font_path, 12)

        SEC_PILL_H = 28
        COL_HEAD = 46                      # 栏头胶囊 24 + 上下留白
        SEC_GAP = 16

        card_rgb = pal.card_fill[:3]
        # 前三名奖牌：金 / 银 / 铜（竖直渐变 + 白字）
        MEDALS = {
            1: ((255, 213, 110), (236, 168, 58)),
            2: ((228, 236, 245), (176, 192, 210)),
            3: ((240, 194, 148), (203, 141, 90)),
        }

        def rows_of(data):
            """截断到 MAX_ROWS，并过滤掉空行/长度不足的畸形数据（防止 row[0] 越界）。"""
            out = []
            for row in list(data)[:MAX_ROWS] if data else []:
                if not row or len(row) < 4:
                    continue
                out.append(row)
            return out

        today_sets = [rows_of(today_self), rows_of(today_received), rows_of(today_helped)]
        month_sets = [rows_of(month_self), rows_of(month_received), rows_of(month_helped)]
        today_h = max([len(s) for s in today_sets] + [1])
        month_h = max([len(s) for s in month_sets] + [1])

        # ---- 高度：按各组实际行数，避免今日区只有 6 条却画 10 行留出大片空白 ----
        TITLE_H, SUB_H = 42, 24
        def group_h(n):
            return SEC_PILL_H + 10 + COL_HEAD + n * ROW_H + 12
        H = (MARGIN * 2 + TITLE_H + SUB_H
             + group_h(today_h) + SEC_GAP + group_h(month_h) + 44)

        img = rc.scene(W, H, pal, card_box=(MARGIN, MARGIN, W - MARGIN, H - MARGIN),
                       card_radius=28, shadow_alpha=95, shadow_spread=1.3)
        img.alpha_composite(rc.top_wash(
            W, H, (MARGIN, MARGIN, W - MARGIN, H - MARGIN), 28, pal.feed_top, 130, 60))
        draw = ImageDraw.Draw(img)

        # ---- 标题 ----
        y = MARGIN + 22
        self._draw_denia_logo(img, draw, size=38, xy=(MARGIN + 2, y - 2))
        self._draw_text(draw, (W / 2, y),
                        RANKING_TITLE.format(year=year, month=month),
                        font=f_big, fill=rc.darken(pal.title, 0.9), anchor='mt')
        y += TITLE_H
        self._draw_text(draw, (W / 2, y), RANKING_SUBTITLE,
                        font=f_sub, fill=pal.subtitle, anchor='mt')
        y += SUB_H

        def draw_group(section_title, sets, col_titles, start_y, avail_rows):
            """渲染一整组（今日 / 本月）：居中胶囊小节标题 + 三栏卡片，返回结束 y。"""
            sec_text_w = draw.textlength(section_title, font=f_sec)
            pw, ph = int(sec_text_w) + 48, SEC_PILL_H
            px = (W - pw) / 2
            grad = rc.pill(pw, ph, rc.mix(pal.feed_top, card_rgb, 0.55),
                           rc.mix(pal.feed_bottom, card_rgb, 0.68), ph // 2)
            img.alpha_composite(grad, dest=(int(px), int(start_y)))
            draw.rounded_rectangle([px, start_y, px + pw, start_y + ph], radius=ph // 2,
                                   outline=rc.mix(pal.feed_border, card_rgb, 0.3) + (255,),
                                   width=1)
            self._draw_text(draw, (W / 2, start_y + ph / 2 + 1), section_title,
                            font=f_sec, fill=rc.darken(pal.weekend, 0.8), anchor='mm')
            gy = start_y + SEC_PILL_H + 10
            gh = COL_HEAD + avail_rows * ROW_H + 12
            for i, (rows, col_title) in enumerate(zip(sets, col_titles)):
                cx = MARGIN + i * (COL_W + GAP)
                box = (cx, gy, cx + COL_W, gy + gh)
                # 栏卡片：近白填充 + 主题深色投影，形成"浮在背景上"的层次
                layer = rc.rounded_card_layer(
                    W, H, box, radius=16,
                    fill=rc.mix(pal.feed_top, card_rgb, 0.965) + (255,),
                    border=rc.mix(pal.feed_border, card_rgb, 0.4), border_w=1,
                    shadow=True, shadow_color=rc.darken(pal.weekend, 0.45, 0),
                    shadow_blur=12, shadow_offset=4,
                    shadow_alpha=85, shadow_spread=1.15)
                img.alpha_composite(layer)
                # 栏头胶囊
                ct_w = int(draw.textlength(col_title, font=f_col)) + 32
                chx = cx + (COL_W - ct_w) / 2
                img.alpha_composite(rc.pill(ct_w, 24,
                                            rc.mix(pal.feed_top, card_rgb, 0.72),
                                            rc.mix(pal.feed_bottom, card_rgb, 0.82), 12),
                                    dest=(int(chx), gy + 12))
                self._draw_text(draw, (cx + COL_W / 2, gy + 24 + 1), col_title,
                                font=f_col, fill=rc.darken(pal.subtitle, 0.78), anchor='mm')
                ry = gy + COL_HEAD
                for idx, row in enumerate(rows):
                    rank, uid, nickname, count = row[0], row[1], row[2], row[3]
                    ach = row[4] if len(row) > 4 else 0
                    mid_y = int(round(ry + ROW_H / 2))
                    # 名次：前三名渐变奖牌圆，其余淡色数字
                    medal = MEDALS.get(rank) if isinstance(rank, int) else None
                    mcx = cx + 26
                    if medal:
                        mc0, mc1 = medal
                        d = 24
                        mg = rc.pill(d, d, mc0, mc1, d // 2)
                        mmask = Image.new('L', (d, d), 0)
                        ImageDraw.Draw(mmask).ellipse((0, 0, d - 1, d - 1), fill=255)
                        mlayer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                        mlayer.paste(mg, (mcx - d // 2, mid_y - d // 2), mmask)
                        img.alpha_composite(mlayer)
                        draw.text((mcx, mid_y + 0.5), str(rank), font=f_rank,
                                  fill=(255, 255, 255), anchor='mm')
                    else:
                        draw.text((mcx, mid_y), str(rank), font=f_rank,
                                  fill=pal.subtitle, anchor='mm')
                    inner_l = cx + 46
                    inner_r = cx + COL_W - 46
                    av_rgba = self._load_circle_avatar(avatar_dir, uid, AV)
                    avatar_w = AV if av_rgba is not None else 0
                    badge = f"x{ach}" if ach > 0 else ""
                    badge_w = (self._measure_text_width(draw, badge, f_row_small) + 12) if badge else 0
                    nick_avail = max((inner_r - inner_l) - avatar_w - 8 - badge_w - 10, 20)
                    chosen = None
                    has_emoji = any(ord(ch) > 0xFFFF for ch in nickname)
                    if not (has_emoji and not self._emoji_available()):
                        for f in (f_row, f_row_small):
                            if self._measure_text_width(draw, nickname, f) <= nick_avail:
                                chosen = (nickname, f)
                                break
                        if chosen is None:
                            tr = self._truncate_text(draw, nickname, f_row_small, nick_avail)
                            if tr:
                                chosen = (tr, f_row_small)
                    # 头像固定左对齐：昵称/徽章宽度不影响头像位置，杜绝逐行抖动。
                    sx = inner_l
                    if av_rgba is not None:
                        img.alpha_composite(av_rgba, dest=(sx, mid_y - AV // 2))
                        sx += avatar_w + 8
                    if chosen:
                        self._draw_text(draw, (sx, mid_y), chosen[0], font=chosen[1],
                                        fill=rc.darken(pal.body, 0.85), anchor='lm')
                        sx += int(round(self._measure_text_width(draw, chosen[0], chosen[1]))) + 6
                    if badge:
                        bw = badge_w
                        bh = 18
                        draw.rounded_rectangle(
                            [sx, mid_y - bh / 2, sx + bw, mid_y + bh / 2],
                            radius=bh // 2, fill=rc.mix(pal.feed_top, card_rgb, 0.7) + (255,),
                            outline=rc.mix(pal.feed_border, card_rgb, 0.45) + (255,), width=1)
                        self._draw_text(draw, (sx + bw / 2, mid_y), badge,
                                        font=f_row_small, fill=pal.accent_text, anchor='mm')
                    self._draw_text(draw, (cx + COL_W - 14, mid_y), str(count),
                                    font=f_count, fill=pal.accent, anchor='rm')
                    # 行间分隔线（最后一行不画）
                    if idx < len(rows) - 1:
                        sep_y = ry + ROW_H
                        draw.line([(cx + 16, sep_y), (cx + COL_W - 16, sep_y)],
                                  fill=rc.mix(pal.empty_border, card_rgb, 0.15), width=1)
                    ry += ROW_H
                if not rows:
                    self._draw_text(draw, (cx + COL_W / 2, gy + COL_HEAD + 16),
                                    '今天还没有人投喂哦', font=f_row_small,
                                    fill=pal.subtitle, anchor='mm')
            return gy + gh

        cols = [RANKING_COL_SELF, RANKING_COL_RECEIVED, RANKING_COL_HELP]
        y = draw_group(RANKING_TODAY, today_sets, cols, y, today_h)
        y += SEC_GAP
        y = draw_group(RANKING_MONTH, month_sets, cols, y, month_h)

        y += 14
        page_text = (RANKING_PAGE.format(page=page, total=total_pages, next=page + 1)
                     if page < total_pages
                     else RANKING_PAGE_LAST.format(page=page, total=total_pages))
        self._draw_text(draw, (W / 2, y), page_text, font=f_page,
                        fill=pal.subtitle, anchor='mt')

        file_path = os.path.join(
            self.temp_dir, f"ranking_{year}_{month}_p{page}_{int(time.time())}.png")
        img.convert('RGB').save(file_path, format='PNG')
        return file_path
    async def _get_period_ranking_data(self, db_path, cond_sql, cond_params, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT user_id, SUM(cake_count) as total FROM checkin WHERE group_id = ? AND {cond_sql} GROUP BY user_id ORDER BY total DESC",
                    (group_id, *cond_params)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for uid, total in rows:
                        if str(uid) in group_user_ids:
                            all_users.append((uid, total))
        except Exception as e:
            logger.error(f"查询排行数据失败: {e}")
        return all_users

    async def _get_help_ranking_data(self, db_path, cond_sql, cond_params, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT helper_id, SUM(count) as total FROM help_record WHERE group_id = ? AND {cond_sql} GROUP BY helper_id ORDER BY total DESC",
                    (group_id, *cond_params)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for hid, total in rows:
                        if str(hid) in group_user_ids:
                            all_users.append((hid, total))
        except Exception as e:
            logger.error(f"查询替喂榜数据失败: {e}")
        return all_users

    async def _get_received_ranking_data(self, db_path, cond_sql, cond_params, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT target_id, SUM(count) as total FROM help_record WHERE group_id = ? AND {cond_sql} GROUP BY target_id ORDER BY total DESC",
                    (group_id, *cond_params)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for tid, total in rows:
                        if str(tid) in group_user_ids:
                            all_users.append((tid, total))
        except Exception as e:
            logger.error(f"查询被喂榜数据失败: {e}")
        return all_users
