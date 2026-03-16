import os
import json
import logging
import subprocess
import sys
import asyncio
import tempfile
import shutil
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
from flask import Flask
from threading import Thread

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# إعداد Flask
flask_app = Flask('')
@flask_app.route('/')
def home():
    return "✅ البوت يعمل"
def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)
Thread(target=run_flask, daemon=True).start()

# إعدادات البوت
BOT_TOKEN = '7678984064:AAEjgukqYQVYyTWS54xEg8wL_rIl_0CAKBw'
ADMIN_IDS = [1481056671]
REQUIRED_CHANNEL = "@ctf5bro"
COOKIES_FILE = 'cookies.txt'

DOWNLOAD_DIR = 'downloads'
USERS_FILE = 'users.json'
COOKIES_CONFIG_FILE = 'cookies_config.json'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DURATION_SECONDS = 400 * 60
MAX_FILE_SIZE = 75 * 1024 * 1024

SUPPORTED_SITES = [
    "youtube.com", "youtu.be", "tiktok.com", "instagram.com",
    "twitter.com", "facebook.com", "fb.watch"
]

# البحث عن ffmpeg
def find_ffmpeg():
    path = shutil.which('ffmpeg')
    if path:
        logger.info(f"✅ تم العثور على ffmpeg في: {path}")
        return path
        
    possible_paths = ['ffmpeg', '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']
    for path in possible_paths:
        try:
            result = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info(f"✅ تم العثور على ffmpeg في: {path}")
                return path
        except:
            continue
    logger.error("❌ لم يتم العثور على ffmpeg")
    return None

FFMPEG_PATH = find_ffmpeg()
if FFMPEG_PATH:
    os.environ['FFMPEG_BINARY'] = FFMPEG_PATH

# ================================
# نظام إدارة الكوكيز المحسن
# ================================

def load_cookies_config():
    """تحميل إعدادات الكوكيز"""
    default_config = {
        "cookies_file": COOKIES_FILE,
        "enabled": False,
        "method": "manual"
    }
    try:
        if os.path.exists(COOKIES_CONFIG_FILE):
            with open(COOKIES_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"خطأ في تحميل إعدادات الكوكيز: {e}")
    return default_config

def save_cookies_config(config):
    """حفظ إعدادات الكوكيز"""
    try:
        with open(COOKIES_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"خطأ في حفظ إعدادات الكوكيز: {e}")

def get_active_cookies_path():
    """الحصول على مسار الكوكيز إذا كانت مفعلة"""
    config = load_cookies_config()
    
    if not config.get("enabled", False):
        return None
    
    cookies_path = config.get("cookies_file", COOKIES_FILE)
    
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
        logger.info(f"✅ استخدام ملف الكوكيز: {cookies_path}")
        return cookies_path
    else:
        logger.warning(f"⚠️ ملف الكوكيز غير صالح: {cookies_path}")
        return None

