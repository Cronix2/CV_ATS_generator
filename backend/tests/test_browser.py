"""Chromium install consistency: the image must ship the browser that StealthySession actually launches."""

import re
from pathlib import Path

from app.scraper import browser_check

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_stealthy_session_drives_chromium_through_patchright():
    # If a future Scrapling switches StealthySession to another driver, the Dockerfile install must follow.
    from scrapling.engines._browsers import _stealth

    assert _stealth.sync_playwright.__module__.startswith("patchright.")


def test_image_installs_chromium_with_patchright_cli():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "python -m patchright install --with-deps chromium" in dockerfile
    # `playwright install` would fetch Playwright's own revision, which patchright does not look for.
    assert not re.search(r"(?<!patch)playwright install", dockerfile)
    assert "app.scraper.browser_check --static" in dockerfile


def test_browser_check_fails_when_expected_chromium_is_missing(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "chromium-1243" / "chrome-linux-arm64" / "chrome"
    monkeypatch.setattr(browser_check, "expected_executable", lambda: str(missing))
    assert browser_check.main(["--static"]) == 1
    err = capsys.readouterr().err
    assert "patchright install" in err


def test_browser_check_static_succeeds_when_executable_exists(monkeypatch, tmp_path):
    exe = tmp_path / "chrome"
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setattr(browser_check, "expected_executable", lambda: str(exe))
    monkeypatch.setattr(browser_check, "launch_check", lambda: (_ for _ in ()).throw(AssertionError("no launch")))
    assert browser_check.main(["--static"]) == 0


def test_browser_check_reports_launch_failure(monkeypatch, tmp_path, capsys):
    exe = tmp_path / "chrome"
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setattr(browser_check, "expected_executable", lambda: str(exe))

    def boom():
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(browser_check, "launch_check", boom)
    assert browser_check.main([]) == 1
    assert "did not start" in capsys.readouterr().err
