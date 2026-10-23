"""Capability-scoped UI adapter. The service credential never reaches the browser."""
import os
import secrets
from uuid import UUID, uuid4
from fastapi import APIRouter, Header, Request, Response
from app.v1.auth import authenticate
from app.v1.crypto import digest
from app.v1.errors import APIError
from app.v1.schemas import WorkflowInput, CVInput, Approval
from app.v1 import api

router=APIRouter(prefix='/api/workflows',tags=['workflow-ui'])


def actor_for(request,capability):
    key=os.getenv('V1_UI_SERVICE_KEY','')
    if not key:
        raise APIError(503,'ui_not_configured','Revue persistante non configurée.')
    if not capability or len(capability)>128:
        raise APIError(404,'not_found','Workflow inconnu.')
    scope=dict(request.scope)
    scope['headers']=[(b'authorization',('Bearer '+key).encode()),
                      (b'x-passefiltre-user-id',('ui-'+digest(capability)).encode())]
    return authenticate(Request(scope))


@router.post('',status_code=202)
def create(body: WorkflowInput,request: Request,response: Response):
    capability=secrets.token_urlsafe(32)
    actor=actor_for(request,capability)
    result=api.workflow_create(body,response,actor,str(uuid4()))
    return {**result,'key':capability}


@router.get('/jobs/{ident}')
def job(ident: UUID,request: Request,x_passefiltre_job_key: str=Header('')):
    return api.job(ident,actor_for(request,x_passefiltre_job_key))


@router.delete('/jobs/{ident}')
def cancel_job(ident: UUID,request: Request,x_passefiltre_job_key: str=Header('')):
    return api.cancel_job(ident,actor_for(request,x_passefiltre_job_key))


@router.get('/exports/{ident}/download')
def download(ident: UUID,request: Request,x_passefiltre_job_key: str=Header('')):
    return api.download(ident,actor_for(request,x_passefiltre_job_key))


@router.get('/{ident}')
def read(ident: UUID,request: Request,response: Response,x_passefiltre_job_key: str=Header('')):
    return api.workflow(ident,response,actor_for(request,x_passefiltre_job_key))


@router.put('/{ident}/draft')
def edit(ident: UUID,body: CVInput,request: Request,response: Response,
         x_passefiltre_job_key: str=Header(''),if_match: str | None=Header(None)):
    return api.workflow_edit(ident,body,response,actor_for(request,x_passefiltre_job_key),if_match)


@router.post('/{ident}/approve')
def approve(ident: UUID,body: Approval,request: Request,x_passefiltre_job_key: str=Header(''),idempotency_key: str=Header(...)):
    return api.approve(ident,body,actor_for(request,x_passefiltre_job_key),idempotency_key)


@router.post('/{ident}/reject')
def reject(ident: UUID,request: Request,x_passefiltre_job_key: str=Header('')):
    return api.reject(ident,actor_for(request,x_passefiltre_job_key))
