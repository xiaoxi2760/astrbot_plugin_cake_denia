"""🍰 cake_denia —— 鸣潮达妮娅（娅娅）喂小蛋糕插件。

发送 🍰 给娅娅喂一块小蛋糕。支持帮喂、日历、报告、生涯、补签、排行榜、
成就、LLM 概率对话等功能。

基于 astrbot_plugin_deer_check v3 改造（单系统：只有喂蛋糕）。
"""
import aiosqlite
import asyncio
import calendar
import math
import os
import random
import re
from datetime import date, datetime, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Plain, Image
from astrbot.api import logger
from astrbot.core.star import StarTools

from .cake_core import CakeCore

FONT_FILE = "font.ttf"
DB_NAME = "yaya_cake.db"

# 娅娅的撒娇文案
FEED_SUCCESS = [
    "娅娅眼睛一亮，开心地吃掉了小蛋糕～谢谢！蛋糕真好吃！🍰",
    "娅娅小口小口地吃着蛋糕，幸福得眯起眼睛～",
    "娅娅接过蛋糕，甜甜地说：谢谢你呀！",
    "娅娅捧着蛋糕转了个圈，开心得不得了～",
]

FEED_MULTI = [
    "娅娅幸福得眯起眼睛，一口气吃了{count}块小蛋糕，肚子圆滚滚的～",
    "娅娅惊喜地看着{count}块小蛋糕，每吃一块都要夸你一句！",
]

HELP_FEED = "已经替{names}给娅娅喂了蛋糕～娅娅说谢谢你们！"

# ---------------------------------------------------------------- 成就定义
# check 接收 stats: {total_cakes, total_days, max_daily, streak, total_helped, total_received}
ACHIEVEMENTS = {
    'cake_10': {'name': '初尝甜蜜', 'icon': '🍰', 'desc': '累计喂满 10 块蛋糕',
                'check': lambda s: s['total_cakes'] >= 10},
    'cake_50': {'name': '蛋糕学徒', 'icon': '🍰', 'desc': '累计喂满 50 块蛋糕',
                'check': lambda s: s['total_cakes'] >= 50},
    'cake_100': {'name': '蛋糕大师', 'icon': '🎂', 'desc': '累计喂满 100 块蛋糕',
                 'check': lambda s: s['total_cakes'] >= 100},
    'cake_365': {'name': '一年份的甜', 'icon': '🌈', 'desc': '累计喂满 365 块蛋糕',
                 'check': lambda s: s['total_cakes'] >= 365},
    'cake_1000': {'name': '蛋糕之神', 'icon': '👑', 'desc': '累计喂满 1000 块蛋糕',
                  'check': lambda s: s['total_cakes'] >= 1000},
    'streak_3': {'name': '连续投喂3天', 'icon': '🔥', 'desc': '连续 3 天给娅娅喂蛋糕',
                 'check': lambda s: s['streak'] >= 3},
    'streak_7': {'name': '连续投喂7天', 'icon': '🔥', 'desc': '连续 7 天给娅娅喂蛋糕',
                 'check': lambda s: s['streak'] >= 7},
    'streak_30': {'name': '连续投喂30天', 'icon': '🔥', 'desc': '连续 30 天给娅娅喂蛋糕',
                  'check': lambda s: s['streak'] >= 30},
    'daily_5': {'name': '蛋糕暴击', 'icon': '⚡', 'desc': '单日喂满 5 块蛋糕',
                'check': lambda s: s['max_daily'] >= 5},
    'daily_10': {'name': '蛋糕轰炸', 'icon': '⚡', 'desc': '单日喂满 10 块蛋糕',
                 'check': lambda s: s['max_daily'] >= 10},
    'help_5': {'name': '替喂小天使', 'icon': '🤝', 'desc': '替别人喂满 5 块蛋糕',
               'check': lambda s: s['total_helped'] >= 5},
    'help_20': {'name': '金牌代喂', 'icon': '🤝', 'desc': '替别人喂满 20 块蛋糕',
                'check': lambda s: s['total_helped'] >= 20},
    'received_50': {'name': '人气蛋糕师', 'icon': '💝', 'desc': '被喂满 50 块蛋糕',
                    'check': lambda s: s['total_received'] >= 50},
}

