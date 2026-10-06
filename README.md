# yazmeely — Telegram Downloader Bot

<img src="https://th.bing.com/th/id/R.ba83d4b3fd2099e44fe580d519e08037?rik=NJoyNWb%2boU7wXQ&pid=ImgRaw&r=0" width="300">

A Telegram bot that downloads video or audio from YouTube, TikTok, Instagram, X (Twitter) and Facebook, with an admin panel (stats, ban/unban, broadcast, cookies management).

**Use it legally..** Only download content you have the right to download.

[🇸🇦 النسخة العربية بالأسفل](#arabic)

## Quick start

```bash
cp .env.example .env      # set BOT_TOKEN and ADMIN_IDS
pip install -r requirements.txt
python bot.py
```

Required on the machine:
- **ffmpeg**: merges video + audio and converts to mp3.
- **deno** (or node): yt-dlp needs a JS runtime to solve YouTube challenges. Without it many videos fail.
  Install deno: `curl -fsSL https://deno.land/install.sh | sh`

## Run with Docker (recommended for servers)

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f bot
```

This runs the bot together with a **PO Token** server (bgutil), which fixes a large part of the YouTube blocking problem. yt-dlp is auto-updated on every start.

## ⚠️ Why does YouTube block the bot on a server?

YouTube knows datacenter IP ranges (VPS, AWS, Hetzner, Render, Railway, ...) and answers with:

```
Sign in to confirm you're not a bot
```

It works on your PC because your IP is residential. **There is no single magic fix** — combine several:

1. **Keep yt-dlp updated + install deno**: `pip install -U "yt-dlp[default]"` (the Dockerfile does this automatically).
2. **PO Token (free, enabled in docker-compose)**. Without Docker:
   ```bash
   docker run -d --name bgutil -p 4416:4416 --init brainicism/bgutil-ytdlp-pot-provider
   # in .env:
   POT_PROVIDER_URL=http://127.0.0.1:4416
   ```
3. **Cookies from a secondary account** (never your main one — it may get banned). Open an incognito window → log in → open youtube.com → export with *Get cookies.txt LOCALLY* → close the window **without logging out**. Send `/cookies_upload` to the bot, then the file. Check anytime with `/cookies_status`.
4. **Residential proxy — the strongest fix**. Put in `.env`:
   ```
   PROXY=http://user:pass@host:port
   ```
   Free and datacenter proxies are usually blocked too — pick "residential" or "ISP".
5. **Cloudflare WARP (free, works sometimes)**: run WARP in proxy mode (`warp-cli mode proxy` or a `wireproxy` container), then `PROXY=socks5://127.0.0.1:40000`.
6. **Host the bot on a home IP** (Raspberry Pi, old laptop) — almost always solves it.

Extra tips: keep `MAX_CONCURRENT_DOWNLOADS` low (default 2), try `YT_PLAYER_CLIENTS=default,tv,web_safari`.

### Cheapest residential proxy providers (prices as of 2026)

| Provider | Starting price | Notes |
|---|---|---|
| [Evomi](https://evomi.com) | ~$0.49/GB (down to ~$0.45/GB) | Lowest per-GB rate; low rate needs a ~$49.99/month plan |
| [Rayobyte](https://rayobyte.com) | ~$0.70/GB at 1 TB | Cheap only at high volume |
| [GloryCloud](https://www.glorycloud.com) | from ~$0.75/GB | 90M+ IP pool |
| [DataImpulse](https://dataimpulse.com) | $1.00/GB flat, $5 minimum | **Best for small bots / tight budget**, traffic doesn't expire |
| [Scrapeless](https://www.scrapeless.com) | ~$1.80/GB (~$1.44/GB on bigger plans) | 195+ countries |

> Prices change often — check the provider's site before buying.
> **Bandwidth matters**: residential proxies charge per GB and videos are big (a 720p video ≈ 30–50MB, so 1GB ≈ 20–30 videos). Lower `VIDEO_MAX_HEIGHT` (e.g. `480`) to save traffic.

## Large files (over 50MB)
The official Bot API limits uploads to 50MB. To upload up to 2GB run a
[Local Bot API Server](https://github.com/tdlib/telegram-bot-api) and set:
```
TELEGRAM_API_URL=http://localhost:8081
MAX_FILE_SIZE_MB=2000
```

## Commands
| Command | Description |
|---|---|
| `/start`, `/help` | Start and help |
| `/admin` | Admin panel (admins only) |
| `/cookies`, `/cookies_upload`, `/cookies_status`, `/cookies_on`, `/cookies_off` | Cookies management |
| `/cancel` | Cancel broadcast or cookies upload |

## Security
Never put the token in the code and never push `.env` or `cookies.txt` to GitHub (they are in `.gitignore`).

---

<a id="arabic"></a>

# النسخة العربية

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

#### أرخص مزودي البروكسي السكني (أسعار 2026)

| المزود | السعر يبدأ من | ملاحظات |
|---|---|---|
| [Evomi](https://evomi.com) | حوالي 0.49$ للجيجا (حتى 0.45$) | أرخص سعر للجيجا، لكن يحتاج باقة شهرية حوالي 49.99$ |
| [Rayobyte](https://rayobyte.com) | حوالي 0.70$ للجيجا عند 1TB | رخيص فقط مع الكميات الكبيرة |
| [GloryCloud](https://www.glorycloud.com) | من 0.75$ للجيجا | أكثر من 90 مليون IP |
| [DataImpulse](https://dataimpulse.com) | 1$ للجيجا ثابت، أقل شحن 5$ | **الأفضل للبوتات الصغيرة والميزانية المحدودة**، والرصيد لا ينتهي |
| [Scrapeless](https://www.scrapeless.com) | حوالي 1.80$ للجيجا (1.44$ للباقات الأكبر) | أكثر من 195 دولة |

> الأسعار تتغير باستمرار، تأكد من موقع المزود قبل الشراء.
> **انتبه للاستهلاك**: البروكسي السكني يُحسب بالجيجا والفيديو حجمه كبير (فيديو 720p حوالي 30–50MB، يعني 1GB ≈ 20–30 فيديو). قلّل `VIDEO_MAX_HEIGHT` (مثلاً `480`) لتوفير الاستهلاك.

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
