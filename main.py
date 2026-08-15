"""🍰 cake_denia —— 今天你喂娅娅小蛋糕了吗。

发送 🍰 给娅娅喂一块小蛋糕。支持帮喂、日历、报告、生涯、补签、排行榜、
成就、LLM 概率对话等功能。
"""
import aiosqlite
import asyncio
import calendar
import json
import math
import os
import random
import re
import time
from datetime import date, datetime, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import CustomFilter
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Plain, Image
from astrbot.api import logger
from astrbot.core.star import StarTools

from .cake_core import CakeCore
from .resources.texts import (
    FEED_SUCCESS, FEED_MULTI, FEED_TOO_MANY, HELP_FEED,
    DAILY_LIMIT_REPLIES,
    BLACK_FEED_SUCCESS, BLACK_FEED_MULTI, BLACK_HELP_FEED,
    BLACK_FEED_TOO_MANY, BLACK_DAILY_LIMIT_REPLIES,
    LLM_SYSTEM_PROMPT, LLM_USER_PROMPT, LLM_REPLY_PREFIX,
    ACHIEVEMENT_UNLOCK, ACHIEVEMENTS_TITLE,
    ACHIEVEMENTS_PROGRESS, ACHIEVEMENTS_ERROR,
    ACHIEVEMENT_UNLOCKED_LINE, ACHIEVEMENT_LOCKED,
    NO_RECORD, CHECKIN_ERROR, ANALYSIS_BAD_MONTH,
    CAREER_ERROR, CAREER_IMG_ERROR,
    RANKING_GROUP_ONLY, RANKING_NO_MEMBERS, RANKING_ERROR,
    RETRO_FORMAT_ERR, RETRO_INVALID_DAY, RETRO_FUTURE, RETRO_ERROR,
    RESET_ADMIN_ONLY, RESET_DONE, RESET_EMPTY, RESET_ERROR,
    CAREER_SUMMARY_LEVELS, CAREER_REST_GAP, CAREER_REST_ALWAYS,
    CAREER_SAGE_ZERO, CAREER_SAGE_LOW,
    CAREER_STATUS_0, CAREER_STATUS_LE3, CAREER_STATUS_LE7,
    CAREER_STATUS_LE30, CAREER_STATUS_OVER,
    HELP_TEXT,
)

FONT_FILE = "font.ttf"
DB_NAME = "yaya_cake.db"

# 默认字体下载地址（托管在本插件 GitHub Releases 附件）
DEFAULT_FONT_URL = "https://github.com/xiaoxi2760/astrbot_plugin_cake_denia/releases/download/v1.0.0/font.ttf"
DEFAULT_EMOJI_URL = "https://github.com/xiaoxi2760/astrbot_plugin_cake_denia/releases/download/v1.0.0/emoji.ttf"

# ---------------------------------------------------------------- 成就系统（用户可 DIY）
# 成就定义在 resources/achievements.json，字段：id/name/icon/desc/type/threshold。
# type ∈ {total_cakes, streak, max_daily, total_helped, total_received}，对应成就统计字段。
def _load_achievements() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'resources', 'achievements.json')
    achievements = {}
    try:
        with open(path, encoding='utf-8') as f:
            for item in json.load(f):
                aid = str(item.get('id', '')).strip()
                if not aid:
                    continue
                t = item.get('type', 'total_cakes')
                th = item.get('threshold', 1)
                achievements[aid] = {
                    'id': aid,
                    'name': item.get('name', aid),
                    'icon': item.get('icon', '🏅'),
                    'desc': item.get('desc', ''),
                    'type': t,
                    'threshold': th,
                    'check': (lambda s, _t=t, _th=th: s.get(_t, 0) >= _th),
                }
    except Exception as e:
        logger.error(f"加载成就配置失败: {e}")
    return achievements


ACHIEVEMENTS = _load_achievements()

# ---------------------------------------------------------------- 触发词（用户可 DIY）
# 配置项 trigger_words 控制命令关键词（默认 🍰/蛋糕），自定义 filter 在匹配时读取配置动态匹配。
DEFAULT_TRIGGER_WORDS = ["🍰", "蛋糕"]


class _TriggerWordFilter(CustomFilter):
    """按配置的触发词 + 命令后缀动态匹配消息。"""

    prefix = ""          # 触发词前的可选前缀正则（如 查看|查询）
    suffix = ""          # 触发词后的命令正则
    char_class = False   # True 时触发词按字符类匹配（连发计数语义），否则按整体词匹配

    def filter(self, event, cfg):
        words = None
        if cfg is not None and hasattr(cfg, 'get'):
            try:
                words = cfg.get('trigger_words')
            except Exception:
                words = None
        if not words:
            words = DEFAULT_TRIGGER_WORDS
        if self.char_class:
            char_class = ''.join(re.escape(w) for w in words)
            pattern = f'^(?:{self.prefix})?[{char_class}]{self.suffix}'
        else:
            alt = '|'.join(re.escape(w) for w in words)
            pattern = f'^(?:{self.prefix})?(?:{alt}){self.suffix}'
        try:
            return bool(re.match(pattern, event.get_message_str().strip()))
        except re.error:
            return False


def trigger_filter(suffix: str, prefix: str = "", char_class: bool = False):
    """生成一个按触发词动态匹配的 CustomFilter 类（每个命令一个）。

    char_class=True 时触发词按字符类匹配（喂蛋糕连发计数），否则按整体词匹配（命令词）。
    """
    return type('TriggerWordFilter', (_TriggerWordFilter,),
                {'prefix': prefix, 'suffix': suffix, 'char_class': char_class})


