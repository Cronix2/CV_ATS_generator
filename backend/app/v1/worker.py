"""Celery transport; PostgreSQL owns attempts, leases, results and cancellation."""
import base64
import hashlib
import os
import threading
import time
from contextlib import contextmanager
from uuid import uuid4
from celery import Celery
from app.models import CV
from app.services import operations
from app.services.cv import render
from app.v1 import store, tasks, business
from app.v1.auth import Actor, still_authorized
from app.v1.crypto import unseal, seal, digest
from app.v1.db import transaction, sql, engine
from app.v1.errors import APIError

celery = Celery('passefiltre',broker=os.getenv('V1_REDIS_URL','redis://localhost:6379/0'))
celery.conf.update(task_serializer='json',accept_content=['json'],result_serializer='json',
    task_ignore_result=True,task_acks_late=True,task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,broker_transport_options={'visibility_timeout':1800},
    task_soft_time_limit=1140,task_time_limit=1200,
    beat_schedule={'dispatch':{'task':'pf.dispatch','schedule':5.0},'purge':{'task':'pf.purge','schedule':60.0}},
    task_default_queue='default',worker_hijack_root_logger=False,worker_redirect_stdouts=False)


@contextmanager
def capacity():
    # Session-level locks are released by PostgreSQL even after SIGKILL. No Redis lock expiry race.
    conn=engine().connect()
    slot=None
    try:
        for i in range(max(1,int(os.getenv('V1_MAX_JOBS','2')))):
            if sql(conn,'SELECT pg_try_advisory_lock(734001,:slot)',slot=i).scalar():
                slot=i
                break
        if slot is None:
            raise APIError(429,'busy','Tous les workers sont occupés.',5)
        yield
    finally:
        if slot is not None:
            sql(conn,'SELECT pg_advisory_unlock(734001,:slot)',slot=slot)
        conn.close()


def execute(kind,payload,actor,hooks,secrets_payload):
    if kind=='enhance':
        return business.review(payload,actor)
    if kind=='workflow':
        if payload.get('use_ai',True):
            with transaction(actor) as conn:
                still_authorized(conn,actor,'ai:run')
        return business.workflow_draft(payload,actor)
    if kind=='offer_import':
        return dict(title='',company='',url=payload['url'],text=operations.offer(payload['url']))
    if kind=='export':
        result=render(CV.model_validate(payload['cv']),payload['format'])
        return dict(content=base64.b64encode(result.data).decode(),mime=result.mime,filename=result.filename,
                    sha256=hashlib.sha256(result.data).hexdigest(),workflow_id=payload.get('workflow_id'),
                    approved_digest=payload.get('approved_digest'))
    if kind=='agent':
        return operations.converse(business.provider(payload['llm']['provider_ref'],actor),CV.model_validate(payload['cv']),
                                   payload['instruction'],payload['history'],hooks)
    if kind=='scrape':
        from app.v1.linkedin import extract
        return extract(payload,actor,hooks,secrets_payload)
    raise APIError(422,'invalid_job','Type de tâche inconnu.')


def finish(conn,actor,ident,d,result):
    kind=d['kind']
    if kind in ('workflow','offer_import','export'):
        resource_kind={'workflow':'workflow','offer_import':'offer','export':'export'}[kind]
        if kind=='export' and result.get('workflow_id'):
            wf=store.get(conn,'workflow',result['workflow_id'],lock=True)['data']
            if wf['status']!='approved' or wf['digest']!=result['approved_digest'] or not wf.get('approval'):
                raise APIError(409,'approval_required','Validation périmée.')
        row=store.create(conn,actor,resource_kind,result,604800 if kind=='workflow' else 86400 if kind=='export' else None)
        result=dict(resource_id=row['id'],resource_type=resource_kind)
    elif kind=='scrape':
        sid=result.get('session_id')
        cookies=result.pop('session_cookies')
        if sid:
            store.get(conn,'linkedin_session',sid,lock=True)
            store.update(conn,'linkedin_session',sid,dict(cookies=seal(cookies,sid)))
        else:
            sid=str(uuid4())
            store.create(conn,actor,'linkedin_session',dict(cookies=seal(cookies,sid)),2592000,sid)
        result['session_id']=sid
        profile=store.create(conn,actor,'profile',dict(profile=result.pop('profile')))
        result['profile_id']=profile['id']
    elif kind=='agent':
        row=store.get(conn,'conversation',d['payload']['conversation_id'],lock=True)
        # Store proposals separately; factual CV is not silently replaced by arbitrary agent output.
        row['data']['history']=(row['data']['history']+[
            dict(role='user',content=d['payload']['instruction']),dict(role='assistant',content=result['reply'])])[-20:]
        row['data'].update(active_job=None,last_proposal=result)
        store.update(conn,'conversation',row['id'],row['data'])
    d.update(status='succeeded',percent=100,result=result,secret=None,code=None,ticket=None,captcha_socket=None)
    store.update(conn,'job',ident,d)
    store.audit(conn,actor,'job.succeeded',ident)


