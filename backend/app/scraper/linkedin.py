"""LinkedIn profile scraper built on Scrapling's StealthySession.

One browser session per scrape: log in with the user's credentials, then visit
the profile page, the contact-info overlay and every /details/<section>/ page.
The browser profile (cookies) is kept per account in `.sessions/` so we don't
log in from scratch every time, which is what triggers LinkedIn's checks.
"""

import hashlib
import hmac
import os
import logging
import re
import secrets
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

from scrapling.fetchers import StealthySession
from scrapling.parser import Selector

from app.models import Basics, Profile
from app.security import PublicError
from app.scraper import captcha, parsers
from app.scraper.parsers import Entry

log = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).resolve().parents[2] / ".sessions"
DEBUG_DIR = Path(__file__).resolve().parents[3] / "debug"
# Page.goto waits for the "load" event: on a slow host (Raspberry Pi) a LinkedIn page can take > 45 s.
TIMEOUT_MS = int(float(os.getenv("SCRAPE_TIMEOUT", "90")) * 1000)
# Useless for reading text, and what keeps a profile page from reaching "load" (photos, videos, fonts).
HEAVY_RESOURCES = {"image", "media", "font"}

# Profile attribute -> LinkedIn /details/ slug
SECTIONS: dict[str, str] = {
    "experience": "experience",
    "education": "education",
    "certifications": "certifications",
    "skills": "skills",
    "languages": "languages",
    "projects": "projects",
    "volunteering": "volunteering-experiences",
    "honors": "honors",
    "publications": "publications",
    "courses": "courses",
}
PARSERS: dict[str, Callable[[list[Entry]], list]] = {
    "experience": parsers.parse_experience,
    "education": parsers.parse_education,
    "certifications": parsers.parse_certifications,
    "skills": parsers.parse_skills,
    "languages": parsers.parse_languages,
    "projects": parsers.parse_projects,
    "volunteering": parsers.parse_volunteering,
    "honors": parsers.parse_honors,
    "publications": parsers.parse_publications,
    "courses": parsers.parse_courses,
}


class ScrapeError(PublicError):
    pass


class CaptchaRequired(ScrapeError):
    """A CAPTCHA showed up in a headless browser: only a human can solve it, on a visible browser."""


class Hooks(Protocol):
    def progress(self, message: str, percent: int | None = None) -> None: ...
    def ask_code(self, message: str) -> str | None: ...
    def cancelled(self) -> bool: ...
    def captcha_open(self, display: Any, deadline: float) -> None: ...
    def captcha_closed(self) -> None: ...


def _check_cancelled(hooks: Hooks) -> None:
    if hooks.cancelled():
        raise ScrapeError("Extraction annulée.")


def normalize_profile_url(url: str) -> str:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url.strip())
    if not m:
        raise ScrapeError("URL de profil LinkedIn invalide (attendu : https://www.linkedin.com/in/<identifiant>/)")
    return f"https://www.linkedin.com/in/{m.group(1)}/"


def _server_secret() -> bytes:
    """Random per-install secret, so session folder names can't be derived from an email alone."""
    SESSIONS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_file = SESSIONS_DIR / ".secret"
    if not secret_file.exists():
        secret_file.write_bytes(secrets.token_bytes(32))
        secret_file.chmod(0o600)
    return secret_file.read_bytes()


def _session_path(email: str, password: str) -> Path:
    """Browser profile (LinkedIn cookies) bound to email AND password: knowing someone's email is not
    enough to reuse their session; a wrong password lands in an empty profile and a real, failing login."""
    key = f"{email.strip().lower()}\0{password}".encode()
    return SESSIONS_DIR / hmac.new(_server_secret(), key, hashlib.sha256).hexdigest()[:32]


def _session_dir(email: str, password: str) -> str:
    path = _session_path(email, password)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(path)


_accounts_in_use: set[str] = set()
_accounts_lock = threading.Lock()


