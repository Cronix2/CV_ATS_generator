import json
from pathlib import Path
from app.models import CV, Profile, Skill, CVSettings, Target
from app.services.ats import analyse, extract_keywords


def test_original_typescript_fixtures():
    for row in json.loads((Path(__file__).parent / 'fixtures/ats-keywords.json').read_text()):
        assert extract_keywords(row['text']) == row['keywords'], row['text']


def test_included_sections_and_null_score():
    cv = CV(profile=Profile(skills=[Skill(name='Python'), Skill(name='SQL', include=False)]),
            settings=CVSettings(target=Target(keywords=['Python', 'SQL'])))
    assert analyse(cv)['percent'] == 50
    cv.settings.sections = []
    assert analyse(cv)['percent'] == 0
    cv.settings.target.keywords = []
    assert analyse(cv)['percent'] is None
