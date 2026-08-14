"""cake_core：娅娅喂蛋糕插件的图片渲染与数据查询核心。

改造自 deer_core：粉色系主题、🍰 蛋糕标记、娅娅文案。
"""
import aiosqlite
import calendar
import os
import io
import time
import asyncio
from datetime import date, datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from astrbot.api import logger

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

    def __init__(self, font_path: str, db_path: str, temp_dir: str):
        self._plugin_dir = os.path.dirname(font_path) if font_path else os.getcwd()
        self.font_path = None
        self.db_path = db_path
        self.temp_dir = temp_dir
        self._emoji_font = None
        self._init_fonts()

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

    def _load_avatar(self, qq_id: str, size: int = 40):
        """QQ 头像（圆形裁剪），失败返回 None。"""
        import urllib.request
        url = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img = img.resize((size, size))
            mask = Image.new("L", (size, size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, size, size), fill=255)
            result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            result.paste(img, (0, 0), mask)
            return result
        except Exception as e:
            logger.error(f"加载头像 {qq_id} 失败: {e}")
            return None

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

    def _create_calendar_image(self, user_id: str, user_name: str, year: int, month: int,
                                checkin_data: dict, total_cakes: int, avatar_path: str = None) -> str:
        WIDTH, HEIGHT = 600, 531
        BG_COLOR = PINK_BG
        HEADER_COLOR = CHOCO
        WEEKDAY_COLOR = (150, 120, 130)
        DAY_COLOR = (90, 70, 80)
        TODAY_BG_COLOR = (255, 228, 235)

        font_title = ImageFont.truetype(self.font_path, 26)
        font_subtitle = ImageFont.truetype(self.font_path, 15)
        font_weekday = ImageFont.truetype(self.font_path, 18)
        font_day = ImageFont.truetype(self.font_path, 20)
        font_cake_count = ImageFont.truetype(self.font_path, 16)
        font_summary = ImageFont.truetype(self.font_path, 18)

        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # 左上角 QQ 头像
        if avatar_path and os.path.exists(avatar_path):
            try:
                av = Image.open(avatar_path).convert("RGBA")
                av = av.resize((40, 40))
                mask = Image.new("L", (40, 40), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 40, 40), fill=255)
                av_rgba = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
                av_rgba.paste(av, (0, 0), mask)
                img.paste(av_rgba, (15, 15), av_rgba)
            except Exception:
                pass

        # 主标题："{用户名}的投喂日历" 居中，超长截断（不再不显示）
        title_text = f"{user_name}的投喂日历"
        max_title_w = WIDTH - 150
        if self._measure_text_width(draw, title_text, font_title) > max_title_w:
            truncated = self._truncate_text(draw, title_text, font_title, max_title_w)
            if truncated:
                title_text = truncated
        self._draw_text(draw, (WIDTH / 2, 28), title_text, font=font_title, fill=HEADER_COLOR, anchor="mm")

        # 副标题：年月日（小字号，不再用大标题）
        subtitle = f"{year}年{month}月"
        self._draw_text(draw, (WIDTH / 2, 58), subtitle, font=font_subtitle, fill=WEEKDAY_COLOR, anchor="mm")

        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        cell_width = WIDTH / 7
        for i, day in enumerate(weekdays):
            draw.text((i * cell_width + cell_width / 2, 82), day, font=font_weekday, fill=WEEKDAY_COLOR, anchor="mm")

        cal = calendar.monthcalendar(year, month)
        y_offset = 112
        cell_height = 65
        today_num = date.today().day if date.today().year == year and date.today().month == month else 0

        # 投喂日 emoji 图标字体（🍰），不可用时回退红色勾
        cake_emoji_font = None
        if self._emoji_available():
            try:
                ep = getattr(self, '_emoji_path', None)
                if ep and os.path.exists(ep):
                    cake_emoji_font = ImageFont.truetype(ep, 32)
            except Exception:
                cake_emoji_font = None

        for week in cal:
            for i, day_num in enumerate(week):
                if day_num == 0:
                    continue
                x_pos = i * cell_width
                if day_num == today_num:
                    draw.rectangle([x_pos, y_offset, x_pos + cell_width, y_offset + cell_height], fill=TODAY_BG_COLOR)

                draw.text((x_pos + cell_width / 2, y_offset + cell_height / 2 - 20), str(day_num), font=font_day, fill=DAY_COLOR, anchor="mm")

                if day_num in checkin_data:
                    cx = x_pos + cell_width / 2
                    cy = y_offset + cell_height / 2 + 9
                    if cake_emoji_font is not None:
                        # 投喂日覆盖 🍰 图标
                        draw.text((cx, cy), CAKE_EMOJI, font=cake_emoji_font, anchor="mm", embedded_color=True)
                    else:
                        draw.line(
                            [(cx - 13, cy), (cx - 5, cy + 8), (cx + 14, cy - 9)],
                            fill=CAKE_RED, width=4, joint="curve")
                    count = checkin_data[day_num]
                    draw.text((x_pos + cell_width - 5, y_offset + cell_height - 5), str(count), font=font_cake_count, fill=CAKE_RED, anchor="rd")
            y_offset += cell_height

        total_days = len(checkin_data)
        summary_text = f"本月娅娅吃了 {total_days} 天的蛋糕，共 {total_cakes} 块"
        self._draw_text(draw, (WIDTH / 2, HEIGHT - 25), summary_text, font=font_summary, fill=HEADER_COLOR, anchor="mm")

        file_path = os.path.join(self.temp_dir, f"cake_{user_id}_{int(time.time())}.png")
        img.save(file_path, format='PNG')
        return file_path

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

        report = f"这个月你给娅娅喂了 {total_days} 天的蛋糕，一共 {total_cakes} 块！\n"
        if max_day_count > 1:
            if max_day_count >= 3:
                report += f"最猛的一天是 {max_day_num} 日，一口气喂了 {max_day_count} 块，娅娅的小肚子都圆了一圈～\n"
            elif max_day_count == 2:
                report += f"{max_day_num} 日双蛋糕投喂，娅娅开心得转圈圈！\n"
        if max_consecutive >= 7:
            report += f"最长连续投喂 {max_consecutive} 天！娅娅说这是她吃过最幸福的蛋糕～\n"
        elif max_consecutive >= 4:
            report += f"最长连续投喂 {max_consecutive} 天，娅娅已经习惯每天等你投喂啦～\n"
        elif max_consecutive >= 2:
            report += f"最长连续投喂 {max_consecutive} 天，小小的坚持也很甜！\n"
        report += f"本月投喂率：{checkin_rate:.1%}\n\n"
        if freq_per_day >= 1.3:
            report += "娅娅：每天都有小蛋糕……泡泡都跟着飘起来了。\n不过吃太多会胖的，娅娅可不想动。"
        elif freq_per_day >= 0.7:
            report += "娅娅：有蛋糕、有热闹看、还有人陪着……这样的日子，好像也不错。"
        elif freq_per_day >= 0.4:
            report += "娅娅：甜丝丝的，像泡泡轻轻飘过脸颊。继续保持就好。"
        elif freq_per_day >= 0.1:
            report += "娅娅：偶尔的小甜头也不错，娅娅懒懒地等着下一次投喂～"
        else:
            report += "娅娅：这个月的蛋糕有点少呢…\n没关系，娅娅打盹的时候会梦到它们的。"
        report += "\n\n小贴士：甜食要适度，娅娅更想每天都见到你～"
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
        report = f"这一年你喂了娅娅 {total_months} 个月、{total_days} 天的蛋糕，一共 {total_cakes} 块！\n"
        report += f"最宠娅娅的月份：{max_month_num}月，当月喂了 {max_month_cakes} 块，娅娅都记在心里呢～\n\n"
        avg_per_month = total_cakes / 12
        if avg_per_month > 25:
            report += "年度评价：阿列夫级的甜蜜投喂！\n全年无休，娅娅的泡泡都快装不下了。"
        elif avg_per_month > 15:
            report += "年度评价：虚质学部金牌投喂员！\n稳定输出甜蜜，娅娅很满意。"
        elif avg_per_month > 8:
            report += "年度评价：贴心蛋糕师！\n有节制有甜蜜，娅娅觉得刚刚好～"
        else:
            report += "年度评价：娅娅的好朋友！\n虽然蛋糕不多，但娅娅知道你是真心喜欢她的～"
        report += "\n\n新的一年，娅娅还会在学院门口懒懒地等你来投喂～"
        return report

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
        header_text = f"{target_period} {user_name}的娅娅投喂报告"
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
        safe_period = target_period.replace('年', '_').replace('月', '')
        file_path = os.path.join(self.temp_dir, f"analysis_{user_name}_{safe_period}_{int(time.time())}.png")
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
        draw.text((WIDTH / 2, y_pos), "娅娅喂蛋糕生涯档案", font=font_title, fill=TITLE_COLOR, anchor="mm")
        y_pos += 50
        draw.text((WIDTH / 2, y_pos), f"投喂员：{user_name}", font=font_subtitle, fill=SUBTITLE_COLOR, anchor="mm")
        y_pos += 40
        draw.text((WIDTH / 2, y_pos), f"“{stats['summary_comment']}”", font=font_section_title, fill=HIGHLIGHT_COLOR, anchor="mm")
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

        lines = [{'text': f"{stats['first_date_str']} (距今 {stats['total_span_days']} 天)"}]
        y_pos = draw_section("甜蜜起点", lines, y_pos)
        avg_display = ""
        if stats['daily_avg'] > 1:
            avg_display = f"日均投喂：{stats['daily_avg']:.2f} 块"
        elif stats['daily_avg'] > 0:
            interval = 1 / stats['daily_avg']
            avg_display = f"平均频率：每 {interval:.1f} 天 1 块"
        else:
            avg_display = "日均投喂：0 块"
        lines = [
            {'text': f"累计投喂：{stats['total_count']} 块"},
            {'text': f"投喂天数：{stats['total_days']} 天 (占比 {stats['active_ratio']:.1f}%)"},
            {'text': avg_display}
        ]
        y_pos = draw_section("甜蜜战绩", lines, y_pos)
        lines = []
        if stats['max_day_count'] > 1:
            lines.append({'text': f"单日之最：{stats['max_day_date']} ({stats['max_day_count']} 块)"})
        if stats['max_month_count'] > 0:
            lines.append({'text': f"月度之最：{stats['max_month_str']} ({stats['max_month_count']} 块)"})
        y_pos = draw_section("巅峰时刻", lines, y_pos)
        lines = [
            {'text': f"最少月份：{stats['min_month_str']} ({stats['min_month_count']} 块)"},
            {'text': f"最长断喂：{stats['rest_period_str']}"}
        ]
        if stats['sage_comment']:
            lines.append({'text': f"({stats['sage_comment']})", 'is_comment': True})
        y_pos = draw_section("思念时期", lines, y_pos)
        lines = [{'text': f"距离上次：Day {stats['status_day']}"}]
        if stats['status_comment']:
            lines.append({'text': f"({stats['status_comment']})", 'is_comment': True})
        y_pos = draw_section("当前状态", lines, y_pos)
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

    async def _generate_and_send_calendar(self, event, user_id: str, user_name: str,
                                          db_path: str, adjusted_date_str: str = None):
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
                    return '这个月还没有喂娅娅蛋糕哦，发送"🍰"给娅娅喂第一块小蛋糕吧！', None, False
        except Exception as e:
            logger.error(f"查询用户 {user_name} ({user_id}) 的月度数据失败: {e}")
            return "查询日历数据时出错了 >_<", None, True
        image_path = ""
        if not self.font_path:
            # 未配置字体：降级为文字提示（resources/fonts 或系统字体均缺失）
            return (f"未找到可用中文字体，无法生成日历图片。请将字体放入插件目录 "
                    f"resources/fonts/font.ttf。本月您已投喂{len(checkin_records)}天，"
                    f"累计{total_cakes_this_month}块🍰。", None, False)
        avatar_path = os.path.join(self.temp_dir, f"avatar_{user_id}.png")
        av = self._load_avatar(user_id)
        if av:
            av.save(avatar_path)
        else:
            avatar_path = None
        try:
            image_path = await asyncio.to_thread(
                self._create_calendar_image,
                user_id, user_name, current_year, current_month, checkin_records, total_cakes_this_month, avatar_path
            )
            return None, image_path, False
        except FileNotFoundError:
            logger.error("字体文件未找到！无法生成日历图片。")
            return f"服务器缺少字体文件，无法生成日历图片。请将字体放入插件目录 resources/fonts/font.ttf。本月您已投喂{len(checkin_records)}天，累计{total_cakes_this_month}块🍰。", None, False
        except Exception as e:
            logger.error(f"生成或发送日历图片失败: {e}")
            return "处理日历图片时发生了未知错误 >_<", None, True
        finally:
            if avatar_path and os.path.exists(avatar_path):
                try:
                    os.remove(avatar_path)
                except Exception:
                    pass

    def _create_three_column_ranking_image(self, today_self, today_received, today_helped,
                                           month_self, month_received, month_helped,
                                           year, month, page, total_pages, system_name="🍰",
                                           avatar_dir=None, ach_map=None):
        """三栏排行榜：自己喂/被喂/替喂 × 今日/本月，名字旁显示成就徽章数。

        data_rows: (rank, uid, nickname, count, ach_count)
        """
        ach_map = ach_map or {}
        WIDTH = 900
        COL_W = (WIDTH - 80) // 3
        ROW_H = 46
        MAX_ROWS = 10
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
        title_text = f"{year} 年 {month} 月 娅娅蛋糕🍰榜"
        self._draw_text(draw, (WIDTH / 2, y), title_text, font=font_big, fill=BLACK, anchor="mt")
        y += TITLE_H
        self._draw_text(draw, (WIDTH / 2, y), "每块蛋糕 = 娅娅的开心 +1", font=font_small, fill=GRAY, anchor="mt")
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

        self_col_title = "🍰·自己喂"
        recv_col_title = "被喂·他人"
        help_col_title = "替喂·助人"

        self._draw_text(draw, (WIDTH / 2, y), "· 今日 ·", font=font_title, fill=GRAY, anchor="mt")
        y += SEC_H

        draw_column(40, self_col_title, today_self, y)
        draw_column(40 + COL_W + 20, recv_col_title, today_received, y)
        draw_column(40 + 2 * (COL_W + 20), help_col_title, today_helped, y)
        y += HEADER_H + MAX_ROWS * ROW_H

        draw.rectangle([0, y, WIDTH, y + SEP_H], fill=SEP_COLOR)
        y += SEP_H

        self._draw_text(draw, (WIDTH / 2, y), "· 本月 ·", font=font_title, fill=GRAY, anchor="mt")
        y += SEC_H

        draw_column(40, self_col_title, month_self, y)
        draw_column(40 + COL_W + 20, recv_col_title, month_received, y)
        draw_column(40 + 2 * (COL_W + 20), help_col_title, month_helped, y)

        y += HEADER_H + MAX_ROWS * ROW_H + 10
        page_text = f"第 {page}/{total_pages} 页 · 发送「🍰榜 {page + 1}」翻页" if page < total_pages else f"第 {page}/{total_pages} 页"
        self._draw_text(draw, (WIDTH / 2, y), page_text, font=font_small, fill=GRAY, anchor="mt")

        file_path = os.path.join(self.temp_dir, f"ranking_{year}_{month}_p{page}_{int(time.time())}.png")
        img.save(file_path)
        return file_path

    async def _get_period_ranking_data(self, db_path, date_condition, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT user_id, SUM(cake_count) as total FROM checkin WHERE group_id = ? AND {date_condition} GROUP BY user_id ORDER BY total DESC",
                    (group_id,)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for uid, total in rows:
                        if str(uid) in group_user_ids:
                            all_users.append((uid, total))
        except Exception as e:
            logger.error(f"查询排行数据失败: {e}")
        return all_users

    async def _get_help_ranking_data(self, db_path, date_condition, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT helper_id, SUM(count) as total FROM help_record WHERE group_id = ? AND {date_condition} GROUP BY helper_id ORDER BY total DESC",
                    (group_id,)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for hid, total in rows:
                        if str(hid) in group_user_ids:
                            all_users.append((hid, total))
        except Exception as e:
            logger.error(f"查询替喂榜数据失败: {e}")
        return all_users

    async def _get_received_ranking_data(self, db_path, date_condition, group_user_ids, group_id=''):
        all_users = []
        try:
            async with aiosqlite.connect(db_path) as conn:
                async with (await conn.execute(
                    f"SELECT target_id, SUM(count) as total FROM help_record WHERE group_id = ? AND {date_condition} GROUP BY target_id ORDER BY total DESC",
                    (group_id,)
                )) as cursor:
                    rows = await cursor.fetchall()
                    for tid, total in rows:
                        if str(tid) in group_user_ids:
                            all_users.append((tid, total))
        except Exception as e:
            logger.error(f"查询被喂榜数据失败: {e}")
        return all_users
