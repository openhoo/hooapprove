import stat
import sys
from types import SimpleNamespace

import httpx
import pytest

from hooapprove import pair_cli


@pytest.fixture
def pairing_cli(monkeypatch, tmp_path):
    output = tmp_path / "pair.png"
    monkeypatch.setattr(
        sys,
        "argv",
        ["hooapprove-pair", "--subject", "owner", "--label", "Shop", "--output", str(output)],
    )
    monkeypatch.setattr(pair_cli.getpass, "getpass", lambda _: "private-executor-token")

    def save(output, **kwargs):
        output.write(b"fixture-png")

    monkeypatch.setitem(
        sys.modules, "segno", SimpleNamespace(make_qr=lambda _: SimpleNamespace(save=save))
    )
    return output


@pytest.mark.parametrize(
    "url",
    [
        "https:///invalid",
        "https://[invalid",
        "https://user:pass@example.com",
        "https://example.com/path",
        "https://example.com?token=private",
        "https://example.com#fragment",
        "https://example.com:invalid",
        "http://example.com",
    ],
)
def test_pairing_rejects_invalid_origin_before_prompt(pairing_cli, monkeypatch, url):
    sys.argv.extend(["--url", url])

    def unexpected_prompt(_):
        pytest.fail("Must validate origin before requesting credentials")

    monkeypatch.setattr(pair_cli.getpass, "getpass", unexpected_prompt)
    with pytest.raises(SystemExit) as error:
        pair_cli.main()
    assert error.value.code == 2
    assert not pairing_cli.exists()


def test_pairing_keeps_existing_file(pairing_cli):
    pairing_cli.write_bytes(b"keep-existing")
    with pytest.raises(SystemExit) as error:
        pair_cli.main()
    assert error.value.code == 2
    assert pairing_cli.read_bytes() == b"keep-existing"


def test_pairing_writes_private_qr(pairing_cli, monkeypatch, capsys):
    def handler(request):
        assert request.url == "https://approve.openhoo.dev/v1/pairings"
        assert request.headers["authorization"] == "Bearer private-executor-token"
        return httpx.Response(201, json={"uri": "hooapprove://pair?token=private-ticket"})

    real_client = httpx.Client
    monkeypatch.setattr(
        pair_cli.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    pair_cli.main()
    assert pairing_cli.read_bytes() == b"fixture-png"
    assert stat.S_IMODE(pairing_cli.stat().st_mode) == 0o600
    output = capsys.readouterr()
    assert "private-ticket" not in output.out + output.err
    assert "private-executor-token" not in output.out + output.err


def test_pairing_failure_removes_file_and_hides_response(pairing_cli, monkeypatch, capsys):
    def fail_qr(_):
        raise ValueError("private-ticket must not appear")

    real_client = httpx.Client
    monkeypatch.setattr(
        pair_cli.httpx,
        "Client",
        lambda **kwargs: real_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(201, json={"uri": "private-ticket"})
            ),
        ),
    )
    monkeypatch.setitem(sys.modules, "segno", SimpleNamespace(make_qr=fail_qr))
    with pytest.raises(SystemExit) as error:
        pair_cli.main()
    assert error.value.code == 1
    assert not pairing_cli.exists()
    output = capsys.readouterr()
    assert "private-ticket" not in output.out + output.err


def test_pairing_refuses_echoing_token(pairing_cli, monkeypatch, capsys):
    import warnings

    def insecure_prompt(_):
        warnings.warn("Cannot disable echo", pair_cli.getpass.GetPassWarning, stacklevel=2)
        pytest.fail("Token must not be read when echo cannot be disabled")

    monkeypatch.setattr(pair_cli.getpass, "getpass", insecure_prompt)
    with pytest.raises(SystemExit) as error:
        pair_cli.main()
    assert error.value.code == 1
    assert not pairing_cli.exists()