@contextmanager
def _account_in_use(user_data_dir: str) -> Iterator[None]:
    """One browser at a time per LinkedIn profile directory (Chromium cannot share it)."""
    with _accounts_lock:
        if user_data_dir in _accounts_in_use:
            raise ScrapeError("Une extraction est déjà en cours avec ce compte LinkedIn : attendez qu'elle se termine.")
        _accounts_in_use.add(user_data_dir)
    try:
        yield
    finally:
        with _accounts_lock:
            _accounts_in_use.discard(user_data_dir)


def forget_session(email: str, password: str) -> bool:
    """Delete the saved LinkedIn session of this account (needs its credentials: nobody can wipe someone else's)."""
    path = _session_path(email, password)
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


SEE_MORE = re.compile(r"\s*(…|\.\.\.)\s*(plus|voir plus|afficher plus|see more|more)\s*$", re.I)


def _text(node: Selector) -> str:
    """Visible text of a node, keeping <br> as line breaks.

    Buttons are dropped: LinkedIn puts its "… plus" / "…see more" toggle inside the text itself."""
    html = re.sub(r"<button\b.*?</button>", "", node.html_content, flags=re.I | re.S)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    return SEE_MORE.sub("", str(Selector(html).get_all_text(separator="", strip=False)).strip())


# --------------------------------------------------------------------------- login

# LinkedIn's login page has generated ids and a hidden duplicate form: match by type, keep visible ones.
USER_INPUT = "input#username, input[name=session_key], input[autocomplete*=username], input[type=email]"
PASSWORD_INPUT = "input#password, input[name=session_password], input[type=password]"
ON_LOGIN = re.compile(r"/(login|uas/|checkpoint|authwall|signup)")


def _login(session: StealthySession, email: str, password: str, hooks: Hooks, headless: bool, debug: bool,
           display: captcha.RemoteBrowser | None = None) -> None:
    errors: list[Exception] = []

    def action(page):
        try:
            if _on_checkpoint(page.url):
                # Account under scrutiny: LinkedIn sends /login straight to its checkpoint (CAPTCHA, code...),
                # before any form. Same handling as after the form; headless + CAPTCHA -> CaptchaRequired.
                _handle_checkpoint(page, hooks, headless, display)
            if not ON_LOGIN.search(page.url):
                return  # persisted session (or checkpoint passed): LinkedIn redirected us to the feed
            hooks.progress("Connexion à LinkedIn…")
            user = page.locator(USER_INPUT).filter(visible=True)
            pwd = page.locator(PASSWORD_INPUT).filter(visible=True)
            try:
                pwd.first.wait_for(state="visible", timeout=15_000)
            except Exception:
                # "Welcome back" screen with a remembered account: switch to the regular form.
                other = page.get_by_text(re.compile(r"(another account|autre compte)", re.I))
                if not other.count():
                    raise ScrapeError(
                        f"Formulaire de connexion LinkedIn introuvable (page « {page.title()} » : {page.url}). "
                        "Relancez avec « Afficher le navigateur » pour voir ce que LinkedIn affiche."
                    )
                other.first.click()
                pwd.first.wait_for(state="visible", timeout=15_000)
            if user.count():  # absent when LinkedIn only asks for the password
                user.first.fill(email)
            pwd.first.fill(password)
            pwd.first.press("Enter")
            try:  # leaves /login for the feed or a checkpoint; stays there on wrong credentials
                page.wait_for_url(lambda u: "/login" not in u and "/uas/" not in u, timeout=20_000)
            except Exception:
                pass
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            _handle_checkpoint(page, hooks, headless, display)
            if ON_LOGIN.search(page.url):
                raise ScrapeError("Connexion refusée : identifiant ou mot de passe LinkedIn invalide.")
        except Exception as e:  # Scrapling swallows page_action errors, keep them
            errors.append(e)
            if debug:
                DEBUG_DIR.mkdir(exist_ok=True)
                try:
                    page.screenshot(path=str(DEBUG_DIR / "login-error.png"))
                except Exception:
                    pass

    session.fetch("https://www.linkedin.com/login", page_action=action, google_search=False)
    if errors:
        if isinstance(errors[0], ScrapeError):
            raise errors[0]
        log.error("LinkedIn login failed")  # browser internals stay in the logs
        raise ScrapeError("Échec de la connexion à LinkedIn. Réessayez, ou cochez « Afficher le navigateur » pour voir ce qui bloque.")


