"""Durable jobs, outbox, scoped cancellation and worker hooks."""
import time
from uuid import uuid4
from app.v1 import store
from app.v1.db import transaction, sql
from app.v1.crypto import seal, unseal, canonical
from app.v1.errors import APIError
from app.v1.auth import still_authorized

TERMINAL = {'succeeded','failed','cancelled','expired'}
SCOPES = {'scrape':'linkedin:write','offer_import':'offers:write','enhance':'ai:run',
          'agent':'ai:run','export':'exports:write','workflow':'workflows:write'}


def enqueue(conn, actor, kind, payload, secrets=None):
    store.counter(conn, ['heavy',actor.tenant,actor.user], 20, 86400)
    ident = str(uuid4())
    data = dict(status='queued', kind=kind, payload=payload, key_id=actor.key_id, attempt=0,
        percent=0, messages=[], error=None, result=None, cancel=False, lease=None, heartbeat=None,
        secret=seal(secrets, ident) if secrets else None, secret_expires=time.time()+1800 if secrets else None)
    result = store.create(conn, actor, 'job', data, 86400, ident)
    sql(conn, 'INSERT INTO pf_outbox(job_id,tenant,owner_id,queue) VALUES(:id,:tenant,:user,:queue)',
        id=ident,tenant=actor.tenant,user=actor.user,queue='browser' if kind=='scrape' else 'default')
    store.audit(conn, actor, 'job.created', ident)
    return view(result)


def view(row):
    d = row['data']
    return dict(id=row['id'],status=d['status'],percent=d['percent'],messages=d['messages'][-20:],
        error=d.get('error'),result=d.get('result'),attempt=d['attempt'],expires_at=str(row['expires_at']),
        captcha_expires_in=max(0,int(d.get('captcha_deadline',0)-time.time())) if d['status']=='needs_captcha' else None)


def cancel(conn, actor, ident):
    row = store.get(conn, 'job', ident, lock=True)
    d = row['data']
    if d['status'] not in TERMINAL:
        d.update(cancel=True,status='cancelled',result=None,secret=None,code=None,ticket=None)
        store.update(conn,'job',ident,d)
        store.audit(conn,actor,'job.cancelled',str(ident))
    return view(store.get(conn,'job',ident))


class Hooks:
    def __init__(self, actor, ident, lease):
        self.actor,self.ident,self.lease = actor,ident,lease

    def change(self, mutate):
        with transaction(self.actor) as conn:
            row = store.get(conn,'job',self.ident,lock=True)
            d=row['data']
            still_authorized(conn,self.actor,SCOPES[d['kind']])
            if d['lease'] != self.lease or d['cancel'] or d['status'] in TERMINAL:
                raise APIError(409,'cancelled','Tâche interrompue.')
            mutate(d)
            store.update(conn,'job',self.ident,d)

    def progress(self, message, percent=None):
        def apply(d):
            d['messages'] = (d['messages'] + [message[:500]])[-20:]
            if percent is not None:
                d['percent'] = max(0,min(100,percent))
        self.change(apply)

    def cancelled(self):
        try:
            self.change(lambda d: None)
            return False
        except Exception:
            return True  # fail closed on lost database/authorization

    def ask_code(self, message):
        self.change(lambda d: d.update(status='needs_code',code=None))
        deadline=time.monotonic()+300
        while time.monotonic()<deadline and not self.cancelled():
            with transaction(self.actor) as conn:
                row=store.get(conn,'job',self.ident,lock=True)
                code=row['data'].get('code')
                if code:
                    row['data'].update(code=None,status='running')
                    store.update(conn,'job',self.ident,row['data'])
                    return unseal(code,self.ident)
            time.sleep(.5)
        return None

    def captcha_open(self, display, deadline):
        self.change(lambda d: d.update(status='needs_captcha',captcha_socket=display.vnc_socket,
                                      captcha_deadline=deadline,ticket=None))

    def captcha_closed(self):
        try:
            self.change(lambda d: d.update(status='running',captcha_socket=None,ticket=None))
        except APIError:
            pass
