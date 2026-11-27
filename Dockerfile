FROM python:3.12-slim-trixie@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Kyiv \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
        fonts-dejavu-core \
        fonts-liberation \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libharfbuzz-subset0 \
        libffi8 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install --upgrade "pip==26.3" \
    && python -m pip install --only-binary=:all: -r /tmp/requirements.txt \
    && python -m pip check \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.12/ensurepip \
    && rm /tmp/requirements.txt

USER 1000:1000

CMD ["sleep", "infinity"]