CAPTCHA = "iframe[src*=captcha], #captcha-internal, iframe[title*=captcha i]"
PIN_INPUT = "input[name=pin], input[id*=verification_pin], input[name*=verificationCode]"


def _on_checkpoint(url: str) -> bool:
    return "/checkpoint" in url or "/challenge" in url


def _handle_checkpoint(page, hooks: Hooks, headless: bool, display: captcha.RemoteBrowser | None = None) -> None:
    """Wait until LinkedIn itself lets us out of its checkpoint pages (code, CAPTCHA, app approval).

    With the isolated remote browser, a CAPTCHA is shown to the user over VNC; it is considered solved
    only when LinkedIn leaves the checkpoint, never because the user says so."""
    deadline = time.time() + 300
    notified = remote = False
    try:
        while _on_checkpoint(page.url):
            _check_cancelled(hooks)
            if time.time() > deadline:
                raise ScrapeError("CAPTCHA non résolu dans le temps imparti : relancez l'extraction." if remote
                                  else "Vérification LinkedIn non terminée après 5 minutes.")
            pin = page.locator(PIN_INPUT)
            if pin.count() and pin.first.is_visible():
                if remote:  # the CAPTCHA is done: the code goes through the PasseFiltre form
                    display.stop_vnc()
                    hooks.captcha_closed()
                    remote = False
                code = hooks.ask_code("LinkedIn demande un code de vérification (envoyé par email ou SMS).")
                if not code:
                    raise ScrapeError("Vérification annulée.")
                pin.first.fill(code.strip())
                page.locator("button[type=submit], #email-pin-submit-button, #pin-submit-button").first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
                continue
            if page.locator(CAPTCHA).count():
                if display is not None:
                    if not remote:
                        display.start_vnc()
                        deadline = time.time() + captcha.timeout()
                        hooks.captcha_open(display, deadline)
                        hooks.progress("LinkedIn demande un CAPTCHA : cliquez sur « Résoudre le CAPTCHA » pour le faire vous-même.")
                        remote = True
                elif headless:
                    raise CaptchaRequired(
                        "LinkedIn affiche un captcha. Relancez avec l'option « Afficher le navigateur » pour le résoudre."
                    )
                elif not notified:
                    hooks.progress("Résolvez le captcha dans la fenêtre du navigateur…")
                    notified = True
            elif not notified and not remote:
                hooks.progress("LinkedIn demande une validation : approuvez la connexion dans l'application mobile…")
                notified = True
            page.wait_for_timeout(2000)
        if remote:
            hooks.progress("Vérification acceptée par LinkedIn : reprise de l'extraction…")
    finally:
        if remote:  # solved, expired, cancelled or browser gone: the VNC session ends here
            display.stop_vnc()
            hooks.captcha_closed()


# --------------------------------------------------------------------------- pages

TOP_CARD_JS = """() => {
  const main = document.querySelector('main') || document.body;
  const h1 = main.querySelector('h1');
  const section = (h1 && h1.closest('section')) || main;
  let aboutText = '';
  // New UI: a section titled "About"/"Infos" with an expandable text box. Old UI: an #about anchor.
  const aboutSec = [...main.querySelectorAll('section')].find(
    s => /^(about|infos|à propos)$/i.test((s.innerText || '').trim().split('\\n')[0].trim()));
  const box = aboutSec && aboutSec.querySelector('[data-testid="expandable-text-box"]');
  if (box) {
    aboutText = box.innerText.trim();
  } else if (document.getElementById('about')) {
    const spans = [...document.getElementById('about').closest('section').querySelectorAll('span[aria-hidden="true"]')];
    aboutText = spans.map(s => s.innerText.trim()).sort((a, b) => b.length - a.length)[0] || '';
  }
  return {
    name: h1 ? h1.innerText.trim() : document.title.replace(/^\\(\\d+\\)\\s*/, '').split('|')[0].trim(),
    lines: section.innerText.split('\\n').map(s => s.trim()).filter(Boolean),
    about: aboutText,
  };
}"""

