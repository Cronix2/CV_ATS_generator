"""Isolation of the human-driven CAPTCHA browser: compose topology, egress proxy rules, session host."""

import asyncio
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from app.scraper import browser_host, egress

ROOT = Path(__file__).resolve().parents[2]


class ComposeLoader(yaml.SafeLoader):
    pass


ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def compose(name: str) -> dict:
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=ComposeLoader)


# --- Topologie Docker ---------------------------------------------------------------------------------

def test_captcha_browser_has_no_secrets_no_sessions_and_no_route_out():
    services, networks = compose("docker-compose.yml")["services"], compose("docker-compose.yml")["networks"]
    browser = services["captcha-browser"]
    assert "env_file" not in browser and "ports" not in browser
    assert browser["volumes"] == ["captcha-run:/run/pf-captcha"]
    assert browser["networks"] == ["captcha"]
    assert browser["cap_drop"] == ["ALL"] and "no-new-privileges:true" in browser["security_opt"]
    assert "PASSEFILTRE_TOKEN" not in str(browser.get("environment"))
    assert networks["captcha"]["internal"] is True
    assert networks["captcha"]["driver_opts"]["com.docker.network.bridge.inhibit_ipv4"] == "true"

    proxy = services["captcha-egress"]
    assert "env_file" not in proxy and "ports" not in proxy and "volumes" not in proxy
    assert proxy["cap_drop"] == ["ALL"] and proxy["read_only"] is True

    api = services["api"]
    assert "captcha-run:/run/pf-captcha" in api["volumes"] and "captcha" in api["networks"]
    assert api["environment"]["CAPTCHA_BROWSER_URL"] == "http://captcha-browser:9300"


def test_server_overlay_pins_the_captcha_services_too():
    services = compose("docker-compose.server.yml")["services"]
    for name in ("captcha-browser", "captcha-egress"):
        assert services[name]["build"] is None and "${PASSEFILTRE_IMAGE_TAG:?" in services[name]["image"]


# --- Proxy de sortie --------------------------------------------------------------------------------

@pytest.mark.parametrize("host,ok", [
    ("www.linkedin.com", True), ("linkedin.com", True), ("static.licdn.com", True), ("WWW.LinkedIn.com.", True),
    ("client-api.arkoselabs.com", True), ("www.google.com", True),
    ("evil-linkedin.com", False), ("linkedin.com.evil.com", False), ("google.com", False),
    ("maps.google.com", False), ("127.0.0.1", False), ("::1", False), ("api", False), ("", False),
])
def test_egress_allowlist(host, ok):
    assert egress.host_allowed(host, egress.DEFAULT_DOMAINS) is ok


@pytest.mark.parametrize("address,ok", [
    ("13.107.42.14", True), ("2620:1ec:21::14", True),
    ("10.0.0.1", False), ("172.18.0.2", False), ("192.168.1.63", False), ("127.0.0.1", False),
    ("169.254.169.254", False), ("100.64.0.1", False), ("0.0.0.0", False), ("::1", False),
    ("fd00::1", False), ("fe80::1", False), ("::ffff:192.168.1.1", False), ("224.0.0.1", False), ("nope", False),
])
def test_egress_only_public_addresses(address, ok):
    assert egress.is_public(address) is ok


def test_extra_domains_from_the_environment(monkeypatch):
    monkeypatch.setenv("CAPTCHA_ALLOWED_DOMAINS", " Example.org., ,cdn.test ")
    assert egress.allowed_domains()[-2:] == ("example.org", "cdn.test")


async def _ask(proxy: egress.Egress, request: bytes) -> bytes:
    server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(request)
        await writer.drain()
        answer = await asyncio.wait_for(reader.read(200), 5)
        writer.close()
        return answer
    finally:
        server.close()


def run_proxy(request: bytes, resolved: list[str]) -> tuple[bytes, list[str]]:
    asked: list[str] = []

    async def resolver(host, port):
        asked.append(host)
        return resolved

    return asyncio.run(_ask(egress.Egress(resolver=resolver), request)), asked


@pytest.mark.parametrize("request_line", [
    b"GET http://www.linkedin.com/ HTTP/1.1",            # plain HTTP
    b"CONNECT www.linkedin.com:80 HTTP/1.1",             # other port
    b"CONNECT api:443 HTTP/1.1",                         # internal service
    b"CONNECT 192.168.1.1:443 HTTP/1.1",                 # IP literal
    b"CONNECT example.com:443 HTTP/1.1",                 # not allowlisted
])
def test_egress_refuses_before_any_dns_lookup(request_line):
    answer, asked = run_proxy(request_line + b"\r\nHost: x\r\n\r\n", ["13.107.42.14"])
    assert answer.startswith(b"HTTP/1.1 403") and asked == []


