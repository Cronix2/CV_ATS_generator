import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.llm.agents import LLMConfig
from app.llm.supervisor import run_agent
from app.llm.tools import Workspace, _is_public_url
from app.models import CV

CV_DATA = {
    "profile": {"basics": {"full_name": "Jane"},
                "experience": [{"id": "e1", "title": "Pentester", "company": "Acme", "description": "tests"}]},
    "settings": {"target": {"title": "Pentester senior", "keywords": ["SIEM"]}},
}


def test_url_guard_blocks_local_and_intranet():
    for url in ("http://localhost:8000", "http://127.0.0.1", "http://192.168.1.1", "https://intranet/x", "file:///c:/x"):
        assert not _is_public_url(url), url


def test_workspace_tools_log_changes_and_report_errors():
    ws = Workspace(CV.model_validate(CV_DATA))
    t = {tool.name: tool for tool in ws.tools()}
    assert t["modifier_element"].invoke({"section": "experience", "id": "e1", "champs": {"description": "- X"}}) == "OK"
    assert t["modifier_element"].invoke({"section": "experience", "id": "nope", "champs": {}}).startswith("Erreur")
    assert t["modifier_element"].invoke({"section": "experience", "id": "e1", "champs": {"foo": 1}}).startswith("Erreur")
    t["definir_competences"].invoke({"noms": ["Python", "python", "SQL"]})
    t["inclure_element"].invoke({"section": "experience", "id": "e1", "inclure": False})
    cv = ws.cv()
    assert cv.profile.experience[0].description == "- X" and not cv.profile.experience[0].include
    assert [s.name for s in cv.profile.skills] == ["Python", "SQL"]
    assert [c["action"] for c in ws.changes] == ["update", "update", "hide"]


class FakeLLM(BaseHTTPRequestHandler):
    """OpenAI-compatible server scripted to call tools, like a real tool-calling model."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tools = [t["function"]["name"] for t in body.get("tools", [])]
        if "ATSReviewOut" in tools:  # the ATS auditor sub-agent
            calls = [("ATSReviewOut", {"score": 71, "strengths": [], "improvements": [], "missing_keywords": ["SIEM"]})]
        elif body["messages"][-1]["role"] == "tool":
            calls = None
        else:
            calls = [("modifier_element", {"section": "experience", "id": "e1", "champs": {"description": "- Audits"}}),
                     ("audit_ats", {})]
        message = {"role": "assistant", "content": None if calls else "Fait."}
        if calls:
            message["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                      "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
        data = json.dumps({"id": "1", "object": "chat.completion", "created": 0, "model": "x",
                           "choices": [{"index": 0, "finish_reason": "stop", "message": message}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def test_supervisor_edits_cv_and_uses_subagent():
    server = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    events = []

    class Hooks:
        def progress(self, message, percent=None):
            events.append(message.split("::")[0])

    try:
        out = run_agent(LLMConfig(api_key="k", base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", model="x"),
                        CV.model_validate(CV_DATA), "Adapte mon CV", [], Hooks())
    finally:
        server.shutdown()
    assert out["reply"] == "Fait."
    assert out["cv"]["profile"]["experience"][0]["description"] == "- Audits"
    assert [c["label"] for c in out["changes"]] == ["Pentester · description"]
    assert events == ["think", "edit", "agent", "done"]