class CakeDeniaPlugin(Star):

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        config = config if config is not None else {}
        self.group_whitelist = [str(g) for g in config.get("group_whitelist", [])]
        self.user_blacklist = [str(b) for b in config.get("user_blacklist", [])]
        self.day_start_time = config.get("day_start_time", "00:00")
        self.auto_delete_last_month_data = bool(config.get("auto_delete_last_month_data", False))
        self.daily_max_checkins = int(config.get("daily_max_checkins", 0))
        self.max_cakes_per_message = max(1, int(config.get("max_cakes_per_message", 3)))
        self.ranking_display_count = int(config.get("ranking_display_count", 10))
        self.llm_enabled = bool(config.get("llm_enabled", True))
        try:
            self.llm_trigger_probability = float(config.get("llm_trigger_probability", 0.3))
        except (ValueError, TypeError):
            self.llm_trigger_probability = 0.3
        self.llm_daily_min_cakes = int(config.get("llm_daily_min_cakes", 3))
        self.llm_daily_limit = int(config.get("llm_daily_limit", 5))
        self.auto_download_font = bool(config.get("auto_download_font", True))
        self.font_download_url = config.get("font_download_url", DEFAULT_FONT_URL)
        self.emoji_download_url = config.get("emoji_download_url", DEFAULT_EMOJI_URL)
        self.render_backend = config.get("render_backend", "pil")
        self.theme_preset = config.get("theme_preset", "white-1")
        # 触发词（用户可 DIY）：默认 🍰/蛋糕，可改为任意关键词
        words = config.get("trigger_words") or DEFAULT_TRIGGER_WORDS
        self.trigger_words = [str(w) for w in words]

        data_dir = StarTools.get_data_dir("astrbot_plugin_cake_denia")
        plugin_dir = os.path.dirname(os.path.abspath(__file__))

        self.db_path = os.path.join(data_dir, DB_NAME)
        self.font_path = os.path.join(plugin_dir, FONT_FILE)
        self.temp_dir = os.path.join(plugin_dir, "tmp")
        self.avatar_dir = os.path.join(plugin_dir, "avatars")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)

        self.core = CakeCore(self.font_path, self.db_path, self.temp_dir,
                             self.render_backend, self.theme_preset)

        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._last_maintenance = 0.0

    async def _ensure_initialized(self):
        if not self._initialized:
            async with self._init_lock:
                if self._initialized:
                    return
                await self._init_db()
                await self._monthly_cleanup()
                await self._cleanup_temp_files()
                # 资源字体缺失时自动下载默认字体（失败静默降级，不影响使用）
                if self.auto_download_font:
                    await self.core.ensure_fonts(self.font_download_url, self.emoji_download_url)
                self._initialized = True
        await self._maybe_periodic_maintenance()

    async def _maybe_periodic_maintenance(self):
        """周期维护：每天最多执行一次月度清理与临时文件清理（跨月不重启也能清）。"""
        now = time.time()
        if now - self._last_maintenance < 86400:
            return
        self._last_maintenance = now
        await self._monthly_cleanup()
        await self._cleanup_temp_files()

    @filter.on_plugin_unloaded()
    async def _close_html_browser(self, metadata=None):
        """插件卸载/热重载时回收 HTML 渲染器的浏览器进程（AstrBot on_plugin_unloaded 事件）。"""
        try:
            from .render_html.calendar import _shutdown_html_renderer
            # 卸载清理在 worker 线程执行，避免阻塞事件循环（内部含 30s 上限的关闭等待）
            await asyncio.to_thread(_shutdown_html_renderer)
        except Exception:
            pass

    async def _cleanup_temp_files(self, max_age: float = 3600):
        """清理 tmp 目录中超过 max_age 秒的临时图片/HTML，避免长期运行积累。"""
        try:
            now = time.time()
            for name in os.listdir(self.temp_dir):
                path = os.path.join(self.temp_dir, name)
                try:
                    if os.path.isfile(path) and now - os.path.getmtime(path) > max_age:
                        os.remove(path)
                except OSError:
                    continue
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    async def _init_db(self):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''CREATE TABLE IF NOT EXISTS checkin (
                user_id TEXT, group_id TEXT, checkin_date TEXT, cake_count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, group_id, checkin_date)
            )''')
            await conn.execute('''CREATE TABLE IF NOT EXISTS help_record (
                helper_id TEXT, target_id TEXT, group_id TEXT, date TEXT, count INTEGER DEFAULT 1,
                PRIMARY KEY (helper_id, target_id, group_id, date)
            )''')
            await conn.execute('''CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT
            )''')
            await conn.execute('''CREATE TABLE IF NOT EXISTS achievements (
                user_id TEXT, achievement_id TEXT, unlocked_at TEXT,
                PRIMARY KEY (user_id, achievement_id)
            )''')
            await self._migrate_db(conn, 'checkin', 'group_id')
            await self._migrate_db(conn, 'help_record', 'group_id')
            await conn.commit()

    async def _migrate_db(self, conn, table: str, col: str):
        """旧库迁移：表缺少列时重建并保留数据，缺失列默认空串"""
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in await cursor.fetchall()]
        if col in cols:
            return
        try:
            if table == 'checkin':
                await conn.execute("CREATE TABLE checkin_new (user_id TEXT, group_id TEXT, checkin_date TEXT, cake_count INTEGER DEFAULT 1, PRIMARY KEY (user_id, group_id, checkin_date))")
                await conn.execute("INSERT INTO checkin_new (user_id, group_id, checkin_date, cake_count) SELECT user_id, '', checkin_date, cake_count FROM checkin")
                await conn.execute("DROP TABLE checkin")
                await conn.execute("ALTER TABLE checkin_new RENAME TO checkin")
            elif table == 'help_record':
                await conn.execute("CREATE TABLE help_record_new (helper_id TEXT, target_id TEXT, group_id TEXT, date TEXT, count INTEGER DEFAULT 1, PRIMARY KEY (helper_id, target_id, group_id, date))")
                await conn.execute("INSERT INTO help_record_new (helper_id, target_id, group_id, date, count) SELECT helper_id, target_id, '', date, count FROM help_record")
                await conn.execute("DROP TABLE help_record")
                await conn.execute("ALTER TABLE help_record_new RENAME TO help_record")
            logger.info(f"已迁移表 {table}，新增列 {col}")
        except Exception as e:
            logger.error(f"迁移表 {table} 失败: {e}")

    def _get_adjusted_date(self, current_time=None):
        if current_time is None:
            current_time = datetime.now()
        try:
            hour, minute = map(int, self.day_start_time.split(':'))
            day_start = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError, TypeError):
            day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_time.time() < day_start.time():
            adjusted = current_time - timedelta(days=1)
        else:
            adjusted = current_time
        return adjusted.strftime("%Y-%m-%d")

    async def _monthly_cleanup(self):
        if not self.auto_delete_last_month_data:
            return
        two_months_ago = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
        two_months_ago_str = two_months_ago.strftime("%Y-%m")
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "DELETE FROM checkin WHERE strftime('%Y-%m', checkin_date) <= ?",
                    (two_months_ago_str,))
                await conn.execute(
                    "DELETE FROM help_record WHERE strftime('%Y-%m', date) <= ?",
                    (two_months_ago_str,))
                await conn.commit()
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")

    async def _check_group_and_blacklist(self, event: AstrMessageEvent) -> bool:
        group_id = event.get_group_id()
        if group_id:
            if self.group_whitelist and str(group_id) not in self.group_whitelist:
                return False
        sender_id = event.get_sender_id()
        if str(sender_id) in self.user_blacklist:
            return False
        return True

    async def _is_group_admin(self, event: AstrMessageEvent, group_id: str, user_id: str) -> bool:
        """判断用户是否为管理员：AstrBot 全局管理员（event.role）或群主/群管理员（QQ 平台）。"""
        if getattr(event, 'role', 'member') == 'admin':
            return True
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    member_info = await event.bot.get_group_member_info(
                        group_id=int(group_id), user_id=int(user_id))
                    return member_info.get('role') in ('owner', 'admin')
        except Exception as e:
            logger.error(f"查询群管理权限失败: {e}")
        return False

    def _get_at_targets(self, event: AstrMessageEvent) -> list:
        targets = []
        try:
            message_obj = event.message_obj
            if hasattr(message_obj, 'message') and message_obj.message:
                for seg in message_obj.message:
                    if getattr(seg, 'type', None) == 'at' or seg.__class__.__name__ == 'At':
                        qq = getattr(seg, 'qq', None)
                        if qq and str(qq) != 'all':
                            targets.append(str(qq))
        except Exception:
            pass
        return targets

    def _black_egg(self) -> bool:
        """达妮娅彩蛋：20% 概率随机出现，与日历主题无关。"""
        return random.random() < 0.2

    def _feed_reply(self, count: int, egg: bool = None) -> str:
        if egg is None:
            egg = self._black_egg()
        if count > 1:
            if egg and BLACK_FEED_MULTI:
                return random.choice(BLACK_FEED_MULTI).format(count=count)
            return random.choice(FEED_MULTI).format(count=count)
        if egg and BLACK_FEED_SUCCESS:
            return random.choice(BLACK_FEED_SUCCESS)
        return random.choice(FEED_SUCCESS)

    def _feed_too_many(self, egg: bool = None) -> str:
        if egg is None:
            egg = self._black_egg()
        if egg and BLACK_FEED_TOO_MANY:
            return random.choice(BLACK_FEED_TOO_MANY).format(max=self.max_cakes_per_message)
        return random.choice(FEED_TOO_MANY).format(max=self.max_cakes_per_message)

    # ------------------------------------------------------------ 触发词辅助
    def _after_trigger(self, text: str):
        """去掉开头的触发词，返回剩余部分；不是触发词开头返回 None（最长词优先）。"""
        for w in sorted(self.trigger_words, key=len, reverse=True):
            if text.startswith(w):
                return text[len(w):]
        return None

    def _count_trigger_chars(self, text: str) -> int:
        """统计消息开头连续喂的触发词个数（按完整触发词计数：🍰🍰=2、蛋糕=1）。"""
        words = sorted(self.trigger_words, key=len, reverse=True)
        n = 0
        i = 0
        while i < len(text):
            for w in words:
                if text.startswith(w, i):
                    n += 1
                    i += len(w)
                    break
            else:
                break
        return n

    # ------------------------------------------------------------ 每日次数限额
    @staticmethod
    def _daily_ops_key(user_id: str, group_id: str, adjusted_date: str) -> str:
        return f"daily_ops:{user_id}:{group_id}:{adjusted_date}"

    async def _try_consume_daily_op(self, user_id: str, group_id: str, adjusted_date: str):
        """原子地检查并占用一次当日额度。

        返回：True=占用成功（已计数）；False=已达每日上限；None=数据库错误（区分于超限）。
        """
        if self.daily_max_checkins <= 0:
            return True
        key = self._daily_ops_key(user_id, group_id, adjusted_date)
        try:
            async with aiosqlite.connect(self.db_path, timeout=5.0) as conn:
                cursor = await conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, '1') "
                    "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
                    "WHERE CAST(CAST(value AS INTEGER) AS INTEGER) < ?",
                    (key, self.daily_max_checkins))
                await conn.commit()
                return bool(cursor.rowcount)
        except Exception as e:
            logger.error(f"占用每日次数失败: {e}")
            return None

    def _daily_limit_reply(self, egg: bool = None) -> str:
        if egg is None:
            egg = self._black_egg()
        if egg and BLACK_DAILY_LIMIT_REPLIES:
            return random.choice(BLACK_DAILY_LIMIT_REPLIES).format(max=self.daily_max_checkins)
        return random.choice(DAILY_LIMIT_REPLIES).format(max=self.daily_max_checkins)

    def _help_reply(self, names: str, egg: bool = None) -> str:
        if egg is None:
            egg = self._black_egg()
        if egg and BLACK_HELP_FEED:
            return random.choice(BLACK_HELP_FEED).format(names=names)
        return random.choice(HELP_FEED).format(names=names)

    # ------------------------------------------------------------ 成就
    async def _get_user_achievement_stats(self, user_id: str) -> dict:
        """统计用户喂蛋糕数据，用于成就判定（跨群全局统计）。"""
        stats = {
            'total_cakes': 0, 'total_days': 0, 'max_daily': 0,
            'streak': 0, 'total_helped': 0, 'total_received': 0,
        }
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT COALESCE(SUM(cake_count),0) FROM checkin WHERE user_id = ?",
                    (user_id,))
                row = await cursor.fetchone()
                stats['total_cakes'] = row[0] if row else 0
                cursor = await conn.execute(
                    "SELECT COUNT(DISTINCT checkin_date) FROM checkin WHERE user_id = ?",
                    (user_id,))
                row = await cursor.fetchone()
                stats['total_days'] = row[0] if row else 0
                cursor = await conn.execute(
                    "SELECT COALESCE(MAX(daily),0) FROM ("
                    "SELECT SUM(cake_count) AS daily FROM checkin WHERE user_id = ? GROUP BY checkin_date)",
                    (user_id,))
                row = await cursor.fetchone()
                stats['max_daily'] = row[0] if row else 0
                cursor = await conn.execute(
                    "SELECT checkin_date FROM checkin WHERE user_id = ? ORDER BY checkin_date DESC",
                    (user_id,))
                rows = await cursor.fetchall()
                # 连续天数：从最近日期往回数
                day_set = {r[0] for r in rows}
                cursor2 = await conn.execute(
                    "SELECT COALESCE(SUM(count),0) FROM help_record WHERE helper_id = ?",
                    (user_id,))
                row = await cursor2.fetchone()
                stats['total_helped'] = row[0] if row else 0
                cursor3 = await conn.execute(
                    "SELECT COALESCE(SUM(count),0) FROM help_record WHERE target_id = ?",
                    (user_id,))
                row = await cursor3.fetchone()
                stats['total_received'] = row[0] if row else 0
                if day_set:
                    cur = datetime.strptime(self._get_adjusted_date(), "%Y-%m-%d").date()
                    streak = 0
                    while cur.strftime("%Y-%m-%d") in day_set:
                        streak += 1
                        cur -= timedelta(days=1)
                    stats['streak'] = streak
        except Exception as e:
            logger.error(f"统计成就数据失败 ({user_id}): {e}")
        return stats

    async def _check_and_unlock_achievements(self, user_id: str) -> list:
        """检查并解锁新成就，返回新解锁的成就元数据列表。"""
        stats = await self._get_user_achievement_stats(user_id)
        new_achievements = []
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT achievement_id FROM achievements WHERE user_id = ?",
                    (user_id,))
                rows = await cursor.fetchall()
                unlocked = {r[0] for r in rows}
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for aid, meta in ACHIEVEMENTS.items():
                    if aid not in unlocked and meta['check'](stats):
                        await conn.execute(
                            "INSERT OR IGNORE INTO achievements (user_id, achievement_id, unlocked_at) VALUES (?, ?, ?)",
                            (user_id, aid, now_str))
                        new_achievements.append(meta)
                await conn.commit()
        except Exception as e:
            logger.error(f"解锁成就失败 ({user_id}): {e}")
        return new_achievements

    # ------------------------------------------------------------ LLM
    async def _rollback_llm_placeholder(self, user_key, count_key):
        """回滚 LLM 触发占位（删用户标记、递减全群计数），供空回复/异常路径复用。"""
        try:
            async with aiosqlite.connect(self.db_path, timeout=5.0) as conn:
                await conn.execute("DELETE FROM metadata WHERE key = ?", (user_key,))
                await conn.execute(
                    "UPDATE metadata SET value = CAST(CAST(value AS INTEGER) - 1 AS TEXT) "
                    "WHERE key = ? AND CAST(value AS INTEGER) > 0",
                    (count_key,))
                await conn.commit()
        except Exception as e:
            logger.error(f"回滚 LLM 占位失败: {e}")

    async def _maybe_llm_reply(self, user_id: str, adjusted_date: str):
        """条件触发娅娅 LLM 回复：今日累计达阈值 + 概率命中 + 原子占用次数上限。"""
        if not self.llm_enabled:
            return None
        user_key = None
        count_key = None
        try:
            if self.llm_daily_min_cakes > 0:
                async with aiosqlite.connect(self.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT COALESCE(SUM(cake_count),0) FROM checkin WHERE user_id = ? AND checkin_date = ?",
                        (user_id, adjusted_date))
                    row = await cursor.fetchone()
                    today_total = row[0] if row else 0
                if today_total < self.llm_daily_min_cakes:
                    return None
            if random.random() >= self.llm_trigger_probability:
                return None
            # 原子占位：user_key 未占用 且 count_key 未达上限 才成功（与每日限额同思路）
            user_key = f"llm_user:{user_id}:{adjusted_date}"
            count_key = f"llm_count:{adjusted_date}"
            async with aiosqlite.connect(self.db_path, timeout=5.0) as conn:
                cur1 = await conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                    (user_key, adjusted_date))
                if cur1.rowcount == 0:
                    return None  # 该用户今日已触发过
                if self.llm_daily_limit > 0:
                    cur2 = await conn.execute(
                        "INSERT INTO metadata (key, value) VALUES (?, '1') "
                        "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
                        "WHERE CAST(CAST(value AS INTEGER) AS INTEGER) < ?",
                        (count_key, self.llm_daily_limit))
                    if cur2.rowcount == 0:
                        await conn.execute("DELETE FROM metadata WHERE key = ?", (user_key,))
                        await conn.commit()
                        return None  # 全群每日上限已满
                else:
                    await conn.execute(
                        "INSERT INTO metadata (key, value) VALUES (?, '1') "
                        "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)",
                        (count_key,))
                await conn.commit()
            provider = await self.context.get_using_provider_async()
            resp = await provider.text_chat(
                prompt=LLM_USER_PROMPT, system_prompt=LLM_SYSTEM_PROMPT)
            text = (getattr(resp, 'completion_text', '') or '').strip()
            if not text:
                # 占位回滚，避免空回复白占次数
                await self._rollback_llm_placeholder(user_key, count_key)
                return None
            return text
        except Exception as e:
            logger.error(f"娅娅 LLM 对话失败: {e}")
            if user_key:
                # 占位已写入但后续（provider/网络等）失败，回滚避免吞掉当日触发机会
                await self._rollback_llm_placeholder(user_key, count_key)
            return None

    @filter.custom_filter(trigger_filter(r'成就$'), description='查看娅娅成就墙')
    async def handle_cake_achievements(self, event: AstrMessageEvent):
        """查看娅娅成就墙：列出全部成就的解锁/未解锁状态与当前进度。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT achievement_id FROM achievements WHERE user_id = ?",
                    (user_id,))
                rows = await cursor.fetchall()
        except Exception as e:
            logger.error(f"查询成就失败: {e}")
            yield event.plain_result(ACHIEVEMENTS_ERROR)
            return
        unlocked = {r[0] for r in rows}
        stats = await self._get_user_achievement_stats(user_id)
        lines = [ACHIEVEMENTS_TITLE.format(name=user_name, unlocked=len(unlocked),
                                           total=len(ACHIEVEMENTS))]
        lines.append("")
        for aid, meta in ACHIEVEMENTS.items():
            if aid in unlocked:
                lines.append(ACHIEVEMENT_UNLOCKED_LINE.format(
                    icon=meta['icon'], name=meta['name'], desc=meta['desc']))
            else:
                lines.append(ACHIEVEMENT_LOCKED.format(
                    icon=meta['icon'], name=meta['name'], desc=meta['desc']))
        lines.append("")
        lines.append(ACHIEVEMENTS_PROGRESS.format(
            total_cakes=stats['total_cakes'], streak=stats['streak'],
            total_helped=stats['total_helped']))
        yield event.plain_result("\n".join(lines))

    @filter.custom_filter(trigger_filter(r'+(\s+|$)', char_class=True), description='🍰/蛋糕 喂娅娅小蛋糕')
    async def handle_cake_checkin(self, event: AstrMessageEvent):
        """喂娅娅小蛋糕：发送 🍰/蛋糕 计数并生成日历图；@某人 为替喂，超限提示娅娅吃不下。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        text = event.get_message_str()
        raw_cake_count = self._count_trigger_chars(text)
        if raw_cake_count <= 0:
            return  # 前缀只是触发词的部分字符（非完整词），静默忽略
        too_many = raw_cake_count > self.max_cakes_per_message
        cake_count = min(raw_cake_count, self.max_cakes_per_message)
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        adjusted_date = self._get_adjusted_date()
        group_id = str(event.get_group_id() or '')
        targets = self._get_at_targets(event)

        if targets:
            # 帮喂也计入每日次数限额（原子占用一次额度）
            daily_op = await self._try_consume_daily_op(user_id, group_id, adjusted_date)
            if daily_op is None:
                yield event.plain_result(CHECKIN_ERROR)
                return
            if not daily_op:
                yield event.plain_result(self._daily_limit_reply())
                return
            for target_id in targets:
                try:
                    async with aiosqlite.connect(self.db_path) as conn:
                        await conn.execute(
                            "INSERT INTO help_record (helper_id, target_id, group_id, date, count) VALUES (?, ?, ?, ?, ?) "
                            "ON CONFLICT(helper_id, target_id, group_id, date) DO UPDATE SET count = count + ?",
                            (user_id, target_id, group_id, adjusted_date, cake_count, cake_count))
                        await conn.commit()
                except Exception as e:
                    logger.error(f"帮喂蛋糕失败: {e}")
            at_names = []
            for target_id in targets:
                name = await self.core._get_user_name(event, target_id)
                at_names.append(name)
            egg = self._black_egg()
            help_text = self._help_reply('、'.join(at_names), egg)
            chain = [Plain(help_text)]
            if too_many:
                chain.append(Plain(self._feed_too_many(egg)))
            # 帮喂成就：helper 的替喂成就 + 每个 target 的被喂成就
            for ach_uid in [user_id] + list(targets):
                try:
                    for a in await self._check_and_unlock_achievements(ach_uid):
                        chain.append(Plain(ACHIEVEMENT_UNLOCK.format(icon=a['icon'], name=a['name'], desc=a['desc'])))
                except Exception as e:
                    logger.error(f"帮喂成就检查失败: {e}")
            for target_id in targets:
                try:
                    target_name = await self.core._get_user_name(event, target_id)
                    result = await self.core._generate_and_send_calendar(
                        event, target_id, target_name, self.db_path, adjusted_date, dark=egg)
                    if result[1]:
                        chain.append(Image(file=result[1]))
                    elif result[0]:
                        chain.append(Plain(result[0]))
                except Exception as e:
                    logger.error(f"生成被喂者日历失败: {e}")
            yield event.chain_result(chain)
        else:
            # 每日次数限额（原子占用一次额度，每条喂蛋糕消息算 1 次）
            daily_op = await self._try_consume_daily_op(user_id, group_id, adjusted_date)
            if daily_op is None:
                yield event.plain_result(CHECKIN_ERROR)
                return
            if not daily_op:
                yield event.plain_result(self._daily_limit_reply())
                return
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(
                        "INSERT INTO checkin (user_id, group_id, checkin_date, cake_count) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(user_id, group_id, checkin_date) DO UPDATE SET cake_count = cake_count + ?",
                        (user_id, group_id, adjusted_date, cake_count, cake_count))
                    await conn.commit()
            except Exception as e:
                logger.error(f"喂蛋糕失败: {e}")
                yield event.plain_result(CHECKIN_ERROR)
                return

            egg = self._black_egg()
            result = await self.core._generate_and_send_calendar(
                event, user_id, user_name, self.db_path, adjusted_date, dark=egg)

            # 成就检查：累计/单日/连续
            new_achievements = await self._check_and_unlock_achievements(user_id)
            ach_texts = [ACHIEVEMENT_UNLOCK.format(icon=a['icon'], name=a['name'], desc=a['desc'])
                         for a in new_achievements]
            # LLM 概率对话（触发达妮娅彩蛋时禁用，保持神秘感）
            llm_text = None if egg else await self._maybe_llm_reply(user_id, adjusted_date)

            chain = []
            if result[2]:
                chain.append(Plain(result[0]))
            elif result[1]:
                chain.append(Plain(self._feed_reply(cake_count, egg)))
                chain.append(Image(file=result[1]))
            else:
                chain.append(Plain(result[0] or self._feed_reply(cake_count, egg)))
            if too_many:
                chain.append(Plain(self._feed_too_many(egg)))
            for t in ach_texts:
                chain.append(Plain(t))
            if llm_text:
                chain.append(Plain(LLM_REPLY_PREFIX.format(text=llm_text)))
            yield event.chain_result(chain)

    @filter.custom_filter(trigger_filter(r'补签\s+\d{1,2}(?:\s+\d+)?\s*$'), description='🍰补签')
    async def handle_cake_retro(self, event: AstrMessageEvent):
        """补签：🍰补签 DD [次数]，为本月某天补喂蛋糕（不能补未来日期）。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        rest = self._after_trigger(event.get_message_str().strip())
        if rest is None:
            return
        m = re.match(r'^补签\s+(\d{1,2})(?:\s+(\d+))?\s*$', rest)
        if not m:
            yield event.plain_result(RETRO_FORMAT_ERR)
            return
        day = int(m.group(1))
        raw_count = int(m.group(2)) if m.group(2) else 1
        too_many = raw_count > self.max_cakes_per_message
        count = min(raw_count, self.max_cakes_per_message)
        # 以调整日（含 day_start_time）为基准：凌晨 day_start 前算前一天，补签不能越过它
        today_adj = self._get_adjusted_date()
        today_adj_dt = datetime.strptime(today_adj, "%Y-%m-%d").date()
        year, month = today_adj_dt.year, today_adj_dt.month
        days_in_month = calendar.monthrange(year, month)[1]
        if day < 1 or day > days_in_month:
            yield event.plain_result(RETRO_INVALID_DAY.format(days=days_in_month))
            return
        if day > today_adj_dt.day:
            yield event.plain_result(RETRO_FUTURE)
            return

        adjusted_date = f"{year}-{month:02d}-{day:02d}"
        group_id = str(event.get_group_id() or '')
        # 补签操作也占用今天的喂蛋糕次数（原子占用）
        today_ops_date = self._get_adjusted_date()
        daily_op = await self._try_consume_daily_op(user_id, group_id, today_ops_date)
        if daily_op is None:
            yield event.plain_result(RETRO_ERROR)
            return
        if not daily_op:
            yield event.plain_result(self._daily_limit_reply())
            return
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "INSERT INTO checkin (user_id, group_id, checkin_date, cake_count) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id, group_id, checkin_date) DO UPDATE SET cake_count = cake_count + ?",
                    (user_id, group_id, adjusted_date, count, count))
                await conn.commit()
        except Exception as e:
            logger.error(f"补签失败: {e}")
            yield event.plain_result(RETRO_ERROR)
            return

        user_name = await self.core._get_user_name(event, user_id)
        egg = self._black_egg()
        new_achievements = await self._check_and_unlock_achievements(user_id)
        ach_texts = [ACHIEVEMENT_UNLOCK.format(icon=a['icon'], name=a['name'], desc=a['desc'])
                     for a in new_achievements]
        result = await self.core._generate_and_send_calendar(
            event, user_id, user_name, self.db_path, dark=egg)
        chain = []
        if result[0]:
            chain.append(Plain(result[0]))
        elif result[1]:
            chain.append(Image(file=result[1]))
        if too_many:
            chain.append(Plain(self._feed_too_many(egg)))
        for t in ach_texts:
            chain.append(Plain(t))
        yield event.chain_result(chain)

    @filter.custom_filter(trigger_filter(r'重置榜单(\s.*)?$'), description='清空今天的喂蛋糕计数（可@他人）')
    async def handle_cake_reset(self, event: AstrMessageEvent):
        """重置榜单：管理员清空今天（或 @他人）的喂蛋糕计数。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        if not await self._is_group_admin(event, str(event.get_group_id() or ''), str(event.get_sender_id())):
            yield event.plain_result(RESET_ADMIN_ONLY)
            return
        targets = self._get_at_targets(event)
        if targets:
            user_id = targets[0]
            who = '他'
        else:
            user_id = str(event.get_sender_id())
            who = '自己'
        group_id = str(event.get_group_id() or '')
        adjusted_date = self._get_adjusted_date()
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT cake_count FROM checkin WHERE user_id = ? AND group_id = ? AND checkin_date = ?",
                    (user_id, group_id, adjusted_date))
                row = await cursor.fetchone()
                await conn.execute(
                    "DELETE FROM checkin WHERE user_id = ? AND group_id = ? AND checkin_date = ?",
                    (user_id, group_id, adjusted_date))
                await conn.commit()
            if row:
                yield event.plain_result(RESET_DONE.format(
                    who=who, date=adjusted_date, count=row[0]))
            else:
                yield event.plain_result(RESET_EMPTY)
        except Exception as e:
            logger.error(f"重置失败: {e}")
            yield event.plain_result(RESET_ERROR)

    @filter.custom_filter(trigger_filter(r'日历$'), description='查看娅娅本月日历')
    async def handle_cake_calendar(self, event: AstrMessageEvent):
        """查看娅娅本月日历：生成粉色系（或所选主题）投喂日历图。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        today_adj = self._get_adjusted_date()
        result = await self.core._generate_and_send_calendar(
            event, user_id, user_name, self.db_path, today_adj)
        if result[0]:
            yield event.plain_result(result[0])
        elif result[1]:
            yield event.image_result(result[1])

    @filter.custom_filter(trigger_filter(r'(?:报告|分析)(?:\s+\d{2}|\s+\d{4})?$'), description='🍰报告/分析')
    async def handle_cake_analysis(self, event: AstrMessageEvent):
        """投喂分析报告：本月 / 指定月份 / 指定年份的娅娅投喂数据分析图。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        rest = self._after_trigger(event.get_message_str().strip())
        if rest is None:
            return
        m = re.match(r'^(?:报告|分析)\s*(\d{2}|\d{4})?$', rest)
        if m is None:
            yield event.plain_result(ANALYSIS_BAD_MONTH)
            return
        param = m.group(1)

        today = date.today()
        if param is None:
            year, month = today.year, today.month
            period_data = await self.core._get_user_period_data(user_id, year, month)
            report, rate = await self.core._generate_monthly_analysis_report(
                user_name, year, month, period_data)
            target_period = f"{year}年{month}月"
        elif len(param) == 2:
            month = int(param)
            year = today.year
            if month < 1 or month > 12:
                yield event.plain_result(ANALYSIS_BAD_MONTH)
                return
            period_data = await self.core._get_user_period_data(user_id, year, month)
            report, rate = await self.core._generate_monthly_analysis_report(
                user_name, year, month, period_data)
            target_period = f"{year}年{month:02d}月"
        else:
            year = int(param)
            yearly_data = await self.core._get_user_yearly_data(user_id, year)
            report = await self.core._generate_yearly_analysis_report(
                user_name, year, yearly_data)
            rate = 0
            target_period = f"{year}年"

        if not report:
            yield event.plain_result(NO_RECORD)
            return

        try:
            image_path = await asyncio.to_thread(
                self.core._create_analysis_image,
                user_name, target_period, report, rate, "蛋糕")
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成娅娅投喂报告图片失败: {e}")
            yield event.plain_result(report)

    @filter.custom_filter(trigger_filter(r'生涯$'), description='娅娅生涯档案')
    async def handle_cake_career(self, event: AstrMessageEvent):
        """娅娅生涯档案：累计投喂 / 单日之最 / 最长断喂等数据总览图。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT checkin_date, cake_count FROM checkin WHERE user_id = ? ORDER BY checkin_date ASC",
                    (user_id,))
                rows = await cursor.fetchall()
        except Exception as e:
            logger.error(f"查询生涯数据失败: {e}")
            yield event.plain_result(CAREER_ERROR)
            return

        if not rows:
            yield event.plain_result(NO_RECORD)
            return

        try:
            stats = self._compute_career_stats(rows)
        except Exception as e:
            logger.error(f"计算生涯数据失败: {e}")
            yield event.plain_result(CAREER_ERROR)
            return
        try:
            image_path = await asyncio.to_thread(
                self.core._create_career_image,
                user_name, stats, "娅娅")
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成生涯图片失败: {e}")
            yield event.plain_result(CAREER_IMG_ERROR)

    def _compute_career_stats(self, rows):
        total_count = sum(row[1] for row in rows) if rows else 0
        total_days = len(rows)
        first_date_str = rows[0][0] if rows else ""
        first_date = datetime.strptime(first_date_str, "%Y-%m-%d").date() if first_date_str else date.today()
        today = date.today()
        total_span_days = (today - first_date).days

        if total_span_days > 0:
            active_ratio = total_days / total_span_days * 100
            daily_avg = total_count / total_span_days
        else:
            active_ratio = 100 if total_days > 0 else 0
            daily_avg = total_count if total_count > 0 else 0

        max_day_row = max(rows, key=lambda r: r[1])
        max_day_count = max_day_row[1]
        max_day_date = max_day_row[0]

        monthly_stats = {}
        for r in rows:
            ym = r[0][:7]
            if ym not in monthly_stats:
                monthly_stats[ym] = {'count': 0, 'days': 0}
            monthly_stats[ym]['count'] += r[1]
            monthly_stats[ym]['days'] += 1

        max_month_ym = max(monthly_stats, key=lambda k: monthly_stats[k]['count'])
        max_month_count = monthly_stats[max_month_ym]['count']
        max_month_str = max_month_ym

        min_month_ym = min(monthly_stats, key=lambda k: monthly_stats[k]['count'])
        min_month_count = monthly_stats[min_month_ym]['count']
        min_month_str = min_month_ym

        all_dates = sorted([datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows])
        max_gap = timedelta(0)
        gap_start = all_dates[0]
        for i in range(1, len(all_dates)):
            gap = all_dates[i] - all_dates[i - 1]
            if gap > max_gap:
                max_gap = gap
                gap_start = all_dates[i - 1]
        if max_gap.days > 0:
            rest_period_str = CAREER_REST_GAP.format(start=gap_start, days=max_gap.days)
        else:
            rest_period_str = CAREER_REST_ALWAYS

        if min_month_count == 0:
            sage_comment = CAREER_SAGE_ZERO
        elif min_month_count <= 2:
            sage_comment = CAREER_SAGE_LOW
        else:
            sage_comment = ""

        last_date = datetime.strptime(rows[-1][0], "%Y-%m-%d").date()
        status_day = (today - last_date).days
        if status_day == 0:
            status_comment = CAREER_STATUS_0
        elif status_day <= 3:
            status_comment = CAREER_STATUS_LE3.format(days=status_day)
        elif status_day <= 7:
            status_comment = CAREER_STATUS_LE7.format(days=status_day)
        elif status_day <= 30:
            status_comment = CAREER_STATUS_LE30.format(days=status_day)
        else:
            status_comment = CAREER_STATUS_OVER.format(days=status_day)

        summary_comment = CAREER_SUMMARY_LEVELS[-1][1]
        for threshold, label in CAREER_SUMMARY_LEVELS:
            if daily_avg > threshold:
                summary_comment = label
                break

        return {
            'summary_comment': summary_comment,
            'first_date_str': first_date_str,
            'total_span_days': total_span_days,
            'total_count': total_count,
            'total_days': total_days,
            'active_ratio': round(active_ratio, 1),
            'daily_avg': round(daily_avg, 2),
            'max_day_count': max_day_count,
            'max_day_date': max_day_date,
            'max_month_count': max_month_count,
            'max_month_str': max_month_str,
            'min_month_count': min_month_count,
            'min_month_str': min_month_str,
            'rest_period_str': rest_period_str,
            'sage_comment': sage_comment,
            'status_day': status_day,
            'status_comment': status_comment,
        }

    async def _format_ranking(self, event, raw_data, name_map=None):
        """格式化榜单。name_map（uid→昵称）提供时直接用，避免逐个 API 查询。"""
        result = []
        for idx, (uid, count) in enumerate(raw_data, 1):
            uid = str(uid)
            if name_map is not None:
                name = name_map.get(uid, uid)
            else:
                name = await self.core._get_user_name(event, uid)
            result.append((idx, uid, name, count))
        return result

    async def _get_achievement_counts(self, user_ids: set) -> dict:
        """查询一组用户已解锁成就数量。"""
        if not user_ids:
            return {}
        ach_map = {}
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                for uid in user_ids:
                    cursor = await conn.execute(
                        "SELECT COUNT(*) FROM achievements WHERE user_id = ?", (str(uid),))
                    row = await cursor.fetchone()
                    ach_map[str(uid)] = row[0] if row else 0
        except Exception as e:
            logger.error(f"查询成就徽章数失败: {e}")
        return ach_map

    def _download_avatar_sync(self, qq_id: str, save_path: str) -> bool:
        """同步下载头像到文件（由调用方 to_thread 包装，避免阻塞事件循环）。"""
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

    async def _download_all_avatars(self, all_data_lists):
        """并发下载本页用户头像到 avatar_dir（排行榜渲染时调用）。"""
        pending = set()
        for data_list in all_data_lists:
            for row in data_list:
                uid = str(row[1])
                save_path = os.path.join(self.avatar_dir, f"{uid}.png")
                if not os.path.exists(save_path):
                    pending.add((uid, save_path))
        if not pending:
            return
        await asyncio.gather(*[
            asyncio.to_thread(self._download_avatar_sync, uid, path)
            for uid, path in pending
        ])

    @filter.custom_filter(trigger_filter(r'(?:榜(\s+\d+)?$|[日月]榜(\s+\d+)?$)', prefix='查看|查询'), description='🍰排行榜')
    async def handle_cake_ranking(self, event: AstrMessageEvent):
        """排行榜：自己喂 / 被喂 / 替喂 × 今日 / 本月三栏排行图，支持翻页。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        text = event.get_message_str().strip()
        m = re.search(r'(\d+)\s*$', text)
        page = int(m.group(1)) if m else 1
        if page < 1:
            page = 1

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result(RANKING_GROUP_ONLY)
            return

        members = await self.core._get_group_members(event, str(group_id))
        if not members:
            yield event.plain_result(RANKING_NO_MEMBERS)
            return
        group_user_ids = {str(m.get('user_id')) for m in members}

        today = date.today()
        year, month_val = today.year, today.month
        adjusted_date_str = self._get_adjusted_date()
        month_str = f"{year}-{month_val:02d}"

        raw_today_self = await self.core._get_period_ranking_data(
            self.db_path, "checkin_date = ?", (adjusted_date_str,), group_user_ids, str(group_id))
        raw_today_received = await self.core._get_received_ranking_data(
            self.db_path, "date = ?", (adjusted_date_str,), group_user_ids, str(group_id))
        raw_today_helped = await self.core._get_help_ranking_data(
            self.db_path, "date = ?", (adjusted_date_str,), group_user_ids, str(group_id))

        raw_month_self = await self.core._get_period_ranking_data(
            self.db_path, "strftime('%Y-%m', checkin_date) = ?", (month_str,), group_user_ids, str(group_id))
        raw_month_received = await self.core._get_received_ranking_data(
            self.db_path, "strftime('%Y-%m', date) = ?", (month_str,), group_user_ids, str(group_id))
        raw_month_helped = await self.core._get_help_ranking_data(
            self.db_path, "strftime('%Y-%m', date) = ?", (month_str,), group_user_ids, str(group_id))

        # 批量昵称映射（用群成员列表一次取回，避免逐个 API 查询）
        name_map = {
            str(m.get('user_id')): (str(m.get('card') or m.get('nickname') or m.get('user_id')))
            for m in members
        }
        today_self = await self._format_ranking(event, raw_today_self, name_map)
        today_received = await self._format_ranking(event, raw_today_received, name_map)
        today_helped = await self._format_ranking(event, raw_today_helped, name_map)
        month_self = await self._format_ranking(event, raw_month_self, name_map)
        month_received = await self._format_ranking(event, raw_month_received, name_map)
        month_helped = await self._format_ranking(event, raw_month_helped, name_map)

        page_size = max(int(self.ranking_display_count or 10), 1)
        max_len = max(
            len(raw_today_self), len(raw_today_received), len(raw_today_helped),
            len(raw_month_self), len(raw_month_received), len(raw_month_helped))
        total_pages = max(math.ceil(max_len / page_size), 1)
        if page > total_pages:
            page = total_pages

        paginate = lambda d, p: d[(p - 1) * page_size:p * page_size]
        today_self_page = paginate(today_self, page)
        today_received_page = paginate(today_received, page)
        today_helped_page = paginate(today_helped, page)
        month_self_page = paginate(month_self, page)
        month_received_page = paginate(month_received, page)
        month_helped_page = paginate(month_helped, page)

        # 成就徽章数（本页用户）
        page_uids = {row[1] for lst in (today_self_page, today_received_page, today_helped_page,
                                        month_self_page, month_received_page, month_helped_page)
                     for row in lst}
        ach_map = await self._get_achievement_counts(page_uids)
        enrich = lambda lst: [row + (ach_map.get(row[1], 0),) for row in lst]
        today_self_page = enrich(today_self_page)
        today_received_page = enrich(today_received_page)
        today_helped_page = enrich(today_helped_page)
        month_self_page = enrich(month_self_page)
        month_received_page = enrich(month_received_page)
        month_helped_page = enrich(month_helped_page)

        # 下载本页用户头像（排行榜渲染用），仅 QQ 平台有效
        if event.get_platform_name() == "aiocqhttp":
            try:
                await self._download_all_avatars(
                    (today_self_page, today_received_page, today_helped_page,
                     month_self_page, month_received_page, month_helped_page))
            except Exception as e:
                logger.error(f"下载排行头像失败: {e}")

        image_path = None
        try:
            image_path = await asyncio.to_thread(
                self.core._create_three_column_ranking_image,
                today_self_page, today_received_page, today_helped_page,
                month_self_page, month_received_page, month_helped_page,
                year, month_val, page, total_pages, "🍰", self.avatar_dir, ach_map,
                max_rows=page_size)
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成排行榜图片失败: {e}")
            yield event.plain_result(RANKING_ERROR)
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

    @filter.custom_filter(trigger_filter(r'帮助$'), description='🍰帮助')
    async def handle_cake_help(self, event: AstrMessageEvent):
        """帮助：列出全部喂蛋糕命令的使用说明。"""
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        yield event.plain_result(HELP_TEXT)
