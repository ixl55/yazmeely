"""
بوت تيليجرام لتحميل الفيديو والصوت من YouTube و TikTok و Instagram و X و Facebook.

كل الإعدادات تُقرأ من متغيرات البيئة (أو من ملف .env) — راجع .env.example و README.md.
"""

import asyncio
import functools
import html
import json
import logging
import math
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from threading import Thread

from dotenv import load_dotenv
from flask import Flask
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

load_dotenv()

# ================================
# الإعدادات
# ================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger("yazmeely")
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.WARNING)


def _env_list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, '').split(',') if x.strip()]


BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_IDS = {int(x) for x in _env_list('ADMIN_IDS')}
REQUIRED_CHANNEL = os.getenv('REQUIRED_CHANNEL', '').strip()  # مثال: @mychannel — اتركه فارغاً لتعطيل الاشتراك الإجباري

DATA_DIR = os.getenv('DATA_DIR', 'data')
DOWNLOAD_DIR = os.path.join(DATA_DIR, 'downloads')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
COOKIES_FILE = os.path.join(DATA_DIR, 'cookies.txt')
COOKIES_CONFIG_FILE = os.path.join(DATA_DIR, 'cookies_config.json')

MAX_DURATION_SECONDS = int(os.getenv('MAX_DURATION_MINUTES', '90')) * 60
# حد Bot API الرسمي للرفع هو 50MB. مع Local Bot API Server يمكن رفعه حتى 2000MB.
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '50'))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '2'))
VIDEO_MAX_HEIGHT = int(os.getenv('VIDEO_MAX_HEIGHT', '720'))

# حلول حظر يوتيوب للسيرفرات (راجع README)
PROXY = os.getenv('PROXY', '').strip()                       # http://user:pass@host:port أو socks5://host:port
POT_PROVIDER_URL = os.getenv('POT_PROVIDER_URL', '').strip()  # http://bgutil-provider:4416
YT_PLAYER_CLIENTS = _env_list('YT_PLAYER_CLIENTS')          # مثال: default,tv,web_safari

TELEGRAM_API_URL = os.getenv('TELEGRAM_API_URL', '').strip().rstrip('/')  # Local Bot API Server (اختياري)
PORT = int(os.getenv('PORT', '8080'))
WEB_SERVER = os.getenv('WEB_SERVER', '1') != '0'

URL_RE = re.compile(r'https?://\S+')
SUPPORTED_SITES = (
    'youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com',
    'twitter.com', 'x.com', 'facebook.com', 'fb.watch',
)

FFMPEG_PATH = shutil.which('ffmpeg')
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ================================
# خادم الويب (للاستضافات التي تتطلب منفذ HTTP مفتوح)
# ================================

flask_app = Flask(__name__)


@flask_app.route('/')
def home():
    return "✅ البوت يعمل"


def run_flask():
    flask_app.run(host='0.0.0.0', port=PORT)


# ================================
# التخزين (المستخدمون والإعدادات)
# ================================

