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

    def __init__(self, font_path: str, db_path: str, temp_dir: str, render_backend: str = "pil",
                 theme_preset: str = "custom"):
        self._plugin_dir = os.path.dirname(font_path) if font_path else os.getcwd()
        self.font_path = None
        self.db_path = db_path
        self.temp_dir = temp_dir
        self._emoji_font = None
        self._init_fonts()
        # 日历渲染后端：pil（默认，无额外依赖）/ html（Playwright + 系统 Chrome）
        self.render_backend = render_backend if render_backend in ("pil", "html") else "pil"
        # 日历主题：预设 white-1/white-2/black-1/black-2 或 custom（读 resources/theme.json）
        from .theme import load_theme
        self.theme_preset = theme_preset
        self.theme = load_theme(theme_preset)
        from .render_pil.calendar import PilCalendarRenderer
        self._pil_renderer = PilCalendarRenderer(self, self.theme)
        if self.render_backend == "html":
            from .render_html.calendar import HtmlCalendarRenderer
            self.calendar_renderer = HtmlCalendarRenderer(self, self.theme)
        else:
            self.calendar_renderer = self._pil_renderer
        # 达妮娅（暗夜·black-1）彩蛋渲染器：懒加载，仅在彩蛋触发时使用
        self._dark_renderer = None

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
                draw.text((xy[0] + size / 2 - w / 2, xy[1]), CAKE_EMOJI, font=ef, fill=(0, 0, 0, 0), embedded_color=True)
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

    def _create_analysis_image(self, user_name: str, target_period: str, analysis_result: str,
                               checkin_rate: float = 0.0, system_name: str = "蛋糕") -> str:
        WIDTH, HEIGHT = 750, 550
        if checkin_rate >= 0.7:
            BG_COLOR = (255, 235, 240)
            HEADER_COLOR = (200, 80, 110)
        elif checkin_rate >= 0.4:
            BG_COLOR = (255, 242, 235)
            HEADER_COLOR = (180, 110, 90)
        else:
            BG_COLOR = (240, 240, 255)
            HEADER_COLOR = (110, 100, 180)
        TEXT_COLOR = (60, 50, 55)
        font_header = ImageFont.truetype(self.font_path, 32)
        font_content = ImageFont.truetype(self.font_path, 22)
        img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        header_text = ANALYSIS_HEADER.format(period=target_period, name=user_name)
        header_bbox = draw.textbbox((0, 0), header_text, font=font_header)
        header_width = header_bbox[2] - header_bbox[0]
        draw.text(((WIDTH - header_width) // 2, 40), header_text, font=font_header, fill=HEADER_COLOR)
        lines = analysis_result.split('\n')
        y_offset = 100
        line_height = 35
        for line in lines:
            line = line.strip()
            if not line:
                y_offset += line_height // 2
                continue
            bbox = draw.textbbox((0, 0), line, font=font_content)
            text_width = bbox[2] - bbox[0]
            x_pos = (WIDTH - text_width) // 2
            draw.text((x_pos, y_offset), line, font=font_content, fill=TEXT_COLOR)
            y_offset += line_height
        safe_user = self._safe_file_component(user_name)
        safe_period = self._safe_file_component(target_period.replace('年', '_').replace('月', ''))
        file_path = os.path.join(self.temp_dir, f"analysis_{safe_user}_{safe_period}_{int(time.time())}.png")
        img.save(file_path, format='PNG')
        return file_path

    def _create_career_image(self, user_name: str, stats: dict, system_name: str = "娅娅") -> str:
        WIDTH = 800
        HEIGHT = 1100
        BG_COLOR = PINK_BG
        TITLE_COLOR = CHOCO
        SUBTITLE_COLOR = (150, 110, 120)
        TEXT_COLOR = (90, 70, 80)
        HIGHLIGHT_COLOR = PINK_DEEP
        SECTION_BG_COLOR = (255, 255, 255)
        COMMENT_COLOR = (160, 130, 140)

        img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)
        font_title = ImageFont.truetype(self.font_path, 40)
        font_subtitle = ImageFont.truetype(self.font_path, 24)
        font_section_title = ImageFont.truetype(self.font_path, 28)
        font_text = ImageFont.truetype(self.font_path, 24)
        font_comment = ImageFont.truetype(self.font_path, 20)
        y_pos = 50
        draw.text((WIDTH / 2, y_pos), CAREER_TITLE, font=font_title, fill=TITLE_COLOR, anchor="mm")
        y_pos += 50
        draw.text((WIDTH / 2, y_pos), CAREER_FEEDER.format(name=user_name),
                  font=font_subtitle, fill=SUBTITLE_COLOR, anchor="mm")
        y_pos += 40
        draw.text((WIDTH / 2, y_pos), CAREER_QUOTE.format(comment=stats['summary_comment']),
                  font=font_section_title, fill=HIGHLIGHT_COLOR, anchor="mm")
        y_pos += 60

        def draw_section(title, lines, start_y):
            content_height = 0
            processed_lines = []
            for item in lines:
                text = item['text']
                is_comment = item.get('is_comment', False)
                f = font_comment if is_comment else font_text
                color = COMMENT_COLOR if is_comment else TEXT_COLOR
                offset = 30 if is_comment else 35
                processed_lines.append((text, f, color, offset))
                content_height += offset
            section_height = 40 + content_height + 20
            draw.rectangle([40, start_y, WIDTH - 40, start_y + section_height], fill=SECTION_BG_COLOR, outline=(240, 210, 220), width=1)
            current_y = start_y + 25
            draw.text((60, current_y), title, font=font_section_title, fill=HIGHLIGHT_COLOR, anchor="lm")
            current_y += 40
            for text, f, color, offset in processed_lines:
                draw.text((80, current_y), text, font=f, fill=color, anchor="lm")
                current_y += offset
            return start_y + section_height + 30

        lines = [{'text': CAREER_FIRST.format(date=stats['first_date_str'],
                                              days=stats['total_span_days'])}]
        y_pos = draw_section(CAREER_SECTIONS[0], lines, y_pos)
        avg_display = ""
        if stats['daily_avg'] > 1:
            avg_display = CAREER_AVG_DAILY.format(avg=f"{stats['daily_avg']:.2f}")
        elif stats['daily_avg'] > 0:
            interval = 1 / stats['daily_avg']
            avg_display = CAREER_AVG_INTERVAL.format(interval=f"{interval:.1f}")
        else:
            avg_display = CAREER_AVG_ZERO
        lines = [
            {'text': CAREER_TOTAL.format(count=stats['total_count'])},
            {'text': CAREER_DAYS.format(days=stats['total_days'],
                                        ratio=f"{stats['active_ratio']:.1f}%")},
            {'text': avg_display}
        ]
        y_pos = draw_section(CAREER_SECTIONS[1], lines, y_pos)
        lines = []
        if stats['max_day_count'] > 1:
            lines.append({'text': CAREER_MAX_DAY.format(
                date=stats['max_day_date'], count=stats['max_day_count'])})
        if stats['max_month_count'] > 0:
            lines.append({'text': CAREER_MAX_MONTH.format(
                month=stats['max_month_str'], count=stats['max_month_count'])})
        y_pos = draw_section(CAREER_SECTIONS[2], lines, y_pos)
        lines = [
            {'text': CAREER_MIN_MONTH.format(month=stats['min_month_str'],
                                             count=stats['min_month_count'])},
            {'text': CAREER_REST.format(text=stats['rest_period_str'])}
        ]
        if stats['sage_comment']:
            lines.append({'text': CAREER_COMMENT_WRAP.format(text=stats['sage_comment']),
                          'is_comment': True})
        y_pos = draw_section(CAREER_SECTIONS[3], lines, y_pos)
        lines = [{'text': CAREER_STATUS.format(days=stats['status_day'])}]
        if stats['status_comment']:
            lines.append({'text': CAREER_COMMENT_WRAP.format(text=stats['status_comment']),
                          'is_comment': True})
        y_pos = draw_section(CAREER_SECTIONS[4], lines, y_pos)
        file_path = os.path.join(self.temp_dir, f"career_{int(time.time())}.png")
        img.save(file_path)
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
        renderer = self._get_dark_renderer() if dark else self.calendar_renderer
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
        today = (date.today().day if (current_year == date.today().year
                                      and current_month == date.today().month) else 0)
        avatar_path = await self._save_qq_avatar(event, user_id, dark)
        renderer = self._get_dark_renderer() if dark else self.calendar_renderer
        pil_fallback = self._get_dark_renderer() if dark else self._pil_renderer
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

    def _create_three_column_ranking_image(self, today_self, today_received, today_helped,
                                           month_self, month_received, month_helped,
                                           year, month, page, total_pages, system_name="🍰",
                                           avatar_dir=None, ach_map=None, max_rows=10):
        """三栏排行榜：自己喂/被喂/替喂 × 今日/本月，名字旁显示成就徽章数。

        data_rows: (rank, uid, nickname, count, ach_count)
        max_rows: 每栏最多展示行数（默认 10，与 ranking_display_count 配置保持一致）。
        """
        ach_map = ach_map or {}
        WIDTH = 900
        COL_W = (WIDTH - 80) // 3
        ROW_H = 46
        MAX_ROWS = max(int(max_rows), 1)
        HEADER_H = 60
        TITLE_H = 75
        SUB_H = 25
        SEP_H = 12
        SEC_H = 30
        FOOTER_H = 35
        HEIGHT = TITLE_H + SUB_H + SEP_H + SEC_H + HEADER_H + MAX_ROWS * ROW_H + SEP_H + SEC_H + HEADER_H + MAX_ROWS * ROW_H + FOOTER_H + 20

        img = Image.new("RGB", (WIDTH, HEIGHT), PINK_BG)
        draw = ImageDraw.Draw(img)
        font_big = ImageFont.truetype(self.font_path, 28)
        font_title = ImageFont.truetype(self.font_path, 20)
        font_small = ImageFont.truetype(self.font_path, 14)
        font_row = ImageFont.truetype(self.font_path, 16)
        font_row_small = ImageFont.truetype(self.font_path, 13)
        font_count = ImageFont.truetype(self.font_path, 15)
        SEP_COLOR = PINK_LIGHT
        GRAY = (170, 140, 150)
        BLACK = CHOCO
        RED = CAKE_RED

        y = 15
        # 娅娅立绘接口：插件目录存在 denia.png 时绘制在标题左侧
        self._draw_denia_logo(img, draw, size=44, xy=(30, y - 4))
        title_text = RANKING_TITLE.format(year=year, month=month)
        self._draw_text(draw, (WIDTH / 2, y), title_text, font=font_big, fill=BLACK, anchor="mt")
        y += TITLE_H
        self._draw_text(draw, (WIDTH / 2, y), RANKING_SUBTITLE, font=font_small, fill=GRAY, anchor="mt")
        y += SUB_H
        draw.rectangle([0, y, WIDTH, y + SEP_H], fill=SEP_COLOR)
        y += SEP_H

        def draw_column(x_start, title, data_rows, start_y):
            self._draw_text(draw, (x_start + COL_W / 2, start_y), title, font=font_title, fill=GRAY, anchor="mt")
            yy = start_y + HEADER_H
            for row in data_rows[:MAX_ROWS]:
                rank, uid, nickname, count = row[0], row[1], row[2], row[3]
                ach_count = row[4] if len(row) > 4 else 0
                self._draw_text(draw, (x_start + 5, yy + ROW_H / 2), str(rank), font=font_row, fill=BLACK, anchor="lm")
                mid_left = x_start + 35
                mid_right = x_start + COL_W - 70
                mid_center = (mid_left + mid_right) / 2
                av_rgba = None
                if avatar_dir and uid:
                    av_path = os.path.join(avatar_dir, f"{uid}.png")
                    if os.path.exists(av_path):
                        try:
                            av = Image.open(av_path).convert("RGBA")
                            av = av.resize((45, 45))
                            mask = Image.new("L", (45, 45), 0)
                            ImageDraw.Draw(mask).ellipse((0, 0, 45, 45), fill=255)
                            av_rgba = Image.new("RGBA", (45, 45), (0, 0, 0, 0))
                            av_rgba.paste(av, (0, 0), mask)
                        except Exception:
                            av_rgba = None
                avatar_w = 45 if av_rgba is not None else 0
                gap = 8
                badge = ""
                if ach_count > 0:
                    badge = f"🏆x{ach_count}"
                badge_w = 0
                if badge:
                    badge_w = self._measure_text_width(draw, badge, font_row_small) + 4
                nick_avail = (mid_right - mid_left) - avatar_w - gap - badge_w - (6 if badge else 0)
                if nick_avail < 10:
                    nick_avail = 10
                chosen = None
                has_emoji = any(ord(ch) > 0xFFFF for ch in nickname)
                if not (has_emoji and not self._emoji_available()):
                    for f in (font_row, font_row_small):
                        if self._measure_text_width(draw, nickname, f) <= nick_avail:
                            chosen = (nickname, f)
                            break
                    if chosen is None:
                        truncated = self._truncate_text(draw, nickname, font_row_small, nick_avail)
                        if truncated:
                            chosen = (truncated, font_row_small)
                total_w = avatar_w
                if chosen:
                    total_w += (gap if avatar_w > 0 else 0) + self._measure_text_width(draw, chosen[0], chosen[1])
                if badge:
                    total_w += 6 + badge_w
                start_x = mid_center - total_w / 2
                if av_rgba is not None:
                    img.paste(av_rgba, (int(start_x), yy), av_rgba)
                    start_x += avatar_w + gap
                if chosen:
                    text, f = chosen
                    self._draw_text(draw, (start_x, yy + ROW_H / 2), text, font=f, fill=BLACK, anchor="lm")
                    start_x += self._measure_text_width(draw, text, f) + 6
                if badge:
                    self._draw_text(draw, (start_x, yy + ROW_H / 2), badge, font=font_row_small, fill=PINK_DEEP, anchor="lm")
                c_x = x_start + COL_W - 10
                self._draw_text(draw, (c_x, yy + ROW_H / 2), str(count), font=font_count, fill=RED, anchor="rm")
                yy += ROW_H

        self_col_title = RANKING_COL_SELF
        recv_col_title = RANKING_COL_RECEIVED
        help_col_title = RANKING_COL_HELP

        self._draw_text(draw, (WIDTH / 2, y), RANKING_TODAY, font=font_title, fill=GRAY, anchor="mt")
        y += SEC_H

        draw_column(40, self_col_title, today_self, y)
        draw_column(40 + COL_W + 20, recv_col_title, today_received, y)
        draw_column(40 + 2 * (COL_W + 20), help_col_title, today_helped, y)
        y += HEADER_H + MAX_ROWS * ROW_H

        draw.rectangle([0, y, WIDTH, y + SEP_H], fill=SEP_COLOR)
        y += SEP_H

        self._draw_text(draw, (WIDTH / 2, y), RANKING_MONTH, font=font_title, fill=GRAY, anchor="mt")
        y += SEC_H

        draw_column(40, self_col_title, month_self, y)
        draw_column(40 + COL_W + 20, recv_col_title, month_received, y)
        draw_column(40 + 2 * (COL_W + 20), help_col_title, month_helped, y)

        y += HEADER_H + MAX_ROWS * ROW_H + 10
        if page < total_pages:
            page_text = RANKING_PAGE.format(page=page, total=total_pages, next=page + 1)
        else:
            page_text = RANKING_PAGE_LAST.format(page=page, total=total_pages)
        self._draw_text(draw, (WIDTH / 2, y), page_text, font=font_small, fill=GRAY, anchor="mt")

        file_path = os.path.join(self.temp_dir, f"ranking_{year}_{month}_p{page}_{int(time.time())}.png")
        img.save(file_path)
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
