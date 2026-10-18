from app.scraper.linkedin import _entries, _parse_top_card
from app.scraper.parsers import (
    Entry, is_date_line, normalize_date, parse_certifications, parse_education,
    parse_experience, parse_languages, parse_range, parse_skills,
)
from scrapling.parser import Selector


def test_dates():
    assert normalize_date("Jan 2020") == ("01/2020", False)
    assert normalize_date("janv. 2020") == ("01/2020", False)
    assert normalize_date("Present") == ("", True)
    assert normalize_date("2019") == ("2019", False)
    assert parse_range("Jan 2020 - Present · 4 yrs 2 mos") == ("01/2020", "", True)
    assert parse_range("Sep 2016 – Jun 2018") == ("09/2016", "06/2018", False)
    assert is_date_line("2016 - 2018")
    assert is_date_line("Mar 2021 · 1 mo")
    assert not is_date_line("Paris, Île-de-France, France")
    assert not is_date_line("Built the 2020 roadmap for the data platform and led a team of five.")


def test_single_role():
    exp = parse_experience([Entry(lines=[
        "Data Engineer", "Acme · Full-time", "Jan 2020 - Present · 4 yrs",
        "Paris, Île-de-France, France · Hybrid", "- Built pipelines\n- Cut costs by 30%",
        "Skills: Python · Airflow",
    ])])[0]
    assert (exp.title, exp.company, exp.employment_type) == ("Data Engineer", "Acme", "Full-time")
    assert (exp.start, exp.end, exp.current) == ("01/2020", "", True)
    assert exp.location == "Paris, Île-de-France, France"
    assert exp.description == "- Built pipelines\n- Cut costs by 30%"
    assert exp.skills == ["Python", "Airflow"]


def test_grouped_roles():
    out = parse_experience([Entry(
        lines=["Acme", "Full-time · 5 yrs", "Lyon, France"],
        children=[
            Entry(lines=["Lead Dev", "Jan 2022 - Present · 2 yrs", "Led the team"]),
            Entry(lines=["Developer", "Jan 2019 - Dec 2021 · 3 yrs"]),
        ],
    )])
    assert [e.title for e in out] == ["Lead Dev", "Developer"]
    assert all(e.company == "Acme" and e.employment_type == "Full-time" and e.location == "Lyon, France" for e in out)
    assert out[1].end == "12/2021"


def test_education_certs_skills_languages():
    ed = parse_education([Entry(lines=["EPITA", "Master's degree, Computer Science", "2016 - 2018", "Grade: Honors"])])[0]
    assert (ed.school, ed.degree, ed.field, ed.start, ed.end, ed.grade) == (
        "EPITA", "Master's degree", "Computer Science", "2016", "2018", "Honors")
    c = parse_certifications([Entry(
        lines=["AWS Solutions Architect", "Amazon Web Services (AWS)", "Issued Jan 2023 · Expires Jan 2026", "Credential ID ABC123", "Show credential"],
        links=["https://www.linkedin.com/company/amazon", "https://aws.amazon.com/verify/ABC123"],
    )])[0]
    assert (c.issuer, c.issued, c.expires, c.credential_id, c.url) == (
        "Amazon Web Services (AWS)", "01/2023", "01/2026", "ABC123", "https://aws.amazon.com/verify/ABC123")
    assert [s.name for s in parse_skills([Entry(lines=["Python", "3 endorsements"]), Entry(lines=["python"])])] == ["Python"]
    assert parse_languages([Entry(lines=["English", "Full professional proficiency"])])[0].proficiency == "Full professional proficiency"


def test_entries_from_html():
    html = """<main><section><ul>
      <li><span aria-hidden="true"><!---->Acme<!----></span><span class="visually-hidden">Acme</span>
        <span aria-hidden="true">Full-time · 5 yrs</span>
        <ul><li><span aria-hidden="true">Lead Dev</span><span aria-hidden="true">Jan 2022 - Present · 2 yrs</span>
          <span aria-hidden="true">Line one<br>Line two</span></li></ul></li>
      <li><span aria-hidden="true">Solo role</span><a href="https://x.io">x</a></li>
    </ul></section></main>"""
    entries = _entries(Selector(html))
    assert entries[0].lines == ["Acme", "Full-time · 5 yrs"]
    assert entries[0].children[0].lines[2] == "Line one\nLine two"
    assert entries[1].links == ["https://x.io"]


def test_top_card():
    b = _parse_top_card({
        "name": "Jane Doe",
        "lines": ["Jane Doe", "She/Her", "· 2nd", "Senior Data Engineer at Acme", "Paris, Île-de-France, France", "·", "Contact info", "500+ connections"],
        "about": "Passionate engineer.",
    }, "https://www.linkedin.com/in/jane/")
    assert (b.headline, b.location, b.summary) == ("Senior Data Engineer at Acme", "Paris, Île-de-France, France", "Passionate engineer.")


