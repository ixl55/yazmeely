FROM python:3.12-slim

# ffmpeg للدمج وتحويل الصوت، و deno لأن yt-dlp يحتاج JS runtime لفك تشفير يوتيوب
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .

ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data
VOLUME ["/app/data"]

# تحديث yt-dlp عند كل تشغيل (يوتيوب يغيّر الحماية باستمرار)
CMD pip install --no-cache-dir -q -U "yt-dlp[default]" bgutil-ytdlp-pot-provider; python bot.py
