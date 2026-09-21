"""启动策略链与配置发现的单元测试。

重点验证「零硬编码」：所有路径都通过平台惯例 / env / 发现得到。
"""

from __future__ import annotations

import os
from pathlib import Path

from codex_web_login import config, launcher
from codex_web_login.launcher import LaunchResult, launch


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
def test_codex_home_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_CODEX_HOME, str(tmp_path))
    assert config.codex_home() == tmp_path


def test_codex_home_default_is_dot_codex(monkeypatch):
    monkeypatch.delenv(config.ENV_CODEX_HOME, raising=False)
    assert config.codex_home() == Path.home() / ".codex"


def test_proxy_env_sets_both_cases():
    env = config.proxy_env("http://127.0.0.1:9999")
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert env[k] == "http://127.0.0.1:9999"
    assert "localhost" in env["NO_PROXY"]


def test_proxy_env_without_proxy_keeps_no_proxy_only():
    env = config.proxy_env(None)
    assert "HTTP_PROXY" not in env or env.get("HTTP_PROXY") == os.environ.get("HTTP_PROXY")


def test_settings_proxy_override_wins(monkeypatch):
    s = config.Settings.from_env()
    s.proxy = "http://127.0.0.1:1234"
    assert s.resolve_proxy() == "http://127.0.0.1:1234"


def test_find_codex_cli_returns_none_or_path():
    p = config.find_codex_cli()
    assert p is None or isinstance(p, Path)
    if p is not None:
        assert p.exists()


def test_user_launchers_empty_when_no_file(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_CODEX_HOME, str(tmp_path))
    assert config.load_user_launchers() == []


def test_user_launchers_reads_list(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_CODEX_HOME, str(tmp_path))
    (tmp_path / "web-login-launchers.json").write_text(
        '["C:/a/b.exe", "C:/c/d.exe"]', encoding="utf-8")
    assert config.load_user_launchers() == ["C:/a/b.exe", "C:/c/d.exe"]


def test_user_launchers_reads_dict(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_CODEX_HOME, str(tmp_path))
    (tmp_path / "web-login-launchers.json").write_text(
        '{"launchers": ["X"]}', encoding="utf-8")
    assert config.load_user_launchers() == ["X"]


def test_user_launchers_tolerates_garbage(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_CODEX_HOME, str(tmp_path))
    (tmp_path / "web-login-launchers.json").write_text("not json{{{", encoding="utf-8")
    assert config.load_user_launchers() == []


# --------------------------------------------------------------------------
# launcher
# --------------------------------------------------------------------------
def _never(*_a, **_k):
    return LaunchResult(False, "stub", "不应被调用")


def test_launch_stops_at_first_success(monkeypatch, tmp_path):
    """策略链应短路：第一个成功即返回，不继续尝试。"""
    fake = tmp_path / "launcher.exe"
    fake.write_bytes(b"x")
    s = config.Settings()
    s.launcher = fake

    calls: list[str] = []

    def good(settings, env):
        calls.append("good")
        return LaunchResult(True, "good", "ok")

    def should_not_run(settings, env):
        calls.append("bad")
        return _never()

    monkeypatch.setattr(launcher, "STRATEGIES", (
        launcher.strat_user_launcher,
        good,
        should_not_run,
    ))
    monkeypatch.setattr(launcher, "load_user_launchers", lambda: [])

    r = launch(s, {}, verbose=False)
    assert r.ok and r.method == "good"
    assert "bad" not in calls


def test_launch_skips_strategy_that_raises(monkeypatch):
    """单个策略抛异常不应中断整条链。"""
    def boom(settings, env):
        raise RuntimeError("kaboom")

    def good(settings, env):
        return LaunchResult(True, "good", "ok")

    monkeypatch.setattr(launcher, "STRATEGIES", (boom, good))
    r = launch(config.Settings(), {}, verbose=False)
    assert r.ok and r.method == "good"


def test_env_launcher_reports_missing(monkeypatch, tmp_path):
    s = config.Settings()
    s.launcher = tmp_path / "nope.exe"
    r = launcher.strat_env_launcher(s, {})
    assert not r.ok
    assert "不存在" in r.detail


def test_shortcut_strategy_does_not_crash_when_none():
    r = launcher.strat_shortcut(config.Settings(), {})
    assert isinstance(r, LaunchResult)


def test_direct_strategy_handles_missing_app(monkeypatch):
    monkeypatch.setattr(launcher, "find_codex_app", lambda: None)
    r = launcher.strat_direct(config.Settings(), {})
    assert not r.ok