EXPAND_JS = """() => {
  const re = /^(show more results|afficher plus de résultats|voir plus de résultats|afficher plus|show more)$/i;
  const btn = [...document.querySelectorAll('main button')].find(b => re.test(b.innerText.trim()));
  if (btn) { btn.click(); return true; }
  return false;
}"""

# Lists are lazy-loaded while scrolling (and the scroller may be an inner element, not the window):
# bring the last item into view until the number of items stops growing.
SCROLL_JS = """() => {
  const items = document.querySelectorAll('main [componentkey^="entity-collection-item"], main li');
  if (items.length) items[items.length - 1].scrollIntoView({block: 'end'});
  window.scrollBy(0, 2500);
  return items.length;
}"""

PRONOUNS = re.compile(r"^(he|she|they|il|elle|iel)/", re.I)
CONTACT = re.compile(r"^(contact info|coordonnées)$", re.I)


# Truncated texts ("… plus" / "…see more"): click every toggle so the full text is in the DOM.
EXPAND_TEXT_JS = """() => {
  const re = /^(…|\\.\\.\\.)?\\s*(plus|voir plus|afficher plus|see more|more)$/i;
  let clicked = 0;
  document.querySelectorAll(
    'main [data-testid="expandable-text-button"], main .inline-show-more-text__button, main button, main [role="button"]'
  ).forEach(b => {
    const isToggle = b.matches('[data-testid="expandable-text-button"], .inline-show-more-text__button')
      || re.test((b.innerText || '').trim());
    if (isToggle && b.getAttribute('aria-expanded') !== 'true' && !b.dataset.pfClicked) {
      b.dataset.pfClicked = '1';
      b.click();
      clicked++;
    }
  });
  return clicked;
}"""


def _expand_texts(page) -> None:
    for _ in range(3):  # new toggles can appear once a section is expanded
        if not page.evaluate(EXPAND_TEXT_JS):
            break
        page.wait_for_timeout(600)


def _scroll_and_expand(page) -> None:
    last, stable = -1, 0
    for _ in range(60):
        count = page.evaluate(SCROLL_JS)
        page.wait_for_timeout(700)
        if page.evaluate(EXPAND_JS):
            page.wait_for_timeout(1200)
            stable = 0
            continue
        stable = stable + 1 if count == last else 0
        last = count
        if stable >= 3:
            break
    _expand_texts(page)


def _light_page(page) -> None:
    """page_setup for the pages we only read: skip heavy resources. Not used on login/CAPTCHA pages."""
    page.route("**/*", lambda route: route.abort() if route.request.resource_type in HEAVY_RESOURCES
               else route.continue_())


def _profile_action(top: dict):
    """Profile page: read the top card, then load the lazy sections (About…) and expand their texts."""
    def action(page) -> None:
        top.update(page.evaluate(TOP_CARD_JS))
        for _ in range(6):
            page.evaluate("() => window.scrollBy(0, 1500)")
            page.wait_for_timeout(500)
        _expand_texts(page)
    return action


def _parse_top_card(data: dict, url: str) -> Basics:
    name = data.get("name", "")
    lines = [l for l in data.get("lines", []) if l not in ("·", "•")]
    basics = Basics(full_name=name, linkedin_url=url, summary=data.get("about", ""))
    if name in lines:
        after = [l for l in lines[lines.index(name) + 1:] if not PRONOUNS.match(l) and not l.startswith("·")]
        basics.headline = after[0] if after else ""
    contact_idx = next((i for i, l in enumerate(lines) if CONTACT.match(l)), None)
    if contact_idx:
        candidate = lines[contact_idx - 1]
        if candidate not in (name, basics.headline):
            basics.location = candidate
    return basics


def _parse_about(page: Selector) -> str:
    """About text from the final HTML (the section is lazy-loaded, often after TOP_CARD_JS ran)."""
    for sec in page.xpath("//main//section"):
        head = str(sec.get_all_text(separator="\n", strip=True)).split("\n", 1)[0].strip()
        if re.fullmatch(r"(about|infos|à propos)", head, re.I):
            box = sec.css('[data-testid="expandable-text-box"]')
            return _text(box[0]) if box else ""
    return ""


