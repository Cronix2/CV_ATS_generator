import base64
import hashlib
import json
import time
from uuid import uuid4
from sqlalchemy import text
from app.v1 import worker, tasks, store
from app.v1.db import transaction, check, sql
from app.v1.crypto import digest, seal, unseal

CV={'profile':{'basics':{'full_name':'Jane Example'},'skills':[{'id':'python','name':'Python'}]}}


def post(client,path,body,key=None):
    return client.post(path,json=body,headers={'Idempotency-Key':key or str(uuid4())})


def run(client,job):
    worker.run(job['id'],client.actor.tenant,client.actor.user)
    response=client.get('/jobs/'+job['id'])
    assert response.status_code==200,response.text
    return response.json()


def test_authentication_is_required_even_on_local_network(clients):
    a=clients[0]
    assert a.get('/health').status_code==200
    assert a.get('/cvs',headers={'Authorization':''}).status_code==401
    assert a.get('/cvs',headers={'X-PasseFiltre-User-Id':''}).status_code==422
    assert clients[3].post('/cvs',json={'cv':CV}).status_code==403


def test_crud_isolation_and_rls(clients):
    a,b,c,_=clients
    check()
    created=post(a,'/cvs',{'cv':CV})
    assert created.status_code==201,created.text
    ident=created.json()['id']
    for other in (b,c):
        assert other.get('/cvs/'+ident).status_code==404
        assert other.delete('/cvs/'+ident).status_code==404
        assert other.get('/cvs').json()['items']==[]
        with transaction(other.actor) as conn:
            assert sql(conn,'SELECT count(*) FROM pf_records WHERE id=:id',id=ident).scalar()==0
    with transaction() as conn:
        assert sql(conn,'SELECT count(*) FROM pf_records').scalar()==0
    assert a.put('/cvs/'+ident,json={'cv':CV}).status_code==428
    assert a.put('/cvs/'+ident,json={'cv':CV},headers={'If-Match':'99'}).status_code==412
    assert a.put('/cvs/'+ident,json={'cv':CV},headers={'If-Match':'1'}).status_code==200
    assert len(a.get('/cvs/'+ident+'/versions').json())==2
    assert a.delete('/cvs/'+ident).status_code==204
    assert a.get('/cvs/'+ident).status_code==404


def test_idempotency_is_scoped_and_conflicts(clients):
    a,b,*_=clients
    key=str(uuid4())
    one=post(a,'/cvs',{'cv':CV},key)
    two=post(a,'/cvs',{'cv':CV},key)
    assert one.status_code==two.status_code==201,one.text
    assert one.json()['id']==two.json()['id']
    assert post(a,'/cvs',{'cv':{'profile':{}}},key).status_code==409
    assert post(b,'/cvs',{'cv':CV},key).json()['id']!=one.json()['id']


def test_render_contract_and_determinism(clients):
    a=clients[0]
    for fmt in ('pdf','docx'):
        one=post(a,'/render',{'cv':CV,'format':fmt})
        two=post(a,'/render',{'cv':CV,'format':fmt})
        assert one.status_code==200,one.text
        assert one.content==two.content
        assert one.headers['X-Content-SHA256']==hashlib.sha256(one.content).hexdigest()


def test_validation_never_echoes_secrets(clients):
    response=post(clients[0],'/linkedin/extractions',{'password':'TOP-SECRET','unknown':'EMAIL@example.test'})
    assert response.status_code==422
    assert 'TOP-SECRET' not in response.text and 'EMAIL' not in response.text


def test_export_job_and_cancellation(clients):
    a,b,*_=clients
    response=post(a,'/exports',{'cv':CV,'format':'pdf'})
    assert response.status_code==202,response.text
    queued=response.json()
    assert b.get('/jobs/'+queued['id']).status_code==404
    done=run(a,queued)
    assert done['status']=='succeeded',done
    ident=done['result']['resource_id']
    assert a.get('/exports/'+ident+'/download').content.startswith(b'%PDF')
    assert b.get('/exports/'+ident+'/download').status_code==404
    queued=post(a,'/exports',{'cv':CV}).json()
    assert a.delete('/jobs/'+queued['id']).status_code==200
    assert run(a,queued)['status']=='cancelled'