def _atomic_write_json(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        logger.error(f"خطأ في قراءة {path}: {e}")
        return default


class UserStore:
    """تخزين المستخدمين في الذاكرة مع حفظ آمن على القرص."""

    def __init__(self, path: str):
        self.path = path
        self.users: dict[str, dict] = {}
        self.lock = asyncio.Lock()

    def load(self) -> None:
        data = _read_json(self.path, {})
        for uid, value in list(data.items()):
            # تحويل الصيغة القديمة {id: username}
            if isinstance(value, str):
                data[uid] = {"username": value, "banned": False, "date_joined": None}
        self.users = data

    async def save(self) -> None:
        snapshot = json.loads(json.dumps(self.users))
        await asyncio.to_thread(_atomic_write_json, self.path, snapshot)

    async def touch(self, user) -> dict:
        """تسجيل المستخدم أو تحديث اسمه، وإرجاع بياناته."""
        uid = str(user.id)
        username = user.username or user.full_name or "بدون اسم"
        async with self.lock:
            record = self.users.get(uid)
            if record is None:
                record = {
                    "username": username,
                    "banned": False,
                    "date_joined": datetime.now(timezone.utc).isoformat(timespec='seconds'),
                }
                self.users[uid] = record
                logger.info(f"✅ مستخدم جديد: {uid} - {username}")
                await self.save()
            elif record.get('username') != username:
                record['username'] = username
                await self.save()
            return record

    def is_banned(self, user_id: int) -> bool:
        return self.users.get(str(user_id), {}).get('banned', False)

    async def set_banned(self, uid: str, banned: bool) -> bool:
        async with self.lock:
            if uid not in self.users:
                return False
            self.users[uid]['banned'] = banned
            await self.save()
            return True


store = UserStore(USERS_FILE)


def load_cookies_config() -> dict:
    return _read_json(COOKIES_CONFIG_FILE, {"enabled": False})


def save_cookies_config(config: dict) -> None:
    _atomic_write_json(COOKIES_CONFIG_FILE, config)


def get_active_cookies_path() -> str | None:
    if not load_cookies_config().get("enabled", False):
        return None
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        return COOKIES_FILE
    logger.warning("⚠️ الكوكيز مفعلة لكن الملف غير موجود أو فارغ")
    return None


# ================================
# yt-dlp
# ================================

def base_ydl_opts() -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'retries': 3,
        'fragment_retries': 3,
        'socket_timeout': 30,
        'concurrent_fragment_downloads': 4,
        # تمهّل بين الطلبات لتقليل احتمال الحظر
        'sleep_interval_requests': 1,
    }
    if FFMPEG_PATH:
        opts['ffmpeg_location'] = os.path.dirname(FFMPEG_PATH)
    if PROXY:
        opts['proxy'] = PROXY

    youtube_args = {}
    if YT_PLAYER_CLIENTS:
        youtube_args['player_client'] = YT_PLAYER_CLIENTS
    extractor_args = {}
    if youtube_args:
        extractor_args['youtube'] = youtube_args
    if POT_PROVIDER_URL:
        # يتطلب تثبيت الإضافة bgutil-ytdlp-pot-provider (موجودة في requirements.txt)
        extractor_args['youtubepot-bgutilhttp'] = {'base_url': [POT_PROVIDER_URL]}
    if extractor_args:
        opts['extractor_args'] = extractor_args
    return opts