def _parse_contact(page: Selector, basics: Basics) -> None:
    # The overlay is a dialog outside <main> (role=dialog before, data-testid=dialog-content now);
    # pick the one that links to the profile, not the ad dialogs.
    dialogs = [d for d in page.css('[role=dialog], [data-testid="dialog-content"]')
               if any("/in/" in h or h.startswith("mailto:") for h in d.css("a::attr(href)").getall())]
    scope = dialogs[0] if dialogs else page
    basics.email = next((h[7:] for h in scope.css("a::attr(href)").getall() if h.startswith("mailto:")), "")
    basics.websites = [
        h for h in scope.css("a::attr(href)").getall()
        if h.startswith("http") and "linkedin.com" not in h
    ]
    text = str(scope.get_all_text(separator="\n", strip=True))
    phone = re.search(r"(?:Phone|Téléphone)\s*\n\s*(\+?[\d(][\d ().-]{5,}\d)", text)  # stays on one line
    if phone:
        basics.phone = phone.group(1).strip()


# New LinkedIn UI ("SDUI"): one block per entry, one <p> per text line, grouped roles as nested <li>.
# Paragraphs inside external links are attachments (Instagram post, PDF…), not entry text.
SDUI_ITEMS = '//main//*[starts-with(@componentkey, "entity-collection-item")]'
SDUI_LINES = ('.//p[count(ancestor::li)={depth}]'
              '[not(ancestor::a[starts-with(@href, "http") and not(contains(@href, "linkedin.com"))])]')


def _entries(page: Selector) -> list[Entry]:
    items = page.xpath(SDUI_ITEMS)
    if items:
        out = []
        for it in items:
            children = [Entry(lines=[_text(p) for p in li.xpath(SDUI_LINES.format(depth=1))])
                        for li in it.xpath(".//li[count(ancestor::li)=0]")]
            entry = Entry(lines=[_text(p) for p in it.xpath(SDUI_LINES.format(depth=0))],
                          links=it.css("a::attr(href)").getall(),
                          children=[c for c in children if any(c.lines)])
            if any(entry.lines):
                out.append(entry)
        return out

    # Previous UI: <li> items with visible text duplicated in span[aria-hidden=true].
    out = []
    for li in page.xpath("//main//ul/li[not(ancestor::li)]"):
        lines = [_text(s) for s in li.xpath('.//span[@aria-hidden="true"][count(ancestor::li)=1]')]
        if not any(lines):
            continue
        children = [
            Entry(lines=[_text(s) for s in c.xpath('.//span[@aria-hidden="true"][count(ancestor::li)=2]')])
            for c in li.xpath("./descendant::li[count(ancestor::li)=1]")
        ]
        out.append(Entry(lines=lines, links=li.css("a::attr(href)").getall(), children=children))
    return out


def _empty_section(page: Selector) -> bool:
    main = page.css("main")  # css() returns a list of matches
    text = str(main[0].get_all_text(separator=" ")) if main else ""
    return bool(re.search(r"(nothing to see for now|rien à voir pour le moment|n'a pas encore ajouté)", text, re.I))


# --------------------------------------------------------------------------- entry point

def scrape_profile(url: str, email: str, password: str, hooks: Hooks,
                   headless: bool = True, debug: bool = False, remote_captcha: bool = False) -> Profile:
    """remote_captcha: if a CAPTCHA blocks the headless login, log in again in the isolated captcha-browser
    (the user solves the CAPTCHA through the viewer), then resume headless with LinkedIn's cookies only."""
    base = normalize_profile_url(url)
    user_data_dir = _session_dir(email, password)
    with _account_in_use(user_data_dir):
        try:
            return _scrape(base, email, password, hooks, user_data_dir, headless, debug)
        except CaptchaRequired:
            if not (headless and remote_captcha):
                raise
        _check_cancelled(hooks)
        hooks.progress("LinkedIn demande un CAPTCHA : ouverture d'un navigateur isolé…")
        cookies = _remote_login(email, password, hooks, debug)
        _check_cancelled(hooks)
        try:
            return _scrape(base, email, password, hooks, user_data_dir, True, debug, cookies)
        except CaptchaRequired:
            raise ScrapeError("LinkedIn redemande une vérification juste après le CAPTCHA : réessayez dans quelques minutes.") from None