@celery.task(name='pf.run')
def run(ident,tenant,user):
    # owner context comes from the transactional outbox; RLS still checks every access.
    actor=Actor(tenant,user,'',frozenset())
    lease=str(uuid4())
    try:
        with capacity():
            with transaction(actor) as conn:
                row=store.get(conn,'job',ident,lock=True)
                d=row['data']
                actor=Actor(tenant,user,d['key_id'],frozenset())
                if d['status']!='queued' or d['cancel']:
                    return
                still_authorized(conn,actor,tasks.SCOPES[d['kind']])
                d.update(status='running',attempt=d['attempt']+1,lease=lease,heartbeat=time.time())
                store.update(conn,'job',ident,d)
            hooks=tasks.Hooks(actor,ident,lease)
            stop=threading.Event()
            def heartbeat():
                while not stop.wait(10):
                    try:
                        hooks.change(lambda data:data.update(heartbeat=time.time()))
                    except Exception:
                        break
            thread=threading.Thread(target=heartbeat,daemon=True)
            thread.start()
            try:
                secret=None
                if d['secret']:
                    if d['secret_expires']<time.time():
                        raise APIError(409,'credentials_expired','Identifiants expirés : créez une nouvelle extraction.')
                    secret=unseal(d['secret'],ident)
                result=execute(d['kind'],d['payload'],actor,hooks,secret)
                with transaction(actor) as conn:
                    current=store.get(conn,'job',ident,lock=True)['data']
                    still_authorized(conn,actor,tasks.SCOPES[d['kind']])
                    if current['lease']==lease and not current['cancel'] and current['status'] not in tasks.TERMINAL:
                        finish(conn,actor,ident,current,result)
            finally:
                stop.set()
                thread.join(timeout=2)
    except APIError as exc:
        if exc.code=='busy':
            return  # outbox will deliver again
        fail(actor,ident,lease,exc.code,exc.message)
    except Exception:
        fail(actor,ident,lease,'processing_failed','Traitement interrompu. Réessayez ou vérifiez les données.')


def fail(actor,ident,lease,code,message):
    try:
        with transaction(actor) as conn:
            d=store.get(conn,'job',ident,lock=True)['data']
            if d['status'] in tasks.TERMINAL or d['lease'] not in (None,lease):
                return
            d.update(status='failed',error=dict(code=code,message=message),secret=None,code=None,ticket=None,captcha_socket=None)
            store.update(conn,'job',ident,d)
            store.audit(conn,actor,'job.failed',ident,outcome=code)
    except Exception:
        pass  # database outage: heartbeat expiry is reconciled by dispatcher


@celery.task(name='pf.dispatch')
def dispatch():
    with transaction() as conn:
        rows=sql(conn,"SELECT * FROM pf_outbox WHERE published_at IS NULL OR published_at<now()-interval '20 seconds' ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED").mappings().all()
        for row in rows:
            actor=Actor(row['tenant'],row['owner_id'],'',frozenset())
            sql(conn,"SELECT set_config('pf.tenant',:tenant,true),set_config('pf.user',:user,true)",tenant=actor.tenant,user=actor.user)
            try:
                job=store.get(conn,'job',row['job_id'],lock=True)
            except APIError:
                sql(conn,'DELETE FROM pf_outbox WHERE job_id=:id',id=row['job_id'])
                continue
            d=job['data']
            if d['status'] in tasks.TERMINAL:
                # Keep failed jobs resumable; terminal outbox entries expire with the job.
                sql(conn,'UPDATE pf_outbox SET published_at=now() WHERE job_id=:id',id=row['job_id'])
                continue
            if d['status']!='queued' and (d.get('heartbeat') or 0)<time.time()-90:
                if d['attempt']>=3:
                    d.update(status='failed',error=dict(code='worker_lost',message='Worker interrompu.'),secret=None)
                else:
                    d.update(status='queued',lease=None,code=None,ticket=None,captcha_socket=None)
                store.update(conn,'job',job['id'],d)
            if d['status']=='queued':
                run.apply_async(args=[job['id'],actor.tenant,actor.user],queue=row['queue'])
            sql(conn,'UPDATE pf_outbox SET published_at=now() WHERE job_id=:id',id=row['job_id'])


@celery.task(name='pf.purge')
def purge():
    with transaction() as conn:
        owners=sql(conn,'SELECT * FROM pf_expired_owners()').all()
        for owner in owners:
            sql(conn,"SELECT set_config('pf.tenant',:tenant,true),set_config('pf.user',:user,true)",tenant=owner.tenant,user=owner.owner_id)
            sql(conn,'DELETE FROM pf_records WHERE expires_at<=now()')
        sql(conn,'DELETE FROM pf_counters WHERE expires_at<=now()')
        sql(conn,"DELETE FROM pf_outbox WHERE created_at<now()-interval '1 day'")
