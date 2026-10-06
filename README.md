# yazmeely — بوت تحميل تيليجرام

<img src="https://th.bing.com/th/id/R.ba83d4b3fd2099e44fe580d519e08037?rik=NJoyNWb%2boU7wXQ&pid=ImgRaw&r=0" width="300">

بوت يحمّل الفيديو أو الصوت من YouTube و TikTok و Instagram و X (Twitter) و Facebook، وفيه لوحة إدارة (إحصائيات، حظر، إذاعة، إدارة الكوكيز).

**Use it legally..** حمّل فقط محتوى يحق لك تحميله.

---

## التشغيل السريع

```bash
cp .env.example .env      # ثم ضع BOT_TOKEN و ADMIN_IDS
pip install -r requirements.txt
python bot.py
```

لازم يكون مثبتاً على الجهاز:
- **ffmpeg**: لدمج الفيديو مع الصوت وتحويله إلى mp3.
- **deno** (أو node): yt-dlp يحتاجه لفك تشفير يوتيوب. بدونه كثير من الفيديوهات تفشل.
  تثبيت deno: `curl -fsSL https://deno.land/install.sh | sh`

## التشغيل بـ Docker (الطريقة المفضلة للسيرفر)

```bash
cp .env.example .env      # املأ القيم
docker compose up -d --build
docker compose logs -f bot
```

هذا يشغّل البوت ومعه خادم **PO Token** (bgutil)، وهو يحل جزءاً كبيراً من مشكلة حظر يوتيوب. ويحدّث yt-dlp تلقائياً مع كل تشغيل.

---

## ⚠️ لماذا يتبنّد البوت من يوتيوب على السيرفر؟

يوتيوب يعرف عناوين IP الخاصة بمراكز البيانات (VPS و AWS و Hetzner و Render و Railway وغيرها)، فيرد بخطأ:

```
Sign in to confirm you're not a bot
```

على جهازك الشخصي يعمل البوت لأن الـ IP منزلي (residential). **لا يوجد حل سحري واحد.** هذه الحلول مرتبة من الأسهل للأقوى، والأفضل أن تجمع بين أكثر من حل:

### 1) حدّث yt-dlp دائماً + ثبّت deno
يوتيوب يغيّر حمايته كل أسبوع تقريباً، ونسخة yt-dlp القديمة تفشل.
```bash
pip install -U "yt-dlp[default]"
```
الـ Dockerfile يعمل هذا تلقائياً.

### 2) PO Token (مجاني ومفعّل في docker-compose)
خادم `bgutil-ytdlp-pot-provider` يولّد توكنات تجعل الطلب يبدو كأنه من متصفح حقيقي.
بدون Docker:
```bash
docker run -d --name bgutil -p 4416:4416 --init brainicism/bgutil-ytdlp-pot-provider
# وفي .env:
POT_PROVIDER_URL=http://127.0.0.1:4416
```

### 3) الكوكيز من حساب ثانوي
- استخدم **حساب يوتيوب جديد/ثانوي، وليس حسابك الأساسي** (قد يُحظر الحساب).
- افتح نافذة تصفح خفي ← سجّل الدخول ← افتح youtube.com ← صدّر الكوكيز بإضافة *Get cookies.txt LOCALLY* ← أغلق النافذة **بدون تسجيل خروج**.
- أرسل الأمر `/cookies_upload` للبوت ثم أرسل الملف. افحصها متى شئت بـ `/cookies_status`.
- الكوكيز تنتهي بعد فترة، وسيرسل لك البوت تنبيهاً عندما يبدأ يوتيوب بالحظر.

### 4) بروكسي سكني (Residential Proxy) — الحل الأقوى
هذا ما تستخدمه البوتات الكبيرة. ضع في `.env`:
```
PROXY=http://user:pass@host:port
```
⚠️ البروكسيات المجانية وبروكسيات مراكز البيانات غالباً محظورة أيضاً. اختر خدمة "residential" أو "ISP".

### 5) Cloudflare WARP (مجاني، ينجح أحياناً)
شغّل WARP على السيرفر بوضع proxy (مثلاً عبر `warp-cli mode proxy` أو حاوية `wireproxy`)، ثم:
```
PROXY=socks5://127.0.0.1:40000
```

### 6) استضافة البوت على IP منزلي
تشغيل البوت على جهاز في البيت (Raspberry Pi، لابتوب قديم، أو كمبيوترك) يحل المشكلة نهائياً تقريباً، لأن الـ IP منزلي.

### نصائح إضافية
- قلّل `MAX_CONCURRENT_DOWNLOADS` (القيمة الافتراضية 2): الطلبات الكثيرة في نفس الوقت تسرّع الحظر.
- جرّب تغيير العملاء: `YT_PLAYER_CLIENTS=default,tv,web_safari`.
- إذا حُظر الـ IP بشدة، فتغيير السيرفر أو الـ IP يعيد البوت للعمل مؤقتاً فقط.

---

## الملفات الكبيرة (أكثر من 50MB)
Bot API الرسمي لا يسمح برفع ملفات أكبر من 50MB. لرفع ملفات حتى 2GB شغّل
[Local Bot API Server](https://github.com/tdlib/telegram-bot-api) وضع:
```
TELEGRAM_API_URL=http://localhost:8081
MAX_FILE_SIZE_MB=2000
```

## الأوامر
| الأمر | الوصف |
|---|---|
| `/start`، `/help` | البدء والتعليمات |
| `/admin` | لوحة الإدارة (للمسؤول فقط) |
| `/cookies`، `/cookies_upload`، `/cookies_status`، `/cookies_on`، `/cookies_off` | إدارة الكوكيز |
| `/cancel` | إلغاء الإذاعة أو رفع الكوكيز |

## الأمان
لا تكتب التوكن داخل الكود ولا ترفع `.env` أو `cookies.txt` إلى GitHub (موجودة في `.gitignore`).
