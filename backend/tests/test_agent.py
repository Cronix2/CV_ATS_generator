import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.llm.agents import LLMConfig
from app.llm.supervisor import run_agent
from app.llm.tools import Workspace, _is_public_url
from app.models import CV
from app.security import PublicError

import pytest


@pytest.fixture(autouse=True)
def local_llm_allowed(monkeypatch):
    # The fake LLM servers listen on 127.0.0.1: allowed only with ALLOW_LOCAL_LLM=1 (SSRF protection).
    monkeypatch.setenv("ALLOW_LOCAL_LLM", "1")


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


class FakeNoToolsLLM(BaseHTTPRequestHandler):
    """Behaves like vLLM without --enable-auto-tool-choice: any request with tools is rejected."""

    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "tools" in body:
            return self._send(400, {"error": {"message": '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set', "code": "400"}})
        last = body["messages"][-1]["content"]
        if "Résultat de modifier_element" in last:
            content = '{"final": "Fait en mode JSON."}'
        else:
            content = 'Je modifie la description.\n```json\n{"outil": "modifier_element", "arguments": {"section": "experience", "id": "e1", "champs": {"description": "- Audits"}}}\n```'
        self._send(200, {"id": "1", "object": "chat.completion", "created": 0, "model": "x",
                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})


def test_supervisor_falls_back_to_json_actions_without_native_tools():
    server = HTTPServer(("127.0.0.1", 0), FakeNoToolsLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    events = []

    class Hooks:
        def progress(self, message, percent=None):
            events.append(message)

    cfg = LLMConfig(api_key="k", base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", model="no-tools")
    try:
        out = run_agent(cfg, CV.model_validate(CV_DATA), "Adapte mon CV", [], Hooks())
        events_second = len(events)
        run_agent(cfg, CV.model_validate(CV_DATA), "Encore", [], Hooks())  # mode remembered: no failing attempt
    finally:
        server.shutdown()
    assert out["reply"] == "Fait en mode JSON."
    assert out["cv"]["profile"]["experience"][0]["description"] == "- Audits"
    assert any("mode outils par JSON" in e for e in events[:events_second])
    assert not any("mode outils par JSON" in e for e in events[events_second:])


def test_llm_config_falls_back_to_server_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-server")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_MODEL", "model-x")
    assert LLMConfig().resolved().model_dump() == {"api_key": "sk-server", "base_url": "https://llm.example/v1", "model": "model-x"}
    # A key typed in the UI always wins over the server default.
    assert LLMConfig(api_key="sk-ui", model="m").resolved().api_key == "sk-ui"
    monkeypatch.delenv("LLM_API_KEY")
    with pytest.raises(PublicError):
        LLMConfig().resolved()
