# PasseFiltre API: FastAPI + Scrapling (headless Chromium) + LangChain.
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
RUN pip install --require-hashes -r requirements.lock \
 && python -m patchright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
 && mkdir -p /app/.sessions \
 && chown app:app /app/.sessions \
 && chmod 700 /app/.sessions

COPY app ./app

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
