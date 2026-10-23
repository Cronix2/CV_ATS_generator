"""v1 uses encrypted cookie snapshots; browser profiles exist only in private temporary storage."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from app.scraper import linkedin, captcha
from app.v1.crypto import digest, unseal
from app.v1.db import transaction, sql
from app.v1 import store
from app.v1.errors import APIError


def extract(payload, actor, hooks, credentials):
    sid=payload.get('session_id')
    cookies=[]
    # Keep a session-level transaction lock across extraction, including human challenges.
    with transaction(actor) as conn:
        lock=int(digest(sid or [actor.tenant,actor.user,(credentials or {}).get('email','').strip().lower()])[:15],16)
        if not sql(conn,'SELECT pg_try_advisory_xact_lock(:lock)',lock=lock).scalar():
            raise APIError(409,'session_busy','Session déjà utilisée.')
        if sid:
            row=store.get(conn,'linkedin_session',sid)
            cookies=unseal(row['data']['cookies'],sid)
        email=(credentials or {}).get('email','')
        password=(credentials or {}).get('password','')
        saved=[]
        root=os.getenv('V1_BROWSER_TMP','/tmp')
        with TemporaryDirectory(prefix='pf-v1-',dir=root) as tmp:
            os.chmod(tmp,0o700)
            try:
                profile=linkedin._scrape(payload['profile_url'],email,password,hooks,tmp,True,False,cookies,save_cookies=saved.extend)
            except linkedin.CaptchaRequired:
                if not captcha.available() or not credentials:
                    raise APIError(409,'reauthentication_required','Reconnectez la session LinkedIn.') from None
                cookies=linkedin._remote_login(email,password,hooks,False)
                profile=linkedin._scrape(payload['profile_url'],email,password,hooks,tmp,True,False,cookies,save_cookies=saved.extend)
        if hooks.cancelled():
            raise APIError(409,'cancelled','Tâche annulée.')
        # The worker commits session material together with the successful job, under its lease.
        return dict(profile=profile.model_dump(),session_id=sid,session_cookies=saved)
