"""v1 orchestration over the shared engines, without transport or database dependencies."""
import os
import json
from langchain_core.callbacks import UsageMetadataCallbackHandler
from app.llm.agents import LLMConfig, AGENTS
from app.services import operations
from app.services.ats import analyse
from app.models import CV
from app.v1.errors import APIError
from app.v1.crypto import digest


def provider(ref, actor):
    configs = json.loads(os.getenv('V1_LLM_PROVIDERS', '{}'))
    cfg = configs.get(ref)
    if cfg is None and ref == 'default':
        cfg = dict(key_env='LLM_API_KEY', base_url_env='LLM_BASE_URL', model_env='LLM_MODEL')
    if cfg is None or (cfg.get('tenants') and actor.tenant not in cfg['tenants']):
        raise APIError(403, 'provider_forbidden', 'Fournisseur non autorisé.')
    key = os.getenv(cfg.get('key_env', 'LLM_API_KEY'), '')
    if not key:
        raise APIError(503, 'provider_unavailable', 'Fournisseur IA non configuré.')
    out = LLMConfig(api_key=key, base_url=os.getenv(cfg.get('base_url_env', 'LLM_BASE_URL'), ''),
                    model=os.getenv(cfg.get('model_env', 'LLM_MODEL'), '') or 'gpt-4o-mini')
    out._resolved = True  # trusted server configuration, never an input field
    return out


def review(body, actor):
    cv = CV.model_validate(body['cv'])
    offer = body.get('offer') or {}
    cfg = provider(body.get('llm', {}).get('provider_ref', 'default'), actor)
    callback = UsageMetadataCallbackHandler()
    suggestions = operations.enhance(cfg, cv, offer.get('text', ''), body.get('agents', list(AGENTS)), callbacks=[callback])
    values = list(callback.usage_metadata.values())
    usage = dict(model=cfg.model, input_tokens=sum(v['input_tokens'] for v in values) if values else None,
                 output_tokens=sum(v['output_tokens'] for v in values) if values else None, known=bool(values))
    return dict(suggestions=suggestions, usage=usage, passefiltre_version='1.0.0',
                notice='Propositions à vérifier humainement ; aucune modification automatique du profil.')


def workflow_draft(body, actor):
    source = CV.model_validate(body['cv'])
    draft = source.model_copy(deep=True)
    offer = body['offer']
    draft.settings.target.title = offer['title']
    draft.settings.target.company = offer['company']
    draft.settings.target.offer_text = offer['text']
    draft.settings.target.offer_url = offer.get('url', '')
    before, after = analyse(source), analyse(draft)
    suggestions = review(body, actor) if body.get('use_ai', True) else None
    # Unverified prose is never promoted to a factual CV. The human can edit the draft explicitly.
    # Targeting/ordering reuses existing facts; new qualifications are never inserted by an LLM.
    return dict(status='awaiting_review', source=source.model_dump(), draft=draft.model_dump(),
                digest=digest(draft.model_dump()), suggestions=suggestions,
                before_ats=before, after_ats=after, approval=None,
                changes=[dict(path='settings.target', before=source.settings.target.model_dump(), after=draft.settings.target.model_dump())])