def validate_cookies_file(file_path):
    """التحقق من صحة ملف الكوكيز بربطه بـ YouTube"""
    try:
        if not os.path.exists(file_path):
            return False, "الملف غير موجود"
        
        if os.path.getsize(file_path) < 100:
            return False, "الملف صغير جداً"
        
        # اختبار بسيط لاستخراج المعلومات فقط لتجنب أخطاء الفورمات
        ydl_opts = {
            'cookiefile': file_path,
            'quiet': True,
            'skip_download': True,
            'extract_flat': True,
            'format': 'best' # استخدام أبسط فورمات للاختبار
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            # استخدام فيديو مشهور ومستقر للاختبار
            ydl.extract_info('https://www.youtube.com/watch?v=BaW_jenozKc', download=False)
        
        return True, "✅ الكوكيز صالحة"
        
    except Exception as e:
        error_msg = str(e)
        # إذا كان الخطأ متعلق بالفورمات وليس بصحة الكوكيز، نعتبرها صالحة
        if "format is not available" in error_msg:
             return True, "✅ الكوكيز صالحة (تم تخطي خطأ الفورمات)"
        return False, f"❌ الكوكيز غير صالحة: {error_msg}"

# ================================
# أوامر إدارة الكوكيز
# ================================

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة إعدادات الكوكيز"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    config = load_cookies_config()
    cookies_status = "✅ مفعل" if config.get("enabled", False) else "❌ غير مفعل"
    
    cookies_path = config.get("cookies_file", COOKIES_FILE)
    is_valid, validation_msg = validate_cookies_file(cookies_path) if config.get("enabled", False) else (False, "غير مفعل")
    
    message = (
        f"🍪 **إعدادات الكوكيز:**\n\n"
        f"• الحالة: {cookies_status}\n"
        f"• الملف: {cookies_path}\n"
        f"• الصلاحية: {validation_msg}\n\n"
        f"**الأوامر المتاحة:**\n"
        f"/cookies_on - تفعيل الكوكيز\n"
        f"/cookies_off - إيقاف الكوكيز\n"
        f"/cookies_upload - رفع ملف كوكيز جديد\n"
        f"/cookies_status - عرض الحالة الحالية\n"
    )
    
    await update.message.reply_text(message)

async def cookies_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل استخدام الكوكيز"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    config = load_cookies_config()
    config["enabled"] = True
    save_cookies_config(config)
    
    cookies_path = config.get("cookies_file", COOKIES_FILE)
    is_valid, validation_msg = validate_cookies_file(cookies_path)
    
    if is_valid:
        await update.message.reply_text(f"✅ تم تفعيل الكوكيز\n{validation_msg}")
    else:
        await update.message.reply_text(f"⚠️ تم تفعيل الكوكيز ولكن: {validation_msg}")

async def cookies_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إيقاف استخدام الكوكيز"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    config = load_cookies_config()
    config["enabled"] = False
    save_cookies_config(config)
    
    await update.message.reply_text("✅ تم إيقاف الكوكيز")

async def cookies_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب رفع ملف الكوكيز"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    message = (
        "📤 **رفع ملف الكوكيز:**\n\n"
        "1. أنشئ ملف `cookies.txt` من متصفحك الشخصي\n"
        "2. أرسل الملف كـ **ملف نصي** إلى هذا البوت\n"
        "3. سيتم التحقق من صحته تلقائياً\n\n"
        "🛠 **كيف تنشئ الملف:**\n"
        "• استخدم إضافة 'Get cookies.txt LOCALLY' لمتصفح Chrome\n"
        "• أو انسخ الكوكيز يدوياً من Developer Tools\n\n"
        "⏳ بانتظار رفع الملف..."
    )
    
    await update.message.reply_text(message)
    
    # حفظ حالة المستخدم لمعالجة الملف
    if 'user_states' not in context.chat_data:
        context.chat_data['user_states'] = {}
    context.chat_data['user_states'][user_id] = 'awaiting_cookies_file'

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات المرسلة"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    # التحقق إذا كان المستخدم ينتظر ملف كوكيز
    user_states = context.chat_data.get('user_states', {})
    if user_states.get(user_id) != 'awaiting_cookies_file':
        return

    document = update.message.document
    
    # التحقق من نوع الملف
    if document.mime_type != 'text/plain' and not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يرجى رفع ملف نصي (txt) فقط")
        return

    try:
        # تحميل الملف
        file = await context.bot.get_file(document.file_id)
        
        # حفظ الملف مؤقتاً
        temp_file = f"temp_cookies_{user_id}.txt"
        await file.download_to_drive(temp_file)
        
        # التحقق من صحة الملف
        is_valid, validation_msg = validate_cookies_file(temp_file)
        
        if is_valid:
            # نسخ الملف إلى المكان الرئيسي
            import shutil
            shutil.copy(temp_file, COOKIES_FILE)
            
            # تفعيل الكوكيز تلقائياً
            config = load_cookies_config()
            config["enabled"] = True
            config["cookies_file"] = COOKIES_FILE
            save_cookies_config(config)
            
            # تنظيف الملف المؤقت
            os.remove(temp_file)
            
            # إزالة حالة المستخدم
            context.chat_data['user_states'][user_id] = None
            
            await update.message.reply_text(
                f"✅ تم رفع ملف الكوكيز بنجاح!\n"
                f"{validation_msg}\n\n"
                f"🍪 الكوكيز مفعلة الآن تلقائياً"
            )
        else:
            # تنظيف الملف المؤقت
            os.remove(temp_file)
            context.chat_data['user_states'][user_id] = None
            
            await update.message.reply_text(
                f"❌ ملف الكوكيز غير صالح\n"
                f"{validation_msg}\n\n"
                f"⚠️ يرجى التأكد من صحة الملف والمحاولة مرة أخرى"
            )
            
    except Exception as e:
        logger.error(f"خطأ في معالجة ملف الكوكيز: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء معالجة الملف")

