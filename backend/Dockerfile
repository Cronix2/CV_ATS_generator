# PasseFiltre API: FastAPI + Scrapling (headless Chromium) + LangChain. The same image runs the isolated
# CAPTCHA browser (headful, virtual screen) and its egress proxy as separate services (docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY requirements.lock .
# Every dependency pinned and hash-checked; Chromium + its system libraries installed as root,
# then everything runs as an unprivileged user.
# The scraper (Scrapling's StealthySession) launches Chromium through PATCHRIGHT, not Playwright.
# Both are installed and each pins its own Chromium revision (e.g. patchright 1.63.0 -> 1243,
# playwright 1.64.0 -> 1248): the browser MUST be installed by patchright's own CLI so its
# revision always matches the locked patchright version. Playwright's browser is not needed.
# Remote CAPTCHA solving (app/scraper/browser_host.py, run as the separate captcha-browser service): Xvfb
# (private virtual screen for a headful Chromium) and x11vnc (shows it on a Unix socket in /run/pf-captcha,
# a volume shared with the API, which bridges it). Debian packages, arm64 included.
# /tmp/.X11-unix must exist beforehand: Xvfb runs as the unprivileged user and cannot create it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc \
 && mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix \
 && pip install --require-hashes -r requirements.lock \
 && python -m patchright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
 && mkdir -p /app/.sessions /run/pf-captcha \
 && chown app:app /app/.sessions /run/pf-captcha \
 && chmod 700 /app/.sessions /run/pf-captcha

# Defense in depth for the human-driven CAPTCHA browser (harmless for the headless scraper): no file://
# pages, no file picker (uploads), no downloads, no saved passwords. Chromium and Chrome for Testing
# builds read different directories: install the managed policy in each.
COPY chromium-policies.json /etc/chromium/policies/managed/passefiltre.json
COPY chromium-policies.json /etc/opt/chrome/policies/managed/passefiltre.json
COPY chromium-policies.json /etc/opt/chrome_for_testing/policies/managed/passefiltre.json

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

USER app
# Fail the build if the Chromium that patchright expects is missing (no launch: works under QEMU).
# The real launch test runs in CI / before deployment: python -m app.scraper.browser_check
RUN python -m app.scraper.browser_check --static
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# --proxy-headers: behind the HTTPS proxy, the audit log and the local-client checks see the real client IP
# (trusted only from FORWARDED_ALLOW_IPS, set by docker-compose).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
