import hashlib
import secrets
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from fastapi import Depends, WebSocket
from app.security import cors_origins
from app.scraper.captcha import _is_session_socket
from app.services.captcha_bridge import bridge
from app.v1.api import app
from app.v1.auth import Actor, authenticate, still_authorized
from app.v1.db import transaction
from app.v1 import store
from app.v1.errors import APIError


@app.post('/jobs/{ident}/captcha/ticket',tags=['linkedin'])
def ticket(ident: UUID,actor: Actor=Depends(authenticate)):
    actor.require('linkedin:write')
    with transaction(actor) as conn:
        row=store.get(conn,'job',ident,lock=True)
        if row['data']['status']!='needs_captcha' or row['data'].get('captcha_deadline',0)<=time.time():
            raise APIError(409,'no_captcha_expected','Aucun CAPTCHA attendu.')
        token=secrets.token_urlsafe(32)
        row['data'].update(ticket=hashlib.sha256(token.encode()).hexdigest(),ticket_expiry=time.time()+60)
        store.update(conn,'job',ident,row['data'])
    # Encode routing owner inside an opaque encrypted ticket, rather than revealing it in a URL.
    from app.v1.crypto import seal
    opaque=seal(dict(token=token,tenant=actor.tenant,user=actor.user,key_id=actor.key_id),str(ident))
    import base64
    # WebSocket subprotocols cannot contain '/' or '='.
    safe=base64.urlsafe_b64encode(opaque.encode()).decode().rstrip('=')
    return dict(ticket=safe,protocol='pf-ticket.',expires_in=60)


class View:
    def __init__(self,actor,ident,sock):
        self.actor,self.id=actor,str(ident)
        self._display=SimpleNamespace(vnc_socket=sock)
    @property
    def status(self):
        try:
            with transaction(self.actor) as conn:
                still_authorized(conn,self.actor,'linkedin:write')
                d=store.get(conn,'job',self.id)['data']
                return d['status'] if d.get('captcha_deadline',0)>time.time() else 'expired'
        except Exception:
            return 'expired'
    @property
    def display(self):
        return self._display if self.status=='needs_captcha' else None


@app.websocket('/jobs/{ident}/captcha/vnc')
async def viewer(ws: WebSocket,ident: UUID):
    import base64
    from app.v1.crypto import unseal
    import anyio
    def redeem():
        if ws.headers.get('origin') not in cors_origins():
            raise ValueError()
        offered=next((p[10:] for p in ws.scope.get('subprotocols',[]) if p.startswith('pf-ticket.')),'')
        if len(offered)>4096:
            raise ValueError()
        token=unseal(base64.urlsafe_b64decode(offered+'='*(-len(offered)%4)).decode(),str(ident))
        actor=Actor(token['tenant'],token['user'],token['key_id'],frozenset())
        with transaction(actor) as conn:
            still_authorized(conn,actor,'linkedin:write')
            row=store.get(conn,'job',ident,lock=True)
            d=row['data']
            if d['status']!='needs_captcha' or d.get('ticket_expiry',0)<=time.time() or d.get('captcha_deadline',0)<=time.time():
                raise ValueError()
            if not secrets.compare_digest(d.get('ticket') or '',hashlib.sha256(token['token'].encode()).hexdigest()):
                raise ValueError()
            path=Path(d.get('captcha_socket') or '')
            if not _is_session_socket(path):
                raise ValueError()
            d['ticket']=None
            store.update(conn,'job',ident,d)
            return View(actor,ident,str(path))
    try:
        view=await anyio.to_thread.run_sync(redeem)
    except Exception:
        await ws.close(code=1008)
        return
    await bridge(ws,view)