async def cookies_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة الكوكيز الحالية"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    config = load_cookies_config()
    cookies_path = config.get("cookies_file", COOKIES_FILE)
    
    if os.path.exists(cookies_path):
        file_size = os.path.getsize(cookies_path)
        with open(cookies_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        message = (
            f"📊 **حالة الكوكيز:**\n\n"
            f"• الحالة: {'✅ مفعل' if config.get('enabled', False) else '❌ معطل'}\n"
            f"• حجم الملف: {file_size} بايت\n"
            f"• عدد السجلات: {len(lines)} سطر\n"
            f"• المسار: {cookies_path}\n\n"
        )
        
        # عرض بعض الكوكيز كمثال (بدون قيم حساسة)
        sample_cookies = []
        for line in lines[:5]:  # أول 5 سطور فقط
            parts = line.strip().split('\t')
            if len(parts) >= 6:
                sample_cookies.append(f"• {parts[5]}: {'*' * 10}")
        
        if sample_cookies:
            message += "🔍 **عينة من الكوكيز:**\n" + "\n".join(sample_cookies)
        
    else:
        message = "❌ لا يوجد ملف كوكيز حالياً"
    
    await update.message.reply_text(message)

# ================================
# نظام التحميل مع الكوكيز
# ================================

def download_media(url: str, audio_only: bool = False) -> str:
    """تحميل الميديا مع محاولات متعددة للصيغ في حالة الفشل"""
    cookies_path = get_active_cookies_path()
    
    # قائمة بأساليب التحميل (صيغ مختلفة)
    # سنحاول بـ 5 جودات شائعة تدريجياً لضمان النجاح
    if audio_only:
        formats_to_try = [
            'bestaudio/best',
            'bestaudio[ext=m4a]/best',
            'best'
        ]
    else:
        formats_to_try = [
            # 1. محاولة الجودة المفضلة مع مرونة عالية (تفضل mp4 ولكن تقبل غيره)
            'bestvideo[height<=?720]+bestaudio/best[height<=?720]/best',
            # 2. جودة متوسطة لضمان العمل في الفتحات المحدودة
            'bestvideo[height<=?480]+bestaudio/best[height<=?480]/best',
            # 3. أي جودة متاحة بأي صيغة
            'bestvideo+bestaudio/best',
            # 4. التنسيق الأساسي (الأكثر استقراراً للفيديوهات المحمية)
            'best'
        ]

    last_exception = None
    for i, fmt in enumerate(formats_to_try):
        logger.info(f"🔄 محاولة التحميل بالصيغة رقم {i+1}: {fmt}")
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title).70s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'cookiefile': cookies_path,
            'compat_opts': ['no-youtube-unavailable'],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }
            
        if audio_only:
            ydl_opts.update({
                'format': fmt,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': fmt,
                'merge_output_format': 'mp4',
            })
            
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = os.path.dirname(FFMPEG_PATH)

        def check_duration(info, *, incomplete):
            duration = info.get('duration')
            if duration and duration > MAX_DURATION_SECONDS:
                return "⏱️ الفيديو أطول من المسموح به."
            return None

        ydl_opts['match_filter'] = check_duration

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dict)
                
                if audio_only:
                    filename = os.path.splitext(filename)[0] + '.mp3'
                
                logger.info(f"✅ تم التحميل بالصيغة {i+1}: {filename}")
                return filename
                
        except Exception as e:
            error_str = str(e)
            last_exception = e
            logger.warning(f"⚠️ فشلت المحاولة {i+1} بالصيغة {fmt}: {error_str[:100]}...")
            
            # إذا كان الخطأ متعلق بالتنسيق فقط، استمر في الحلقة
            if "format is not available" in error_str or "Requested format" in error_str:
                continue
            
            # إذا كان الفيديو محمي بطلب تسجيل دخول، حاول بدون كوكيز (لو كانت مفعلة)
            if "Sign in" in error_str and cookies_path:
                logger.warning("🔄 تجربة التحميل بدون كوكيز...")
                return download_media_without_cookies(url, audio_only)
                
            # أي خطأ آخر غير التنسيق، ارفع الاستثناء لو كانت هذه آخر محاولة
            if i == len(formats_to_try) - 1:
                break

    # إذا انتهت الحلقة ولم ينجح التحميل
    raise Exception(f"❌ تعذر تحميل الفيديو بأي صيغة متاحة: {str(last_exception)}")

