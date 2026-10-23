from app.models import CV, Certification, Experience, Profile, Skill
from app.v1 import business
from app.v1.grounding import agent_proposal, suggestions


def test_invented_skills_qualifications_and_item_ids_are_rejected():
    source = CV(
        profile=Profile(
            experience=[Experience(id="e", title="Engineer", company="Original")],
            skills=[Skill(name="Python")],
        )
    )
    out, meta = suggestions(
        source,
        {
            "skills": {"skills": ["Python", "CISSP"], "missing_keywords": ["CISSP"]},
            "experience": {"items": [{"id": "invented", "description": "CEO"}]},
            "cleanup": {
                "experience": [{"id": "e", "company": "Invented", "title": "CEO"}]
            },
        },
    )
    assert out["skills"]["skills"] == ["Python"]
    assert out["experience"]["items"] == [] and out["cleanup"]["experience"] == []
    assert meta["requires_human_review"] and not meta["prose_verified"]
    assert meta["rejected_fields"]


def test_hostile_agent_cannot_change_authoritative_facts():
    source = CV(
        profile=Profile(
            experience=[Experience(id="e", title="Engineer", company="Original")]
        )
    )
    invented = source.model_copy(deep=True)
    invented.profile.experience[0].company = "Invented"
    invented.profile.experience[0].description = "Won 99 awards"
    invented.profile.certifications = [Certification(name="Invented credential")]
    out = agent_proposal(
        source, dict(cv=invented.model_dump(), reply="Untrusted reply")
    )
    assert out["cv"]["profile"]["experience"][0]["company"] == "Original"
    assert out["cv"]["profile"]["experience"][0]["description"] == ""
    assert out["cv"]["profile"]["certifications"] == []
    assert out["proposed_text"][0]["source_ref"] == "profile.experience.e.description"
    assert out["requires_human_review"]


def test_review_usage_is_unknown_without_provider_usage(monkeypatch):
    from app.v1.auth import Actor

    monkeypatch.setenv("LLM_API_KEY", "never-return-this-key")
    monkeypatch.setattr(
        business.operations,
        "enhance",
        lambda *a, **k: {"skills": {"skills": ["Python"]}},
    )
    result = business.review(
        {"cv": {"profile": {"skills": [{"name": "Python"}]}}},
        Actor("t", "u", "key", frozenset()),
    )
    assert result["usage"]["input_tokens"] is None and not result["usage"]["known"]
    assert "never-return-this-key" not in str(result)