@pytest.mark.parametrize("resolved", [["10.0.0.5"], ["13.107.42.14", "192.168.1.63"], ["169.254.169.254"], []])
def test_egress_refuses_allowlisted_names_resolving_to_private_addresses(resolved):
    """DNS rebinding / poisoned answer: www.linkedin.com -> LAN or metadata address."""
    answer, asked = run_proxy(b"CONNECT www.linkedin.com:443 HTTP/1.1\r\n\r\n", resolved)
    assert answer.startswith(b"HTTP/1.1 403") and asked == ["www.linkedin.com"]


def test_egress_tunnels_to_the_address_it_checked(monkeypatch):
    async def scenario() -> bytes:
        async def echo(reader, writer):
            writer.write(await reader.read(100))
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        monkeypatch.setattr(egress, "is_public", lambda a: a == "127.0.0.1")  # stands for a public address
        connected = []
        real_open = asyncio.open_connection

        async def spy(host, port, **kw):
            connected.append(host)
            return await real_open(host, upstream.sockets[0].getsockname()[1], **kw)

        monkeypatch.setattr(egress.asyncio, "open_connection", spy)

        async def resolver(host, port):
            return ["127.0.0.1"]

        proxy = egress.Egress(resolver=resolver)
        server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)
        try:
            reader, writer = await real_open("127.0.0.1", server.sockets[0].getsockname()[1])
            writer.write(b"CONNECT www.linkedin.com:443 HTTP/1.1\r\n\r\nhello")
            await writer.drain()
            data = b""
            while b"hello" not in data:
                chunk = await asyncio.wait_for(reader.read(100), 5)
                if not chunk:
                    break
                data += chunk
            writer.close()
        finally:
            server.close()
            upstream.close()
        assert connected == ["127.0.0.1"]
        return data

    data = asyncio.run(scenario())
    assert data.startswith(b"HTTP/1.1 200") and data.endswith(b"hello")


# --- Hôte des sessions (captcha-browser) -------------------------------------------------------------

class FakeSession:
    instances: list["FakeSession"] = []

    def __init__(self, executable, proxy=None, run_dir=None):
        self.id, self.started, self.closed = "S" * 32, 0.0, False
        FakeSession.instances.append(self)

    def expose(self, port):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def host(monkeypatch):
    FakeSession.instances = []
    monkeypatch.setattr(browser_host, "Session", FakeSession)
    return browser_host.Host("chromium", max_age=60)


def test_one_captcha_session_at_a_time_and_only_by_its_id(host):
    session = host.open()
    with pytest.raises(browser_host.Busy):
        host.open()
    assert host.get("S" * 31 + "T") is None and host.get("..") is None and host.get("é") is None
    assert not host.close("wrong") and not session.closed
    assert host.close(session.id) and session.closed
    host.open()  # the slot is free again


def test_forgotten_sessions_are_reaped(host, monkeypatch):
    session = host.open()
    monkeypatch.setattr(browser_host.time, "monotonic", lambda: session.started + 61)
    host.reap()
    assert session.closed and host.session is None


def test_control_interface(host):
    server = browser_host.ControlServer(("127.0.0.1", 0), host)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, method=method), timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    try:
        status, body = call("POST", "/session")
        assert status == 201 and body == {"id": "S" * 32, "cdp_port": browser_host.CDP_PORT}
        assert call("POST", "/session")[0] == 409
        assert call("DELETE", "/session/" + "X" * 32)[0] == 404
        assert call("GET", "/health") == (200, {"ok": True, "sessions": 1})
        assert call("DELETE", "/session/" + "S" * 32)[0] == 200 and FakeSession.instances[0].closed
    finally:
        server.shutdown()
        server.server_close()


def test_chromium_gets_the_proxy_for_everything_and_a_fresh_profile(tmp_path):
    args = browser_host.chromium_args(tmp_path, "http://captcha-egress:3128")
    assert "--proxy-server=http://captcha-egress:3128" in args and "--proxy-bypass-list=<-loopback>" in args
    assert f"--user-data-dir={tmp_path}" in args and "--remote-debugging-port=0" in args
    assert not any(a.startswith(("--remote-debugging-address", "--enable-automation")) for a in args)