def download_media_without_cookies(url: str, audio_only: bool = False) -> str:
    """تحميل الميديا بدون كوكيز مع محاولات متعددة للصيغ"""
    logger.info("🌀 تجربة التحميل بدون كوكيز مع محاولات متعددة للصيغ")
    
    if audio_only:
        formats_to_try = [
            'bestaudio/best',
            'bestaudio[ext=m4a]/best[ext=mp4]/best',
            'best'
        ]
    else:
        formats_to_try = [
            'bestvideo[height<=?720][ext=mp4]+bestaudio[ext=m4a]/best[height<=?720][ext=mp4]/best',
            'bestvideo[height<=?720]+bestaudio/best[height<=?720]/best',
            'bestvideo[height<=?480]+bestaudio/best[height<=?480]/best',
            'bestvideo+bestaudio/best',
            'best'
        ]

    last_exception = None
    for i, fmt in enumerate(formats_to_try):
        logger.info(f"🌀 (بدون كوكيز) محاولة بالصيغة رقم {i+1}: {fmt}")
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title).70s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
            }
        }
            
        if audio_only:
            ydl_opts.update({
                'format': fmt,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': fmt,
                'merge_output_format': 'mp4',
            })
            
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = os.path.dirname(FFMPEG_PATH)

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info_dict)
                if audio_only:
                    filename = os.path.splitext(filename)[0] + '.mp3'
                
                logger.info(f"✅ تم التحميل بنجاح بدون كوكيز بالصيغة {i+1}: {filename}")
                return filename
        except Exception as e:
            error_str = str(e)
            last_exception = e
            logger.warning(f"🌀 محاولة {i+1} بدون كوكيز فشلت: {error_str[:100]}...")
            if "format is not available" in error_str or "Requested format" in error_str:
                continue
            if i == len(formats_to_try) - 1:
                break

    raise Exception(f"❌ تعذر التحميل حتى بدون كوكيز: {str(last_exception)}")

# ================================
# باقي الدوال الأساسية
# ================================

user_links = {}

