import base64
import getpass
import runpy
import sys

import pytest

from app.passwords import hash_password, verify_password


def run_cli(monkeypatch, *answers):
    replies = iter(answers)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(replies))
    # 避免 runpy 因模块已导入而发出 RuntimeWarning
    monkeypatch.delitem(sys.modules, "app.passwords", raising=False)
    runpy.run_module("app.passwords", run_name="__main__")


def test_hash_and_verify():
    """Scenario: 生成并校验"""
    first = hash_password("P")
    second = hash_password("P")

    assert first != second
    assert verify_password("P", first)
    assert verify_password("P", second)
    assert not verify_password("other", first)


def test_hash_format():
    algorithm, n, r, p, salt, digest = hash_password("P").split("$")

    assert (algorithm, n, r, p) == ("scrypt", "16384", "8", "1")
    assert len(base64.b64decode(salt, validate=True)) == 16
    assert len(base64.b64decode(digest, validate=True)) == 64


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "not-a-hash",
        "scrypt$16384$8$1$c2FsdA==",
        "bcrypt" + hash_password("P")[len("scrypt"):],
        "scrypt$abc$8$1$c2FsdHNhbHRzYWx0c2FsdA==$aGFzaA==",
        "scrypt$3$8$1$c2FsdHNhbHRzYWx0c2FsdA==$aGFzaA==",
        "scrypt$-2$8$1$c2FsdHNhbHRzYWx0c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$!!!$aGFzaA==",
        "scrypt$16384$8$1$c2FsdHNhbHRzYWx0c2FsdA==$!!!",
    ],
)
def test_verify_malformed_returns_false(encoded):
    assert verify_password("P", encoded) is False


def test_cli_prints_hash(monkeypatch, capsys):
    """Scenario: 生成并校验"""
    run_cli(monkeypatch, "P", "P")

    encoded = capsys.readouterr().out.strip()
    assert verify_password("P", encoded)
    assert not verify_password("other", encoded)


def test_cli_rejects_empty_password(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "", "")

    assert exc.value.code == 1
    assert capsys.readouterr().out == ""


def test_cli_mismatch_exits_1(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(monkeypatch, "P", "Q")

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err
