"""Structural provenance checks. Free prose always requires human review, never proves a fact."""

from copy import deepcopy

from app.models import CV
from app.services.ats import norm


def suggestions(cv: CV, proposed: dict) -> tuple[dict, dict]:
    out = deepcopy(proposed)
    rejected = []
    refs = {}
    source = cv.profile
    experience = {e.id: e for e in source.experience if e.include}
    education = {e.id: e for e in source.education if e.include}
    known_skills = {norm(s.name): s.name for s in source.skills if s.include}
    known_skills.update({norm(s): s for e in experience.values() for s in e.skills})
    if isinstance(out.get("skills"), dict) and "skills" in out["skills"]:
        kept = []
        for skill in out["skills"]["skills"]:
            if norm(skill) in known_skills:
                kept.append(known_skills[norm(skill)])
            else:
                rejected.append("skills")
        out["skills"]["skills"] = list(dict.fromkeys(kept))
    if isinstance(out.get("experience"), dict) and "items" in out["experience"]:
        kept = []
        for item in out["experience"]["items"]:
            if item.get("id") in experience:
                kept.append(item)
                refs["experience." + item["id"]] = "profile.experience." + item["id"]
            else:
                rejected.append("experience")
        out["experience"]["items"] = kept
    if isinstance(out.get("cleanup"), dict):
        for section, originals in (
            ("experience", experience),
            ("education", education),
        ):
            kept = []
            for item in out["cleanup"].get(section, []):
                original = originals.get(item.get("id"))
                if original is None:
                    rejected.append("cleanup." + section)
                    continue
                # Correct swapped fields only using text already present on that same item.
                values = {
                    norm(str(v))
                    for v in original.model_dump().values()
                    if isinstance(v, str)
                }
                if any(
                    norm(v) not in values and v for k, v in item.items() if k != "id"
                ):
                    rejected.append("cleanup." + section)
                    continue
                kept.append(item)
                refs["cleanup." + section + "." + item["id"]] = (
                    "profile." + section + "." + item["id"]
                )
            out["cleanup"][section] = kept
    return out, dict(
        source_refs=refs,
        rejected_fields=sorted(set(rejected)),
        prose_verified=False,
        requires_human_review=True,
    )


def agent_proposal(source: CV, proposed: dict) -> dict:
    """Never make an agent-created qualification part of the authoritative CV."""
    candidate = CV.model_validate(proposed["cv"])
    safe = source.model_copy(deep=True)
    safe.settings.sections = candidate.settings.sections
    safe.settings.language = candidate.settings.language
    text = []
    for field in ("headline", "summary"):
        if getattr(candidate.profile.basics, field) != getattr(
            source.profile.basics, field
        ):
            text.append(
                dict(
                    source_ref="profile.basics." + field,
                    text=getattr(candidate.profile.basics, field),
                )
            )
    changes = []
    for section in type(source.profile).model_fields:
        original = getattr(safe.profile, section)
        if not isinstance(original, list):
            continue
        candidates = {i.id: i for i in getattr(candidate.profile, section)}
        for item in original:
            other = candidates.get(item.id)
            if other is None:
                continue
            if item.include != other.include:
                changes.append(
                    dict(
                        action="show" if other.include else "hide",
                        section=section,
                        label=item.id,
                        before=item.include,
                        after=other.include,
                    )
                )
                item.include = other.include
            if hasattr(item, "description") and item.description != other.description:
                text.append(
                    dict(
                        source_ref=f"profile.{section}.{item.id}.description",
                        text=other.description,
                    )
                )
    return dict(
        cv=safe.model_dump(),
        reply=proposed.get("reply", ""),
        changes=changes,
        proposed_text=text,
        requires_human_review=True,
        prose_verified=False,
    )