# ---------------------------------------------------------------- LLM 娅娅人设
LLM_SYSTEM_PROMPT = (
    "你是鸣潮中的角色达妮娅（昵称娅娅），一个元气、可爱、有点贪吃的女孩。"
    "有人刚刚给你喂了小蛋糕，请用撒娇、开心、感谢的语气回应一小段话（60字以内），"
    "可以提到蛋糕很好吃、很幸福，语气亲昵。不要提及你是AI或模型。"
)
LLM_USER_PROMPT = "今天收到了一块小蛋糕，娅娅想说点什么？"

ACHIEVEMENT_UNLOCK = "🎉 解锁新成就：【{icon} {name}】{desc}！"


class CakeDeniaPlugin(Star):

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        config = config if config is not None else {}
        self.group_whitelist = config.get("group_whitelist", [])
        self.user_blacklist = config.get("user_blacklist", [])
        self.day_start_time = config.get("day_start_time", "00:00")
        self.auto_delete_last_month_data = bool(config.get("auto_delete_last_month_data", True))
        self.daily_max_checkins = int(config.get("daily_max_checkins", 0))
        self.monthly_max_checkins = int(config.get("monthly_max_checkins", 0))
        self.ranking_display_count = int(config.get("ranking_display_count", 10))
        self.llm_enabled = bool(config.get("llm_enabled", True))
        try:
            self.llm_trigger_probability = float(config.get("llm_trigger_probability", 0.3))
        except (ValueError, TypeError):
            self.llm_trigger_probability = 0.3
        self.llm_daily_min_cakes = int(config.get("llm_daily_min_cakes", 3))
        self.llm_daily_limit = int(config.get("llm_daily_limit", 5))

        data_dir = StarTools.get_data_dir("cake_denia")
        plugin_dir = os.path.dirname(os.path.abspath(__file__))

        self.db_path = os.path.join(data_dir, DB_NAME)
        self.font_path = os.path.join(plugin_dir, FONT_FILE)
        self.temp_dir = os.path.join(plugin_dir, "tmp")
        self.avatar_dir = os.path.join(plugin_dir, "avatars")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)

        self.core = CakeCore(self.font_path, self.db_path, self.temp_dir)

        self._initialized = False
        self._init_lock = asyncio.Lock() if False else None

    async def _ensure_initialized(self):
        if self._initialized:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._initialized:
                return
            await self._init_db()
            await self._monthly_cleanup()
            self._initialized = True

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
            if self.group_whitelist and str(group_id) not in [str(g) for g in self.group_whitelist]:
                return False
        sender_id = event.get_sender_id()
        if str(sender_id) in self.user_blacklist:
            return False
        return True

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

    def _feed_reply(self, count: int) -> str:
        if count > 1:
            tpl = random.choice(FEED_MULTI)
            return tpl.format(count=count)
        return random.choice(FEED_SUCCESS)

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
                    "SELECT COALESCE(MAX(cake_count),0) FROM checkin WHERE user_id = ?",
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
                    cur = date.today()
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
    async def _maybe_llm_reply(self, user_id: str, adjusted_date: str):
        """条件触发娅娅 LLM 回复：今日累计达阈值 + 概率命中 + 次数限制。"""
        if not self.llm_enabled:
            return None
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
            user_key = f"llm_user:{user_id}:{adjusted_date}"
            count_key = f"llm_count:{adjusted_date}"
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT value FROM metadata WHERE key = ?", (user_key,))
                row = await cursor.fetchone()
                if row:
                    return None  # 该用户今日已触发过
                cursor = await conn.execute(
                    "SELECT value FROM metadata WHERE key = ?", (count_key,))
                row = await cursor.fetchone()
                global_count = int(row[0]) if row and row[0] else 0
                if self.llm_daily_limit > 0 and global_count >= self.llm_daily_limit:
                    return None
            if random.random() >= self.llm_trigger_probability:
                return None
            provider = await self.context.get_using_provider_async()
            resp = await provider.text_chat(
                prompt=LLM_USER_PROMPT, system_prompt=LLM_SYSTEM_PROMPT)
            text = (getattr(resp, 'completion_text', '') or '').strip()
            if not text:
                return None
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (user_key, adjusted_date))
                await conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)",
                    (count_key, str(global_count + 1)))
                await conn.commit()
            return text
        except Exception as e:
            logger.error(f"娅娅 LLM 对话失败: {e}")
            return None

    @filter.regex(r'^[🍰蛋糕]成就$', description='查看娅娅成就墙')
    async def handle_cake_achievements(self, event: AstrMessageEvent):
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
            yield event.plain_result("查询成就失败了 >_<")
            return
        unlocked = {r[0] for r in rows}
        stats = await self._get_user_achievement_stats(user_id)
        lines = [f"🏆 {user_name} 的娅娅成就墙（{len(unlocked)}/{len(ACHIEVEMENTS)}）"]
        lines.append("")
        for aid, meta in ACHIEVEMENTS.items():
            if aid in unlocked:
                lines.append(f"{meta['icon']} ✅ {meta['name']}：{meta['desc']}")
            else:
                lines.append(f"{meta['icon']} 🔒 {meta['name']}：{meta['desc']}")
        lines.append("")
        lines.append(f"当前进度：累计 {stats['total_cakes']} 块 · 连续 {stats['streak']} 天 · 替喂 {stats['total_helped']} 块")
        yield event.plain_result("\n".join(lines))

    @filter.regex(r'^[🍰蛋糕]+(\s+|$)', description='🍰/蛋糕 喂娅娅小蛋糕')
    async def handle_cake_checkin(self, event: AstrMessageEvent):
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        text = event.get_message_str()
        m_prefix = re.match(r'^[🍰蛋糕]+', text)
        cake_count = len(m_prefix.group(0)) if m_prefix else 0
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        adjusted_date = self._get_adjusted_date()
        group_id = str(event.get_group_id() or '')
        targets = self._get_at_targets(event)

        if targets:
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
            chain = [Plain(HELP_FEED.format(names='、'.join(at_names)))]
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
                        event, target_id, target_name, self.db_path, adjusted_date)
                    if result[1]:
                        chain.append(Image(file=result[1]))
                    elif result[0]:
                        chain.append(Plain(result[0]))
                except Exception as e:
                    logger.error(f"生成被喂者日历失败: {e}")
            yield event.chain_result(chain)
        else:
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    cursor = await conn.execute(
                        "SELECT COALESCE(SUM(cake_count), 0) FROM checkin WHERE user_id = ? AND group_id = ? AND checkin_date = ?",
                        (user_id, group_id, adjusted_date))
                    row = await cursor.fetchone()
                    daily_total = row[0] if row else 0

                    month_str = adjusted_date[:7]
                    cursor = await conn.execute(
                        "SELECT COALESCE(SUM(cake_count), 0) FROM checkin WHERE user_id = ? AND group_id = ? AND strftime('%Y-%m', checkin_date) = ?",
                        (user_id, group_id, month_str))
                    row = await cursor.fetchone()
                    monthly_total = row[0] if row else 0

                    if self.daily_max_checkins > 0 and daily_total + cake_count > self.daily_max_checkins:
                        yield event.plain_result(f"娅娅一天最多吃 {self.daily_max_checkins} 块蛋糕，今天的额度已经用完啦！")
                        return
                    if self.monthly_max_checkins > 0 and monthly_total + cake_count > self.monthly_max_checkins:
                        yield event.plain_result(f"娅娅一个月最多吃 {self.monthly_max_checkins} 块蛋糕，本月额度已经用完啦！")
                        return

                    await conn.execute(
                        "INSERT INTO checkin (user_id, group_id, checkin_date, cake_count) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(user_id, group_id, checkin_date) DO UPDATE SET cake_count = cake_count + ?",
                        (user_id, group_id, adjusted_date, cake_count, cake_count))
                    await conn.commit()
            except Exception as e:
                logger.error(f"喂蛋糕失败: {e}")
                yield event.plain_result("喂蛋糕失败了，数据库出错了 >_<")
                return

            result = await self.core._generate_and_send_calendar(
                event, user_id, user_name, self.db_path, adjusted_date)

            # 成就检查：累计/单日/连续
            new_achievements = await self._check_and_unlock_achievements(user_id)
            ach_texts = [ACHIEVEMENT_UNLOCK.format(icon=a['icon'], name=a['name'], desc=a['desc'])
                         for a in new_achievements]
            # LLM 概率对话
            llm_text = await self._maybe_llm_reply(user_id, adjusted_date)

            chain = []
            if result[2]:
                chain.append(Plain(result[0]))
            elif result[1]:
                chain.append(Plain(self._feed_reply(cake_count)))
                chain.append(Image(file=result[1]))
            else:
                chain.append(Plain(result[0] or self._feed_reply(cake_count)))
            for t in ach_texts:
                chain.append(Plain(t))
            if llm_text:
                chain.append(Plain(f"娅娅有话想对你说——\n{llm_text}"))
            yield event.chain_result(chain)

    @filter.regex(r'^[🍰蛋糕]补签\s+(\d{1,2})(?:\s+(\d+))?\s*$', description='🍰补签')
    async def handle_cake_retro(self, event: AstrMessageEvent):
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        text = event.get_message_str().strip()
        m = re.match(r'^[🍰蛋糕]补签\s+(\d{1,2})(?:\s+(\d+))?\s*$', text)
        if not m:
            yield event.plain_result("格式错误，例：🍰补签 5 或 🍰补签 5 3")
            return
        day = int(m.group(1))
        count = int(m.group(2)) if m.group(2) else 1
        today = date.today()
        year, month = today.year, today.month
        days_in_month = calendar.monthrange(year, month)[1]
        if day < 1 or day > days_in_month:
            yield event.plain_result(f"日期不合法，本月只有 {days_in_month} 天")
            return
        if day > today.day:
            yield event.plain_result("不能补签未来的日期")
            return

        adjusted_date = f"{year}-{month:02d}-{day:02d}"
        try:
            group_id = str(event.get_group_id() or '')
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "INSERT INTO checkin (user_id, group_id, checkin_date, cake_count) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id, group_id, checkin_date) DO UPDATE SET cake_count = cake_count + ?",
                    (user_id, group_id, adjusted_date, count, count))
                await conn.commit()
        except Exception as e:
            logger.error(f"补签失败: {e}")
            yield event.plain_result("补签失败了 >_<")
            return

        user_name = await self.core._get_user_name(event, user_id)
        new_achievements = await self._check_and_unlock_achievements(user_id)
        ach_texts = [ACHIEVEMENT_UNLOCK.format(icon=a['icon'], name=a['name'], desc=a['desc'])
                     for a in new_achievements]
        result = await self.core._generate_and_send_calendar(
            event, user_id, user_name, self.db_path)
        chain = []
        if result[0]:
            chain.append(Plain(result[0]))
        elif result[1]:
            chain.append(Image(file=result[1]))
        for t in ach_texts:
            chain.append(Plain(t))
        yield event.chain_result(chain)

    @filter.regex(r'^[🍰蛋糕]重置榜单(\s.*)?$', description='清空今天的喂蛋糕计数（可@他人）')
    async def handle_cake_reset(self, event: AstrMessageEvent):
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        if getattr(event, 'role', 'member') != 'admin':
            yield event.plain_result("要做一个诚实的好孩子哦，重置需要管理员权限～")
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
                yield event.plain_result(f"已重置{who}今天（{adjusted_date}）的喂蛋糕计数，共清除 {row[0]} 块。")
            else:
                yield event.plain_result("今天还没有喂蛋糕记录，无需重置。")
        except Exception as e:
            logger.error(f"重置失败: {e}")
            yield event.plain_result("重置失败，数据库出错了 >_<")

    @filter.regex(r'^[🍰蛋糕]日历$', description='查看娅娅本月日历')
    async def handle_cake_calendar(self, event: AstrMessageEvent):
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

    @filter.regex(r'^[🍰蛋糕](?:报告|分析)(?:\s+(\d{2}|\d{4}))?$', description='🍰报告/分析')
    async def handle_cake_analysis(self, event: AstrMessageEvent):
        await self._ensure_initialized()
        if not await self._check_group_and_blacklist(event):
            return
        user_id = str(event.get_sender_id())
        user_name = await self.core._get_user_name(event, user_id)
        text = event.get_message_str().strip()
        m = re.match(r'^[🍰蛋糕](?:报告|分析)\s*(\d{2}|\d{4})?$', text)
        param = m.group(1) if m and m.group(1) else None

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
                yield event.plain_result("月份格式不对，请输入 01-12")
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
            yield event.plain_result("还没有喂蛋糕记录，先给娅娅喂一块吧！发送 🍰")
            return

        try:
            image_path = await asyncio.to_thread(
                self.core._create_analysis_image,
                user_name, target_period, report, rate, "蛋糕")
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成娅娅投喂报告图片失败: {e}")
            yield event.plain_result(report)

    @filter.regex(r'^[🍰蛋糕]生涯$', description='娅娅生涯档案')
    async def handle_cake_career(self, event: AstrMessageEvent):
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
            yield event.plain_result("查询生涯数据失败 >_<")
            return

        if not rows:
            yield event.plain_result("还没有喂蛋糕记录，先给娅娅喂一块吧！发送 🍰")
            return

        stats = self._compute_career_stats(rows)
        try:
            image_path = await asyncio.to_thread(
                self.core._create_career_image,
                user_name, stats, "娅娅")
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成生涯图片失败: {e}")
            yield event.plain_result("生成生涯图片失败 >_<")

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
            rest_period_str = f"从 {gap_start} 开始，长达 {max_gap.days} 天没给娅娅喂蛋糕"
        else:
            rest_period_str = "每天都在坚持投喂，娅娅没有挨饿"

        if min_month_count == 0:
            sage_comment = "这个月娅娅饿肚子了！"
        elif min_month_count <= 2:
            sage_comment = "最少月份娅娅只有一点点甜"
        else:
            sage_comment = ""

        last_date = datetime.strptime(rows[-1][0], "%Y-%m-%d").date()
        status_day = (today - last_date).days
        if status_day == 0:
            status_comment = "今天已经喂过娅娅了，她超开心！"
        elif status_day <= 3:
            status_comment = f"已经 {status_day} 天没喂娅娅了，她在门口张望呢"
        elif status_day <= 7:
            status_comment = f"已经 {status_day} 天没喂娅娅了，她有点小委屈"
        elif status_day <= 30:
            status_comment = f"已经 {status_day} 天没喂娅娅了，她开始数着日子等了"
        else:
            status_comment = f"已经 {status_day} 天没喂娅娅了，她攒了好多话想对你说"

        if daily_avg > 1.5:
            summary_comment = "核动力投喂手"
        elif daily_avg > 0.8:
            summary_comment = "贴心蛋糕师"
        elif daily_avg > 0.3:
            summary_comment = "娅娅的好朋友"
        else:
            summary_comment = "甜蜜守护者"

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

    async def _format_ranking(self, event, raw_data):
        cache = {}
        result = []
        for idx, (uid, count) in enumerate(raw_data, 1):
            uid = str(uid)
            if uid not in cache:
                cache[uid] = await self.core._get_user_name(event, uid)
            result.append((idx, uid, cache[uid], count))
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

    async def _download_all_avatars(self, all_data_lists):
        all_uids = set()
        for data_list in all_data_lists:
            for _, uid, _, _ in data_list:
                all_uids.add(uid)
        for uid in all_uids:
            save_path = os.path.join(self.avatar_dir, f"{uid}.png")
            if not os.path.exists(save_path):
                await self._download_avatar(uid, save_path)

    async def _download_avatar(self, qq_id: str, save_path: str) -> bool:
        import urllib.request
        url = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            with open(save_path, 'wb') as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error(f"下载头像 {qq_id} 失败: {e}")
            return False

    @filter.regex(r'^(?:查看|查询)?[🍰蛋糕]榜(\s+\d+)?$|^[🍰蛋糕][日月]榜(\s+\d+)?$', description='🍰排行榜')
    async def handle_cake_ranking(self, event: AstrMessageEvent):
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
            yield event.plain_result("排行榜仅支持群聊使用")
            return

        members = await self.core._get_group_members(event, str(group_id))
        if not members:
            yield event.plain_result("无法获取群成员信息，请稍后再试")
            return
        group_user_ids = {str(m.get('user_id')) for m in members}

        today = date.today()
        year, month_val = today.year, today.month
        adjusted_date_str = self._get_adjusted_date()
        month_str = f"{year}-{month_val:02d}"

        today_condition = f"checkin_date = '{adjusted_date_str}'"
        month_condition = f"strftime('%Y-%m', checkin_date) = '{month_str}'"
        today_help_condition = f"date = '{adjusted_date_str}'"
        month_help_condition = f"strftime('%Y-%m', date) = '{month_str}'"

        raw_today_self = await self.core._get_period_ranking_data(
            self.db_path, today_condition, group_user_ids, str(group_id))
        raw_today_received = await self.core._get_received_ranking_data(
            self.db_path, today_help_condition, group_user_ids, str(group_id))
        raw_today_helped = await self.core._get_help_ranking_data(
            self.db_path, today_help_condition, group_user_ids, str(group_id))

        raw_month_self = await self.core._get_period_ranking_data(
            self.db_path, month_condition, group_user_ids, str(group_id))
        raw_month_received = await self.core._get_received_ranking_data(
            self.db_path, month_help_condition, group_user_ids, str(group_id))
        raw_month_helped = await self.core._get_help_ranking_data(
            self.db_path, month_help_condition, group_user_ids, str(group_id))

        today_self = await self._format_ranking(event, raw_today_self)
        today_received = await self._format_ranking(event, raw_today_received)
        today_helped = await self._format_ranking(event, raw_today_helped)
        month_self = await self._format_ranking(event, raw_month_self)
        month_received = await self._format_ranking(event, raw_month_received)
        month_helped = await self._format_ranking(event, raw_month_helped)

        page_size = max(int(self.ranking_display_count or 10), 1)
        paginate = lambda d, p: d[(p-1)*page_size:p*page_size]

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

        max_len = max(
            len(raw_today_self), len(raw_today_received), len(raw_today_helped),
            len(raw_month_self), len(raw_month_received), len(raw_month_helped))
        total_pages = max(math.ceil(max_len / page_size), 1)
        if page > total_pages:
            page = total_pages

        try:
            image_path = await asyncio.to_thread(
                self.core._create_three_column_ranking_image,
                today_self_page, today_received_page, today_helped_page,
                month_self_page, month_received_page, month_helped_page,
                year, month_val, page, total_pages, "🍰", self.avatar_dir, ach_map)
            yield event.image_result(image_path)
        except Exception as e:
            logger.error(f"生成排行榜图片失败: {e}")
            yield event.plain_result("生成排行榜失败 >_<")
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

    @filter.regex(r'^[🍰蛋糕]帮助$', description='🍰帮助')
    async def handle_cake_help(self, event: AstrMessageEvent):
        help_text = """🍰 娅娅喂蛋糕使用帮助 🍰

[🍰蛋糕] + 数量 → 给娅娅喂蛋糕（例：🍰🍰🍰）
[🍰蛋糕] + @某人 → 替别人喂蛋糕
[🍰蛋糕]日历 → 查看娅娅本月日历
[🍰蛋糕]报告/分析 → 本月投喂报告
[🍰蛋糕]报告/分析 MM → 指定月份报告
[🍰蛋糕]报告/分析 YYYY → 指定年份报告
[🍰蛋糕]生涯 → 投喂生涯档案
[🍰蛋糕]补签 DD [数量] → 补签某天
[🍰蛋糕]榜 [页码] → 查看排行榜（含成就徽章）
[🍰蛋糕]成就 → 查看成就墙
[🍰蛋糕]重置榜单 → 管理员重置今日计数
[🍰蛋糕]帮助 → 本帮助"""
        yield event.plain_result(help_text)