def test_workflow_approval_and_invalidation(clients):
    a=clients[0]
    q=post(a,'/workflows',{'cv':CV,'offer':{'text':'Python Engineer','title':'Engineer'},'use_ai':False})
    assert q.status_code==202,q.text
    done=run(a,q.json())
    assert done['status']=='succeeded',done
    ident=done['result']['resource_id']
    wf=a.get('/workflows/'+ident).json()
    assert wf['data']['status']=='awaiting_review'
    assert wf['data']['draft']['profile']==wf['data']['source']['profile']
    approval={'version':wf['version'],'digest':wf['data']['digest'],'confirmed':True}
    bad={**approval,'digest':'0'*64}
    assert post(a,f'/workflows/{ident}/approve',bad).status_code==409
    response=post(a,f'/workflows/{ident}/approve',approval)
    assert response.status_code==200,response.text
    rendered=run(a,response.json()['jobs'][0])
    assert rendered['status']=='succeeded',rendered
    export_id=rendered['result']['resource_id']
    assert a.get(f'/exports/{export_id}/download').status_code==200
    wf=a.get('/workflows/'+ident).json()
    assert a.put(f'/workflows/{ident}/draft',json={'cv':CV},headers={'If-Match':str(wf['version'])}).status_code==200
    assert a.get(f'/exports/{export_id}/download').status_code==409


def test_revocation_stops_queued_work(clients,db_env):
    a=clients[0]
    q=post(a,'/exports',{'cv':CV}).json()
    with db_env.begin() as conn:
        conn.execute(text('UPDATE pf_keys SET revoked=true WHERE id=:id'),dict(id=a.actor.key_id))
    worker.run(q['id'],a.actor.tenant,a.actor.user)
    assert a.get('/jobs/'+q['id']).status_code==401
    with transaction(a.actor) as conn:
        assert store.get(conn,'job',q['id'])['data']['status']=='failed'


def test_crypto_context_binding_and_no_plaintext_credentials(clients):
    a=clients[0]
    response=post(a,'/linkedin/extractions',dict(profile_url='https://linkedin.com/in/example',email='private@example.test',password='TOP-SECRET'))
    assert response.status_code==202,response.text
    with transaction(a.actor) as conn:
        d=store.get(conn,'job',response.json()['id'])['data']
        assert 'TOP-SECRET' not in json.dumps(d) and 'private@example.test' not in json.dumps(d)
        assert unseal(d['secret'],response.json()['id'])['password']=='TOP-SECRET'
    import pytest
    with pytest.raises(Exception):
        unseal(seal({'secret':'x'},'owner-a'),'owner-b')


def test_at_most_one_result_for_duplicate_delivery(clients):
    a=clients[0]
    q=post(a,'/exports',{'cv':CV}).json()
    one=run(a,q)
    two=run(a,q)
    assert one['result']==two['result']
    with transaction(a.actor) as conn:
        assert len(store.listing(conn,'export'))==1


def test_quota_and_pagination(clients):
    a=clients[0]
    for _ in range(3):
        assert post(a,'/cvs',{'cv':CV}).status_code==201
    page=a.get('/cvs?limit=2').json()
    assert len(page['items'])==2 and page['next_cursor']
    assert len(a.get('/cvs',params={'cursor':page['next_cursor']}).json()['items'])==1
    with transaction(a.actor) as conn:
        store.counter(conn,['heavy',a.actor.tenant,a.actor.user],1,86400)
        # Set to the configured hard limit without invoking providers.
        sql(conn,'UPDATE pf_counters SET count=20 WHERE id=:id',id=digest(['heavy',a.actor.tenant,a.actor.user]))
    response=post(a,'/exports',{'cv':CV})
    assert response.status_code==429 and response.headers['Retry-After']
