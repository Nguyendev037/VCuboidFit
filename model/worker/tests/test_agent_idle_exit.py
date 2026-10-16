"""A16: virtual monotonic clock; no GPU, real server or minute-long sleep."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_agent():
    path = Path(__file__).resolve().parents[2] / "scripts" / "colab_agent.py"
    spec = importlib.util.spec_from_file_location("idle_agent", path)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    return agent


def test_a16_idle_exit_after_one_minute(monkeypatch, capsys):
    agent = load_agent()
    now = [0.0]
    polls = []

    class FakeClient:
        def __init__(self, *args):
            pass

        def call(self, method, path):
            polls.append(now[0])
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr(agent, "Client", FakeClient)
    args = SimpleNamespace(server="https://fake.invalid/api", token="fake", once=False,
                           idle_exit_min=1)
    result = agent.loop(args, sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
                        clock=lambda: now[0])
    assert result == 0
    assert now[0] == 60
    assert polls == [0, 60]
    assert "het viec - tu tat" in capsys.readouterr().out


def test_work_resets_idle_clock(monkeypatch):
    agent = load_agent()
    now = [0.0]
    replies = iter([204, 200, 204, 204])

    class FakeClient:
        def __init__(self, *args):
            pass

        def call(self, *args):
            return SimpleNamespace(status_code=next(replies), json=lambda: {"taskId": "fake"})

    monkeypatch.setattr(agent, "Client", FakeClient)
    monkeypatch.setattr(agent, "process", lambda *args: now.__setitem__(0, now[0] + 120))
    args = SimpleNamespace(server="https://fake.invalid/api", token="fake", once=False,
                           idle_exit_min=1)
    assert agent.loop(args, sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
                      clock=lambda: now[0]) == 0
    assert now[0] == 240


def test_cli_reads_idle_environment(monkeypatch):
    agent = load_agent()
    monkeypatch.setenv("VCF_IDLE_MIN", "15")
    captured = []
    monkeypatch.setattr(agent, "loop", lambda args: captured.append(args.idle_exit_min) or 0)
    assert agent.main(["--server", "https://fake.invalid", "--token", "fake"]) == 0
    assert captured == [15]


def test_zero_idle_limit_keeps_polling(monkeypatch):
    agent = load_agent()
    calls = []

    class FakeClient:
        def __init__(self, *args):
            pass

        def call(self, *args):
            calls.append(1)
            if len(calls) == 3:
                raise agent.Stop("test stop", 7)
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr(agent, "Client", FakeClient)
    args = SimpleNamespace(server="https://fake.invalid", token="fake", once=False,
                           idle_exit_min=0)
    assert agent.loop(args, sleep=lambda _: None, clock=lambda: 9999) == 7
    assert len(calls) == 3