def _remote_login(email: str, password: str, hooks: Hooks, debug: bool) -> list[dict]:
    """Log in on the isolated captcha-browser (fresh profile, no secrets, no other account, no LAN), keep
    that same browser open while the user solves the CAPTCHA, then bring back LinkedIn's cookies only."""
    with captcha.RemoteBrowser() as remote, StealthySession(
        cdp_url=remote.cdp_url,
        locale="en-US",
        timeout=TIMEOUT_MS,
        retries=1,
        google_search=False,
        additional_args=remote.context_options(),
    ) as session:
        _login(session, email, password, hooks, False, debug, remote)
        return _linkedin_cookies(session.context.cookies())


COOKIE_FIELDS = ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")


def _linkedin_cookies(cookies: list[dict]) -> list[dict]:
    """What the isolated browser may hand back to the API's profile: LinkedIn cookies, bounded, known fields."""
    kept = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lstrip(".").lower()
        if (domain == "linkedin.com" or domain.endswith(".linkedin.com")) and len(str(cookie.get("value", ""))) <= 4096:
            kept.append({k: cookie[k] for k in COOKIE_FIELDS if k in cookie})
    if not any(c.get("name") == "li_at" for c in kept):  # LinkedIn's session cookie
        raise ScrapeError("La session LinkedIn n'a pas pu être récupérée après le CAPTCHA : réessayez.")
    return kept[:200]


def _scrape(base: str, email: str, password: str, hooks: Hooks, user_data_dir: str, headless: bool, debug: bool,
            cookies: list[dict] | None = None, save_cookies=None) -> Profile:
    with StealthySession(
        headless=headless,
        user_data_dir=user_data_dir,
        locale="en-US",  # stable UI labels/date formats for the parsers
        timeout=TIMEOUT_MS,
        retries=1,
        google_search=False,
        cookies=cookies or [],
    ) as session:
        _login(session, email, password, hooks, headless, debug)
        _check_cancelled(hooks)
        hooks.progress("Lecture du profil…", 10)

        top: dict = {}
        profile_page = session.fetch(base, page_action=_profile_action(top), page_setup=_light_page, wait=1000)
        if "/in/" not in str(profile_page.url) and "authwall" in str(profile_page.url):
            raise ScrapeError("Session LinkedIn invalide : reconnexion nécessaire.")
        basics = _parse_top_card(top, base)
        basics.summary = basics.summary or _parse_about(profile_page)
        if not basics.full_name:
            raise ScrapeError("Profil introuvable ou inaccessible (vérifiez l'URL).")

        hooks.progress("Lecture des coordonnées…", 15)
        contact = session.fetch(base + "overlay/contact-info/", page_setup=_light_page, wait=1500)
        try:
            _parse_contact(contact, basics)
        except Exception:
            log.error("Contact info parsing failed")
            hooks.progress("Coordonnées non lues : à compléter à la main.")
        profile = Profile(basics=basics)
        if debug:
            _dump("profile", profile_page)
            _dump("contact", contact)

        for i, (attr, slug) in enumerate(SECTIONS.items()):
            _check_cancelled(hooks)
            hooks.progress(f"Section « {attr} »…", 20 + int(75 * i / len(SECTIONS)))
            page = session.fetch(f"{base}details/{slug}/", page_action=_scroll_and_expand, page_setup=_light_page, wait=500)
            if debug:
                _dump(attr, page)
            try:  # one broken section must not kill the whole scrape
                if not _empty_section(page):
                    setattr(profile, attr, PARSERS[attr](_entries(page)))
            except Exception:
                log.error("Parsing failed for %s", attr)
                hooks.progress(f"Section « {attr} » ignorée (lecture impossible).")
            time.sleep(1)  # be gentle with LinkedIn
        hooks.progress("Extraction terminée.", 100)
        if save_cookies is not None:
            save_cookies(_linkedin_cookies(session.context.cookies()))
        return profile


def _dump(name: str, page: Selector) -> None:
    DEBUG_DIR.mkdir(exist_ok=True)
    (DEBUG_DIR / f"{name}.html").write_text(page.html_content, encoding="utf-8")