def test_empty_section_and_contact():
    from app.models import Basics
    from app.scraper.linkedin import _empty_section, _parse_contact

    assert _empty_section(Selector("<main><h2>Projects</h2><p>Nothing to see for now</p></main>"))
    assert not _empty_section(Selector("<main><ul><li><span aria-hidden='true'>Acme</span></li></ul></main>"))
    assert not _empty_section(Selector("<div>no main tag</div>"))

    b = Basics()
    _parse_contact(Selector("""<main><div role="dialog">
      <h3>Website</h3><a href="https://camille.dev">camille.dev</a>
      <h3>Phone</h3><span>+33 6 12 34 56 78</span><span>(Mobile)</span>
      <h3>Email</h3><a href="mailto:camille@example.com">camille@example.com</a>
      <a href="https://www.linkedin.com/in/camille/">profile</a></div></main>"""), b)
    assert (b.email, b.phone, b.websites) == ("camille@example.com", "+33 6 12 34 56 78", ["https://camille.dev"])


SDUI_EXPERIENCE = """<main><section>
  <div componentkey="entity-collection-item-1">
    <a href="https://www.linkedin.com/company/1/"><p>Acme</p><p>Contrat en alternance · 2&#160;ans 2&#160;mois</p></a>
    <p>Lyon, Auvergne-Rhône-Alpes, France · Hybride</p>
    <ul>
      <li><p>Data Engineer</p><p>janv. 2026 - aujourd’hui · 10&#160;mois</p>
        <p><span data-testid="expandable-text-box">Pipelines<br>Dashboards</span></p>
        <p><strong>Compétences&#160;:</strong><span>Python, SQL, +3 compétences</span></p></li>
      <li><p>Stagiaire data</p><p>sept. 2024 - janv. 2026 · 1&#160;an 5&#160;mois</p></li>
    </ul>
  </div>
  <div componentkey="entity-collection-item-2">
    <p>Serveur</p><p>Café · CDI</p><p>juin 2023 - juil. 2023 · 2&#160;mois</p><p>Paris, France · Sur site</p>
    <a href="https://www.instagram.com/cafe/"><p>Café (@cafe) • Instagram photos</p></a>
  </div>
</section></main>"""


def test_sdui_experience():
    from app.scraper.linkedin import _entries
    roles = parse_experience(_entries(Selector(SDUI_EXPERIENCE)))
    assert [(r.title, r.company, r.employment_type) for r in roles] == [
        ("Data Engineer", "Acme", "Contrat en alternance"),
        ("Stagiaire data", "Acme", "Contrat en alternance"),
        ("Serveur", "Café", "CDI"),
    ]
    assert roles[0].location == "Lyon, Auvergne-Rhône-Alpes, France"
    assert (roles[0].start, roles[0].current, roles[1].end) == ("01/2026", True, "01/2026")
    assert roles[0].description == "Pipelines\nDashboards"
    assert roles[0].skills == ["Python", "SQL"]
    assert roles[2].description == ""  # the Instagram attachment is not description text


def test_sdui_about_and_contact():
    from app.models import Basics
    from app.scraper.linkedin import _parse_about, _parse_contact
    page = Selector("""<main><section><h2>Infos</h2>
      <p><span data-testid="expandable-text-box">Ligne 1<br>Ligne 2</span></p></section></main>""")
    assert _parse_about(page) == "Ligne 1\nLigne 2"
    b = Basics()
    _parse_contact(Selector("""<main></main>
      <div data-testid="dialog-content"><p>Pourquoi cette publicité ?</p></div>
      <div data-testid="dialog-content"><a href="https://www.linkedin.com/in/jane/">profil</a>
        <p>E-mail</p><a href="mailto:jane@example.com">jane@example.com</a>
        <a href="https://jane.dev">site</a></div>"""), b)
    assert (b.email, b.websites) == ("jane@example.com", ["https://jane.dev"])


def test_see_more_toggle_is_not_part_of_the_text():
    from app.scraper.linkedin import _text
    box = Selector('<span data-testid="expandable-text-box">Ligne 1<br>Fin du texte.'
                   '<button data-testid="expandable-text-button"><span>… plus</span></button></span>')
    assert _text(box.css("span")[0]) == "Ligne 1\nFin du texte."
    assert _text(Selector("<p>Résumé tronqué…see more</p>").css("p")[0]) == "Résumé tronqué"


def test_light_page_blocks_only_heavy_resources():
    # Regression (Raspberry Pi): images/videos/fonts kept LinkedIn pages from reaching "load" within the timeout.
    from app.scraper.linkedin import _light_page

    class Route:
        def __init__(self, kind):
            self.request = type("Req", (), {"resource_type": kind})()
            self.done = None
        def abort(self):
            self.done = "abort"
        def continue_(self):
            self.done = "continue"

    class Page:
        def route(self, pattern, handler):
            self.handler = handler

    page = Page()
    _light_page(page)
    outcome = {}
    for kind in ("image", "media", "font", "document", "script", "stylesheet", "xhr", "fetch"):
        route = Route(kind)
        page.handler(route)
        outcome[kind] = route.done
    assert {k for k, v in outcome.items() if v == "abort"} == {"image", "media", "font"}