def validate_cookies_file(file_path: str) -> tuple[bool, str]:
    """فحص صيغة ملف الكوكيز (Netscape) ثم تجربته فعلياً على يوتيوب."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [ln for ln in f if ln.strip() and not ln.startswith('#')]
    except OSError:
        return False, "الملف غير موجود"

    rows = [ln.split('\t') for ln in lines]
    if not rows or any(len(r) < 7 for r in rows[:20]):
        return False, "الملف ليس بصيغة Netscape (cookies.txt)"
    if not any('youtube.com' in r[0] for r in rows):
        return False, "الملف لا يحتوي كوكيز youtube.com"

    opts = base_ydl_opts()
    opts.update({'cookiefile': file_path, 'skip_download': True})
    try:
        with YoutubeDL(opts) as ydl:
            ydl.extract_info('https://www.youtube.com/watch?v=jNQXAC9IVRw', download=False, process=False)
        return True, "✅ الكوكيز صالحة"
    except Exception as e:
        msg = str(e)
        if 'Sign in to confirm' in msg:
            return False, "يوتيوب ما زال يطلب التحقق (الكوكيز منتهية أو الـ IP محظور)"
        return False, f"فشل الاختبار: {msg[:200]}"


class DownloadFailed(Exception):
    pass


def friendly_error(err: str) -> str:
    if 'Sign in to confirm' in err or 'not a bot' in err:
        return ("🤖 يوتيوب حظر السيرفر مؤقتاً (يطلب التحقق من أنك لست روبوت).\n"
                "تم إبلاغ الإدارة، حاول لاحقاً.")
    if 'Private video' in err or 'login required' in err.lower() or 'Sign in' in err:
        return "🔒 الفيديو خاص أو يتطلب تسجيل الدخول."
    if 'Video unavailable' in err or 'is not available' in err:
        return "❌ الفيديو غير متاح (محذوف أو محجوب في منطقة السيرفر)."
    if 'File is larger than max-filesize' in err or 'too large' in err:
        return f"📦 حجم الملف أكبر من {MAX_FILE_SIZE_MB}MB."
    if 'duration' in err.lower() and 'long' in err.lower():
        return f"⏱️ الفيديو أطول من {MAX_DURATION_SECONDS // 60} دقيقة."
    if 'Requested format' in err:
        return "❌ لا توجد صيغة مناسبة لهذا الفيديو."
    if 'Unsupported URL' in err:
        return "⚠️ الرابط غير مدعوم."
    return "❌ تعذر التحميل. تأكد من الرابط وحاول مرة أخرى."


def download_media(url: str, audio_only: bool, out_dir: str) -> tuple[str, dict]:
    """تحميل الرابط داخل out_dir وإرجاع (مسار الملف، معلومات الفيديو)."""
    opts = base_ydl_opts()
    opts.update({
        'outtmpl': os.path.join(out_dir, '%(title).60B [%(id)s].%(ext)s'),
        'max_filesize': MAX_FILE_SIZE,
    })
    h = VIDEO_MAX_HEIGHT
    if audio_only:
        opts['format'] = 'ba[ext=m4a]/ba/b'
        if FFMPEG_PATH:
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
    elif FFMPEG_PATH:
        opts['format'] = (
            f'bv*[height<={h}][ext=mp4]+ba[ext=m4a]/'
            f'bv*[height<={h}]+ba/'
            f'b[height<={h}]/bv*+ba/b'
        )
        opts['merge_output_format'] = 'mp4'
    else:
        # بدون ffmpeg لا يمكن الدمج، نختار صيغة جاهزة فيها صوت وصورة
        opts['format'] = f'b[height<={h}][ext=mp4]/b[height<={h}]/b'

    cookies = get_active_cookies_path()
    attempts = [cookies, None] if cookies else [None]
    last_error = ''
    for cookiefile in attempts:
        run_opts = dict(opts)
        if cookiefile:
            run_opts['cookiefile'] = cookiefile
        try:
            with YoutubeDL(run_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info.get('_type') == 'playlist' or 'entries' in info:
                    raise DownloadFailed("Unsupported URL: playlists are not supported")
                if (info.get('duration') or 0) > MAX_DURATION_SECONDS:
                    raise DownloadFailed("video duration too long")
                ydl.process_ie_result(info, download=True)
            files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
                     if not f.endswith(('.part', '.ytdl', '.tmp'))]
            if not files:
                raise DownloadFailed("File is larger than max-filesize")
            return max(files, key=os.path.getsize), info
        except (DownloadError, DownloadFailed) as e:
            last_error = str(e)
            logger.warning(f"⚠️ فشل التحميل ({'مع' if cookiefile else 'بدون'} كوكيز): {last_error[:200]}")
            # لا فائدة من إعادة المحاولة إذا كانت المشكلة في الرابط نفسه
            if any(k in last_error for k in ('Unsupported URL', 'duration too long', 'max-filesize')):
                break
            for f in os.listdir(out_dir):
                os.remove(os.path.join(out_dir, f))
    raise DownloadFailed(last_error)


# ================================
# أدوات مساعدة
# ================================

async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not REQUIRED_CHANNEL or is_admin(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator", "owner")
    except Exception as e:
        # البوت يجب أن يكون مشرفاً في القناة. لا نعطّل البوت للجميع بسبب خطأ هنا.
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return True


async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """تسجيل المستخدم والتحقق من الحظر والاشتراك. ترجع False إذا مُنع."""
    user = update.effective_user
    await store.touch(user)
    reply = update.effective_message.reply_text
    if store.is_banned(user.id):
        await reply("🚫 عذراً، لقد تم حظرك من استخدام هذا البوت.")
        return False
    if not await is_user_subscribed(context, user.id):
        await reply(f"🔒 لا يمكنك استخدام البوت حتى تشترك في القناة أولاً:\n{REQUIRED_CHANNEL}")
        return False
    return True


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except Exception:
            pass


def extract_url(text: str) -> str | None:
    match = URL_RE.search(text or '')
    if not match:
        return None
    url = match.group(0)
    host = re.sub(r'^https?://', '', url).split('/')[0].lower()
    if any(host == d or host.endswith('.' + d) for d in SUPPORTED_SITES):
        return url
    return None


# ================================
# أوامر المستخدم
# ================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return
    msg = (
        "👋 أهلاً بك في بوت التحميل!\n\n"
        "أرسل رابط فيديو من YouTube أو TikTok أو Instagram أو X أو Facebook وسأقوم بتحميله لك.\n"
        "اكتب /help لعرض التعليمات."
    )
    if is_admin(update.effective_user.id):
        cookies_on = load_cookies_config().get("enabled", False)
        msg += (
            "\n\n🛠️ <b>معلومات المسؤول:</b>\n"
            f"🍪 الكوكيز: {'✅ مفعل' if cookies_on else '❌ غير مفعل'}\n"
            f"🔊 FFmpeg: {'✅ متاح' if FFMPEG_PATH else '❌ غير متاح'}\n"
            f"🌐 بروكسي: {'✅' if PROXY else '❌'} | PO Token: {'✅' if POT_PROVIDER_URL else '❌'}\n"
            "اكتب /admin لفتح لوحة التحكم."
        )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 <b>تعليمات استخدام البوت:</b>\n"
        "1. أرسل رابط فيديو من YouTube أو TikTok أو Instagram أو X أو Facebook.\n"
        "2. اختر تحميل الفيديو أو الصوت فقط.\n"
        "3. انتظر حتى يكتمل التحميل.\n\n"
        "⚠️ البوت لا يدعم:\n"
        "• الروابط الخاصة أو المحمية\n"
        f"• الفيديوهات الأطول من {MAX_DURATION_SECONDS // 60} دقيقة\n"
        f"• الملفات الأكبر من {MAX_FILE_SIZE_MB}MB",
        parse_mode=ParseMode.HTML,
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.pop('state', None):
        await update.message.reply_text("❌ تم الإلغاء.")
    else:
        await update.message.reply_text("لا توجد عملية لإلغائها.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ''

    if is_admin(user_id):
        if context.user_data.get('state') == 'awaiting_broadcast':
            context.user_data.pop('state', None)
            context.application.create_task(run_broadcast(update, context), update=update)
            return
        if await handle_admin_keyboard(update, context, text):
            return

    if not await check_access(update, context):
        return

    url = extract_url(text)
    if not url:
        await update.message.reply_text(
            "⚠️ أرسل رابطاً صحيحاً من المواقع المدعومة:\n"
            "YouTube, TikTok, Instagram, X (Twitter), Facebook."
        )
        return

    # نحفظ الرابط بمعرّف قصير حتى تعمل الأزرار حتى لو أرسل المستخدم عدة روابط
    links: dict = context.user_data.setdefault('links', {})
    if len(links) > 20:
        links.pop(next(iter(links)))
    key = uuid.uuid4().hex[:10]
    links[key] = url

    buttons = [[InlineKeyboardButton("🎞️ فيديو", callback_data=f"dl:v:{key}")]]
    buttons[0].insert(0, InlineKeyboardButton("🎵 صوت فقط", callback_data=f"dl:a:{key}"))
    await update.message.reply_text(
        "📥 هل تريد تحميل الصوت فقط أم الفيديو؟",
        reply_markup=InlineKeyboardMarkup(buttons),
        do_quote=True,
    )


async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, kind, key = query.data.split(':', 2)

    if store.is_banned(query.from_user.id):
        await query.answer("🚫 أنت محظور.", show_alert=True)
        return

    url = context.user_data.get('links', {}).pop(key, None)
    if not url:
        await query.answer("❌ انتهت صلاحية الرابط، أرسله مرة أخرى.", show_alert=True)
        return
    await query.answer()

    audio_only = kind == 'a'
    if download_semaphore.locked():
        await query.edit_message_text("⏳ في قائمة الانتظار، يوجد تحميلات أخرى جارية...")

    out_dir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
    try:
        async with download_semaphore:
            await query.edit_message_text("🔄 جارٍ التحميل، يرجى الانتظار...")
            filepath, info = await asyncio.to_thread(download_media, url, audio_only, out_dir)

        if os.path.getsize(filepath) > MAX_FILE_SIZE:
            await query.edit_message_text(f"📦 حجم الملف أكبر من {MAX_FILE_SIZE_MB}MB ولا يمكن إرساله.")
            return

        await query.edit_message_text("📤 جارٍ الرفع إلى تيليجرام...")
        title = (info.get('title') or 'media')[:64]
        chat_id = query.message.chat_id
        await context.bot.send_chat_action(
            chat_id, ChatAction.UPLOAD_VOICE if audio_only else ChatAction.UPLOAD_VIDEO)

        with open(filepath, 'rb') as f:
            if audio_only:
                await context.bot.send_audio(
                    chat_id, audio=f, title=title,
                    performer=info.get('uploader') or 'yazmeely',
                    duration=int(info['duration']) if info.get('duration') else None,
                    read_timeout=600, write_timeout=600,
                )
            else:
                await context.bot.send_video(
                    chat_id, video=f, supports_streaming=True,
                    caption=f"🎬 {title}\nUploaded by yazmeely",
                    width=info.get('width'), height=info.get('height'),
                    duration=int(info['duration']) if info.get('duration') else None,
                    read_timeout=600, write_timeout=600,
                )
        await query.delete_message()
        logger.info(f"✅ تم إرسال الملف للمستخدم {query.from_user.id}")

    except DownloadFailed as e:
        err = str(e)
        logger.error(f"فشل التحميل للمستخدم {query.from_user.id}: {err[:300]}")
        await query.edit_message_text(friendly_error(err))
        if 'Sign in to confirm' in err:
            await notify_admins(
                context,
                "⚠️ يوتيوب يحظر السيرفر حالياً (Sign in to confirm you're not a bot).\n"
                "الحلول: ارفع كوكيز جديدة عبر /cookies_upload، أو فعّل PROXY أو POT_PROVIDER_URL.",
            )
    except Exception as e:
        logger.exception(f"خطأ غير متوقع للمستخدم {query.from_user.id}: {e}")
        try:
            await query.edit_message_text("❌ حدث خطأ أثناء إرسال الملف، حاول مرة أخرى.")
        except BadRequest:
            pass
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


# ================================
# لوحة الإدارة
# ================================

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ['📊 إحصائيات البوت', '👥 قائمة الأعضاء'],
        ['🚫 المحظورين', '📢 إذاعة رسالة'],
        ['🍪 الكوكيز', '🔙 خروج'],
    ],
    resize_keyboard=True,
)
USERS_PER_PAGE = 10


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return
    await update.message.reply_text(
        "🛠 <b>لوحة تحكم المسؤول</b>", reply_markup=ADMIN_KEYBOARD, parse_mode=ParseMode.HTML)


def stats_text() -> str:
    total = len(store.users)
    banned = sum(1 for u in store.users.values() if u.get('banned'))
    return (
        "📊 <b>إحصائيات النظام:</b>\n\n"
        f"👤 إجمالي المستخدمين: {total}\n"
        f"✅ النشطين: {total - banned}\n"
        f"🚫 المحظورين: {banned}\n"
        f"🔊 FFmpeg: {'✅' if FFMPEG_PATH else '❌'}\n"
        f"🍪 الكوكيز: {'✅' if get_active_cookies_path() else '❌'}\n"
        f"🌐 بروكسي: {'✅' if PROXY else '❌'} | PO Token: {'✅' if POT_PROVIDER_URL else '❌'}"
    )


def users_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    users = list(store.users.items())
    pages = max(1, math.ceil(len(users) / USERS_PER_PAGE))
    page = min(max(1, page), pages)
    start_i = (page - 1) * USERS_PER_PAGE
    buttons = []
    for uid, u in users[start_i:start_i + USERS_PER_PAGE]:
        status = "🚫" if u.get('banned') else "✅"
        buttons.append([InlineKeyboardButton(
            f"{status} {uid} ({u.get('username', 'N/A')})", callback_data=f"adm:user:{uid}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"adm:users:{page - 1}"))
    if page < pages:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"adm:users:{page + 1}"))
    if nav:
        buttons.append(nav)
    text = f"👥 <b>الأعضاء ({len(users)}) — صفحة {page} من {pages}</b>\nاختر مستخدماً لإدارته:"
    return text, InlineKeyboardMarkup(buttons)


def user_view(uid: str) -> tuple[str, InlineKeyboardMarkup] | None:
    u = store.users.get(uid)
    if not u:
        return None
    banned = u.get('banned', False)
    text = (
        "👤 <b>إدارة المستخدم:</b>\n"
        f"• ID: <code>{uid}</code>\n"
        f"• الاسم: {html.escape(str(u.get('username')))}\n"
        f"• تاريخ الانضمام: {u.get('date_joined') or 'غير معروف'}\n"
        f"• الحالة: {'محظور 🚫' if banned else 'نشط ✅'}"
    )
    buttons = [
        [InlineKeyboardButton("فك الحظر ✅" if banned else "حظر 🚫",
                              callback_data=f"adm:{'unban' if banned else 'ban'}:{uid}")],
        [InlineKeyboardButton("⬅️ عودة للقائمة", callback_data="adm:users:1")],
    ]
    return text, InlineKeyboardMarkup(buttons)


def banned_view() -> tuple[str, InlineKeyboardMarkup | None]:
    banned = [uid for uid, u in store.users.items() if u.get('banned')]
    if not banned:
        return "لا يوجد مستخدمين محظورين.", None
    text = "🚫 <b>قائمة المحظورين:</b>\n\n" + "\n".join(f"• <code>{uid}</code>" for uid in banned[:50])
    buttons = [[InlineKeyboardButton(f"فك حظر {uid}", callback_data=f"adm:unban:{uid}")] for uid in banned[:50]]
    return text, InlineKeyboardMarkup(buttons)


async def handle_admin_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    reply = update.message.reply_text
    if text == '📊 إحصائيات البوت':
        await reply(stats_text(), parse_mode=ParseMode.HTML)
    elif text == '👥 قائمة الأعضاء':
        if not store.users:
            await reply("لا يوجد أعضاء مسجلين حالياً.")
        else:
            msg, markup = users_page(1)
            await reply(msg, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif text == '🚫 المحظورين':
        msg, markup = banned_view()
        await reply(msg, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif text == '📢 إذاعة رسالة':
        context.user_data['state'] = 'awaiting_broadcast'
        await reply("📢 أرسل الآن الرسالة المراد إذاعتها (نص أو صورة أو فيديو...)، أو /cancel للإلغاء.")
    elif text == '🍪 الكوكيز':
        await cookies_command(update, context)
    elif text == '🔙 خروج':
        await reply("🔙 تم إخفاء لوحة التحكم.", reply_markup=ReplyKeyboardRemove())
    else:
        return False
    return True


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("🚫 غير مصرح لك.", show_alert=True)
        return

    _, action, arg = query.data.split(':', 2)
    if action == 'users':
        msg, markup = users_page(int(arg))
    elif action in ('ban', 'unban'):
        if not await store.set_banned(arg, action == 'ban'):
            await query.answer("❌ مستخدم غير موجود.", show_alert=True)
            return
        msg, markup = user_view(arg)
    elif action == 'user':
        view = user_view(arg)
        if not view:
            await query.answer("❌ مستخدم غير موجود.", show_alert=True)
            return
        msg, markup = view
    else:
        await query.answer()
        return

    await query.answer({'ban': "✅ تم الحظر", 'unban': "✅ تم فك الحظر"}.get(action))
    try:
        await query.edit_message_text(msg, reply_markup=markup, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        if 'not modified' not in str(e):
            raise


async def run_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    source = update.message
    await source.reply_text(f"⏳ جارٍ الإذاعة إلى {len(store.users)} مستخدم...")
    success = fail = 0
    for uid in list(store.users):
        try:
            await context.bot.copy_message(int(uid), source.chat_id, source.message_id)
            success += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await context.bot.copy_message(int(uid), source.chat_id, source.message_id)
                success += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest):
            fail += 1
        except Exception as e:
            logger.warning(f"فشل الإرسال إلى {uid}: {e}")
            fail += 1
        await asyncio.sleep(0.05)  # حد تيليجرام ~30 رسالة/ثانية
    await source.reply_text(f"✅ اكتملت الإذاعة!\nنجح: {success}\nفشل: {fail}")


async def handle_admin_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إذاعة الوسائط (صورة/فيديو...) عندما يكون المسؤول في وضع الإذاعة."""
    if is_admin(update.effective_user.id) and context.user_data.get('state') == 'awaiting_broadcast':
        context.user_data.pop('state', None)
        context.application.create_task(run_broadcast(update, context), update=update)


