FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Kyiv \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp

WORKDIR /app

RUN sed -i "s|http://deb.debian.org|https://deb.debian.org|g" /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    ca-certificates \
    tzdata \
    fonts-dejavu-core \
    fonts-liberation \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["sleep", "infinity"]