def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # تحديث الهيكل القديم لو وجد
            updated = False
            for uid in data:
                if isinstance(data[uid], str):
                    data[uid] = {
                        "username": data[uid],
                        "banned": False,
                        "date_joined": "غير معروف"
                    }
                    updated = True
            if updated:
                save_users(data)
            return data
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return True  # تجاهل الخطأ حتى لا يتعطل البوت للجميع

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_subscribed(context, user_id):
        await update.message.reply_text(
            "🔒 لا يمكنك استخدام البوت حتى تشترك في القناة أولاً:\n"
            f"{REQUIRED_CHANNEL}"
        )
        return

    msg = (
        "👋 أهلاً بك في بوت التحميل!\n\n"
        "أرسل رابط فيديو من YouTube أو TikTok أو Instagram وسأقوم بتحميله لك.\n"
        "اكتب /help لعرض التعليمات."
    )
    
    if user_id in ADMIN_IDS:
        config = load_cookies_config()
        cookies_status = "✅ مفعل" if config.get("enabled", False) else "❌ غير مفعل"
        msg += (
            f"\n\n🛠️ **معلومات المسؤول:**\n"
            f"🍪 الكوكيز: {cookies_status}\n"
            f"🔊 تحويل الصوت: {'✅ متاح' if FFMPEG_PATH else '❌ غير متاح'}\n"
            f"اكتب /admin لفتح لوحة التحكم."
        )
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📌 *تعليمات استخدام البوت:*\n"
        "1. أرسل رابط لفيديو من YouTube أو TikTok أو Instagram أو Twitter أو Facebook.\n"
        "2. سيتم سؤالك إن كنت تريد تحميل الفيديو أو الصوت فقط.\n"
        "3. اختر الخيار المناسب وانتظر حتى يكتمل التحميل.\n\n"
        "⚠️ البوت لا يدعم:\n"
        "• روابط خاصة أو محمية بكلمة مرور\n"
        "• الفيديوهات الأطول من ساعة ونصف\n"
        "• الفيديوهات الأكبر من 50MB\n\n"
        "💬 إن واجهت مشكلة، أعد المحاولة أو تحقق من صحة الرابط."
    )
    
    await update.message.reply_text(help_text)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الواجهة الرئيسية للإدارة بلوحة مفاتيح واضحة"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 هذه الميزة مخصصة للمسؤول فقط.")
        return

    keyboard = [
        ['📊 إحصائيات البوت', '👥 قائمة الأعضاء'],
        ['🚫 المحظورين', '📢 إذاعة رسالة'],
        ['🍪 الكوكيز', '🔙 خروج']
    ]
    
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "🛠 **لوحة تحكم المسؤول**\nتم تفعيل لوحة التحكم السريعة.",
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # إعادة توجيه للأمر الجديد
    await admin_command(update, context)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("🚫 غير مصرح لك.", show_alert=True)
        return

    data = query.data
    
    if data == 'admin_stats':
        users = load_users()
        total_users = len(users)
        banned_users = sum(1 for u in users.values() if u.get('banned', False))
        active_users = total_users - banned_users
        
        msg = (
            f"📊 **إحصائيات النظام:**\n\n"
            f"👤 إجمالي المستخدمين: {total_users}\n"
            f"✅ المستخدمين النشطين: {active_users}\n"
            f"🚫 المستخدمين المحظورين: {banned_users}\n"
            f"🔊 FFmpeg: {'✅' if FFMPEG_PATH else '❌'}\n"
        )
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ عودة", callback_data='admin_back')]]), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith('admin_users_'):
        page = int(data.split('_')[2])
        users = load_users()
        user_list = list(users.items())
        per_page = 10 # زيادة العدد قليلاً
        start = (page - 1) * per_page
        end = start + per_page
        
        msg = f"👥 **قائمة المستخدمين (صفحة {page} من {math.ceil(len(user_list)/per_page)}):**\n\n"
        buttons = []
        
        for uid, udata in user_list[start:end]:
            status = "🚫" if udata.get('banned', False) else "✅"
            msg += f"{status} `{uid}` - @{udata.get('username', 'N/A')}\n"
            buttons.append([InlineKeyboardButton(f"إدارة {uid}", callback_data=f"manage_user_{uid}")])
            
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_users_{page-1}"))
        if end < len(user_list):
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin_users_{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
            
        buttons.append([InlineKeyboardButton("⬅️ عودة لوحة التحكم", callback_data='admin_back')])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith('manage_user_'):
        target_id = data.split('_')[2]
        users = load_users()
        udata = users.get(target_id)
        if not udata:
            await query.answer("❌ مستخدم غير موجود.")
            return
            
        is_banned = udata.get('banned', False)
        status_text = "محظور 🚫" if is_banned else "نشط ✅"
        ban_button_text = "فك الحظر ✅" if is_banned else "حظر 🚫"
        ban_action = "unban" if is_banned else "ban"
        
        msg = (
            f"👤 **إدارة المستخدم:**\n"
            f"• ID: `{target_id}`\n"
            f"• اليوزر: @{udata.get('username')}\n"
            f"• الحالة: {status_text}\n"
        )
        
        buttons = [
            [InlineKeyboardButton(ban_button_text, callback_data=f"act_{ban_action}_{target_id}")],
            [InlineKeyboardButton("⬅️ عودة للقائمة", callback_data='admin_users_1')]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith('act_'):
        parts = data.split('_')
        action = parts[1]
        target_id = parts[2]
        users = load_users()
        
        if action == 'ban':
            users[target_id]['banned'] = True
            await query.answer(f"✅ تم حظر {target_id}", show_alert=True)
        else:
            users[target_id]['banned'] = False
            await query.answer(f"✅ تم فك حظر {target_id}", show_alert=True)
            
        save_users(users)
        # العودة لصفحة المستخدم
        await admin_callback(update, context) # Re-trigger management view

    elif data == 'admin_broadcast':
        await query.edit_message_text("📢 **أرسل الآن الرسالة التي تريد إذاعتها لجميع المستخدمين.**\nأو اكتب /cancel للإلغاء.", parse_mode=ParseMode.MARKDOWN)
        context.user_data['state'] = 'awaiting_broadcast'

    elif data == 'admin_cookies':
        # إعادة توجيه لوظائف الكوكيز الموجودة
        await cookies_command(update, context)

    elif data == 'admin_back':
        await admin_command(update, context)
        await query.delete_message()

    elif data == 'admin_close':
        await query.delete_message()

    elif data == 'admin_banned':
        users = load_users()
        banned = [uid for uid, u in users.items() if u.get('banned', False)]
        if not banned:
            await query.answer("لا يوجد مستخدمين محظورين.", show_alert=True)
            return
            
        msg = "🚫 **قائمة المحظورين:**\n\n"
        buttons = []
        for uid in banned:
            msg += f"• `{uid}`\n"
            buttons.append([InlineKeyboardButton(f"فك حظر {uid}", callback_data=f"act_unban_{uid}")])
            
        buttons.append([InlineKeyboardButton("⬅️ عودة", callback_data='admin_back')])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not await is_user_subscribed(context, int(user_id)):
        await update.message.reply_text(
            "🔒 لا يمكنك استخدام البوت حتى تشترك في القناة أولاً:\n"
            f"{REQUIRED_CHANNEL}"
        )
        return

    users = load_users()
    username = update.effective_user.username or "بدون اسم مستخدم"
    
    if user_id in users:
        if users[user_id].get('banned', False):
            await update.message.reply_text("🚫 عذراً، لقد تم حظرك من استخدام هذا البوت.")
            return
    
    if user_id not in users:
        users[user_id] = {
            "username": username,
            "banned": False,
            "date_joined": str(asyncio.get_event_loop().time()) # تبسيط للتاريخ
        }
        save_users(users)
        logger.info(f"✅ تم تسجيل مستخدم جديد: {user_id} - {username}")
    else:
        # تحديث الاسم لو تغير
        if users[user_id].get('username') != username:
            users[user_id]['username'] = username
            save_users(users)
        logger.info(f"📌 المستخدم موجود مسبقًا: {user_id} - {username}")

    # ميزة الإذاعة
    if context.user_data.get('state') == 'awaiting_broadcast':
        if update.message.text == '/cancel':
            context.user_data['state'] = None
            await update.message.reply_text("❌ تم إلغاء الإذاعة.")
            return
            
        msg_to_send = update.message.text
        context.user_data['state'] = None
        await update.message.reply_text("⏳ جارٍ بدء الإذاعة...")
        
        success = 0
        fail = 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📢 **رسالة من الإدارة:**\n\n{msg_to_send}", parse_mode=ParseMode.MARKDOWN)
                success += 1
            except:
                fail += 1
        
        await update.message.reply_text(f"✅ اكتملت الإذاعة!\nتم الإرسال لـ: {success}\nفشل الإرسال لـ: {fail}")
        return

    # معالجة أزرار لوحة التحكم
    if user_id in map(str, ADMIN_IDS):
        text = update.message.text
        if text == '📊 إحصائيات البوت':
            users = load_users()
            total_users = len(users)
            banned_users = sum(1 for u in users.values() if u.get('banned', False))
            msg = (
                f"📊 **إحصائيات النظام:**\n\n"
                f"👤 إجمالي المستخدمين: {total_users}\n"
                f"✅ النشطين: {total_users - banned_users}\n"
                f"🚫 المحظورين: {banned_users}\n"
                f"🔊 FFmpeg: {'✅' if FFMPEG_PATH else '❌'}"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return
        elif text == '👥 قائمة الأعضاء':
            # نستخدم نفس معالج الإنلاين لعرض القائمة بشكل منظم
            users = load_users()
            user_list = list(users.items())
            if not user_list:
                await update.message.reply_text("لا يوجد أعضاء مسجلين حالياً.")
                return
            
            # بدلاً من عرض 5 فقط، نعيد التوجيه لمعالج الصفحات
            # بما أن الضغطة أتت من زر كيبورد عادي، سنرسل رسالة جديدة تحتوي على الصفحة الأولى
            msg = f"👥 **عرض جميع الأعضاء (إجمالي: {len(user_list)}):**\nالرجاء اختيار مستخدم لإدارته:"
            buttons = []
            per_page = 10
            for uid, udata in user_list[:per_page]:
                status = "🚫" if udata.get('banned', False) else "✅"
                buttons.append([InlineKeyboardButton(f"{status} {uid} (@{udata.get('username', 'N/A')})", callback_data=f"manage_user_{uid}")])
            
            if len(user_list) > per_page:
                buttons.append([InlineKeyboardButton("عرض الصفحة التالية ➡️", callback_data="admin_users_2")])
            
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return
        elif text == '🚫 المحظورين':
            users = load_users()
            banned = [uid for uid, u in users.items() if u.get('banned', False)]
            if not banned:
                await update.message.reply_text("لا يوجد مستخدمين محظورين.")
                return
            msg = "🚫 **قائمة المحظورين:**\n\n"
            buttons = []
            for uid in banned:
                msg += f"• `{uid}`\n"
                buttons.append([InlineKeyboardButton(f"فك حظر {uid}", callback_data=f"act_unban_{uid}")])
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return
        elif text == '📢 إذاعة رسالة':
            await update.message.reply_text("📢 أرسل الآن الرسالة المراد إذاعتها، أو اكتب /cancel للإلغاء.")
            context.user_data['state'] = 'awaiting_broadcast'
            return
        elif text == '🍪 الكوكيز':
            await cookies_command(update, context)
            return
        elif text == '🔙 خروج':
            await update.message.reply_text("🔙 تم الخروج من وضع الإدارة وإزالة لوحة التحكم.", reply_markup=ReplyKeyboardRemove())
            return

    url = update.message.text.strip()
    
    if 'youtu.be' in url or 'youtube.com' in url:
        if '?' in url:
            url = url.split('?')[0]
        if '&' in url:
            url = url.split('&')[0]
    
    if any(domain in url for domain in SUPPORTED_SITES):
        user_links[user_id] = url
        
        if FFMPEG_PATH:
            buttons = [
                [InlineKeyboardButton("🎵 صوت فقط", callback_data='audio'),
                 InlineKeyboardButton("🎞️ فيديو", callback_data='video')]
            ]
            message_text = "📥 هل تريد تحميل الصوت فقط أم الفيديو؟"
        else:
            buttons = [
                [InlineKeyboardButton("🎞️ فيديو", callback_data='video')]
            ]
            message_text = "📥 تحميل الفيديو (تحويل الصوت غير متاح حالياً)"
            
        await update.message.reply_text(
            message_text, 
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            "⚠️ أرسل رابط صحيح من المواقع المدعومة فقط:\n"
            "YouTube, TikTok, Instagram, Twitter, Facebook."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # التحقق من نوع الكالباك (إدارة أم تحميل)
    if query.data.startswith('admin_') or query.data.startswith('manage_user_') or query.data.startswith('act_'):
        await admin_callback(update, context)
        return

    await query.answer()
    
    user_id = str(query.from_user.id)
    url = user_links.get(user_id)
    
    if not url:
        await query.edit_message_text("❌ لم يتم العثور على الرابط، أرسل الرابط مرة أخرى.")
        return

    await query.edit_message_text("🔄 جارٍ التحميل، يرجى الانتظار...")
    
    try:
        audio_only = query.data == 'audio'
        filepath = None
        
        if audio_only and not FFMPEG_PATH:
            await query.message.reply_text("❌ تحويل الصوت غير متاح حالياً. يرجى تثبيت ffmpeg.")
            return
        
        filepath = await asyncio.to_thread(download_media, url, audio_only)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"الملف {filepath} غير موجود")
        
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            await query.message.reply_text("❌ حجم الملف كبير جداً ولا يمكن إرساله عبر التيليجرام.")
            return
        
        with open(filepath, 'rb') as f:
            if audio_only:
                await query.message.reply_audio(
                    audio=f,
                    title=os.path.basename(filepath).replace('.mp3', '')[:64],
                    performer="IXL Download",
                    read_timeout=350,
                    write_timeout=350
                )
            else:
                await query.message.reply_video(
                    video=f,
                    supports_streaming=True,
                    read_timeout=350,
                    write_timeout=350,
                    caption="Uploaded by yazmeely "
                )
        
        logger.info(f"✅ تم إرسال الملف بنجاح للمستخدم {user_id}")
        
    except Exception as e:
        error_msg = f"❌ حدث خطأ أثناء التحميل:\n{str(e)}"
        logger.error(f"خطأ للمستخدم {user_id}: {e}")
        await query.message.reply_text(error_msg)
    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                logger.error(f"خطأ في حذف الملف: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"حدث خطأ: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.")

# تشغيل البوت
def main():
    try:
        # إعداد المجلدات
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        # تحميل إعدادات الكوكيز
        config = load_cookies_config()
        logger.info(f"🍪 إعدادات الكوكيز: {'مفعل' if config.get('enabled', False) else 'معطل'}")
        
        # استيراد math للصفحات
        import math
        
        # بناء التطبيق مع دعم التعددية (Concurrent Updates)
        app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

        # إضافة المعالجات
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("dashboard", dashboard))
        app.add_handler(CommandHandler("admin", admin_command))
        app.add_handler(CommandHandler("cookies", cookies_command))
        app.add_handler(CommandHandler("cookies_on", cookies_on))
        app.add_handler(CommandHandler("cookies_off", cookies_off))
        app.add_handler(CommandHandler("cookies_upload", cookies_upload))
        app.add_handler(CommandHandler("cookies_status", cookies_status))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(CallbackQueryHandler(button_callback))
        
        app.add_error_handler(error_handler)

        print("=" * 50)
        print("✅ البوت يعمل الآن...")
        print(f"🔊 FFmpeg: {'✅ متوفر' if FFMPEG_PATH else '❌ غير متوفر'}")
        config = load_cookies_config()
        print(f"🍪 الكوكيز: {'✅ مفعل' if config.get('enabled', False) else '❌ معطل'}")
        print("=" * 50)
        
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"خطأ في تشغيل البوت: {e}")

if __name__ == '__main__':
    main()