# ================================
# إدارة الكوكيز
# ================================

def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.effective_message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
            return
        return await func(update, context)
    return wrapper


@admin_only
async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    enabled = load_cookies_config().get("enabled", False)
    exists = os.path.exists(COOKIES_FILE)
    await update.effective_message.reply_text(
        "🍪 <b>إعدادات الكوكيز:</b>\n\n"
        f"• الحالة: {'✅ مفعل' if enabled else '❌ غير مفعل'}\n"
        f"• الملف: {'موجود' if exists else 'غير موجود'}\n\n"
        "<b>الأوامر:</b>\n"
        "/cookies_on - تفعيل الكوكيز\n"
        "/cookies_off - إيقاف الكوكيز\n"
        "/cookies_upload - رفع ملف كوكيز جديد\n"
        "/cookies_status - فحص صلاحية الكوكيز الآن",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def cookies_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(COOKIES_FILE):
        await update.message.reply_text("❌ لا يوجد ملف كوكيز. ارفعه أولاً عبر /cookies_upload")
        return
    save_cookies_config({"enabled": True})
    await update.message.reply_text("✅ تم تفعيل الكوكيز")


@admin_only
async def cookies_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_cookies_config({"enabled": False})
    await update.message.reply_text("✅ تم إيقاف الكوكيز")


@admin_only
async def cookies_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'awaiting_cookies_file'
    await update.message.reply_text(
        "📤 <b>رفع ملف الكوكيز:</b>\n\n"
        "1. افتح نافذة تصفح خفي (Incognito) وسجّل الدخول بحساب يوتيوب <b>ثانوي</b> (ليس حسابك الأساسي).\n"
        "2. افتح youtube.com ثم صدّر الكوكيز بإضافة <i>Get cookies.txt LOCALLY</i>.\n"
        "3. أغلق النافذة فوراً بدون تسجيل خروج (حتى لا تتغير الكوكيز).\n"
        "4. أرسل ملف cookies.txt هنا.\n\n"
        "⏳ بانتظار الملف... أو /cancel للإلغاء.",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(COOKIES_FILE):
        await update.message.reply_text("❌ لا يوجد ملف كوكيز حالياً")
        return
    msg = await update.message.reply_text("🔍 جارٍ فحص الكوكيز...")
    ok, result = await asyncio.to_thread(validate_cookies_file, COOKIES_FILE)
    enabled = load_cookies_config().get("enabled", False)
    await msg.edit_text(
        f"📊 حالة الكوكيز:\n• التفعيل: {'✅' if enabled else '❌'}\n"
        f"• الحجم: {os.path.getsize(COOKIES_FILE)} بايت\n• الفحص: {result}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    state = context.user_data.get('state')
    if state == 'awaiting_broadcast':
        await handle_admin_media(update, context)
        return
    if state != 'awaiting_cookies_file':
        return

    document = update.message.document
    if not (document.file_name or '').endswith('.txt') and document.mime_type != 'text/plain':
        await update.message.reply_text("❌ يرجى رفع ملف نصي (txt) فقط")
        return
    if document.file_size and document.file_size > 1024 * 1024:
        await update.message.reply_text("❌ الملف كبير جداً")
        return

    context.user_data.pop('state', None)
    temp_file = os.path.join(DATA_DIR, f"cookies_upload_{update.effective_user.id}.txt")
    msg = await update.message.reply_text("🔍 جارٍ فحص الملف...")
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(temp_file)
        ok, result = await asyncio.to_thread(validate_cookies_file, temp_file)
        if ok:
            os.replace(temp_file, COOKIES_FILE)
            os.chmod(COOKIES_FILE, 0o600)
            save_cookies_config({"enabled": True})
            await msg.edit_text(f"✅ تم حفظ الكوكيز وتفعيلها.\n{result}")
        else:
            await msg.edit_text(f"❌ ملف الكوكيز غير صالح:\n{result}")
    except Exception as e:
        logger.exception(f"خطأ في معالجة ملف الكوكيز: {e}")
        await msg.edit_text("❌ حدث خطأ أثناء معالجة الملف")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


# ================================
# التشغيل
# ================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("حدث خطأ:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.")
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ متغير البيئة BOT_TOKEN غير موجود. راجع ملف .env.example")
    if not ADMIN_IDS:
        logger.warning("⚠️ ADMIN_IDS فارغ — لن يتمكن أحد من استخدام لوحة الإدارة")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    # حذف بقايا تحميلات سابقة لم تكتمل
    for name in os.listdir(DOWNLOAD_DIR):
        shutil.rmtree(os.path.join(DOWNLOAD_DIR, name), ignore_errors=True)
    store.load()

    if WEB_SERVER:
        Thread(target=run_flask, daemon=True).start()

    builder = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True)
    if TELEGRAM_API_URL:
        builder = builder.base_url(f"{TELEGRAM_API_URL}/bot").base_file_url(f"{TELEGRAM_API_URL}/file/bot")
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler(["admin", "dashboard"], admin_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("cookies_on", cookies_on))
    app.add_handler(CommandHandler("cookies_off", cookies_off))
    app.add_handler(CommandHandler("cookies_upload", cookies_upload))
    app.add_handler(CommandHandler("cookies_status", cookies_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.ANIMATION) & ~filters.COMMAND,
        handle_admin_media))
    app.add_handler(CallbackQueryHandler(download_callback, pattern=r'^dl:'))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r'^adm:'))
    app.add_error_handler(error_handler)

    logger.info("=" * 50)
    logger.info("✅ البوت يعمل الآن...")
    logger.info(f"🔊 FFmpeg: {'✅' if FFMPEG_PATH else '❌'}")
    logger.info(f"🍪 الكوكيز: {'✅' if get_active_cookies_path() else '❌'}")
    logger.info(f"🌐 بروكسي: {'✅' if PROXY else '❌'} | PO Token: {'✅' if POT_PROVIDER_URL else '❌'}")
    if not shutil.which('deno') and not shutil.which('node'):
        logger.warning("⚠️ لم يتم العثور على deno/node — يوتيوب يحتاج JS runtime لفك التشفير. راجع README")
    logger.info("=" * 50)

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
