from __future__ import annotations

import asyncio
import io
import socket
from unittest.mock import AsyncMock, patch

import pytest

from spongebob.diagnose import Sample, probe_dns, probe_tcp
from spongebob.diagnose.__main__ import main as diagnose_main


@pytest.mark.asyncio
async def test_probe_tcp_local_server_ok() -> None:
    async def handle_client(
        _reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        samples = await probe_tcp(
            host="127.0.0.1",
            port=port,
            count=4,
            interval_ms=100,
            timeout_ms=1000,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert len(samples) == 4
    assert [s.seq for s in samples] == [0, 1, 2, 3]
    for s in samples:
        assert isinstance(s, Sample)
        assert s.outcome == "ok"
        assert s.rtt_ms is not None
        assert 0.0 <= s.rtt_ms < 500.0
        assert s.sent_at_ms > 0.0


@pytest.mark.asyncio
async def test_probe_tcp_closed_port_refused_early_abort() -> None:
    # Bind and immediately close an ephemeral socket to get an unused local port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]

    samples = await probe_tcp(
        host="127.0.0.1",
        port=closed_port,
        count=10,
        interval_ms=100,
        timeout_ms=5000,
    )

    assert len(samples) == 3
    assert [s.seq for s in samples] == [0, 1, 2]
    assert all(s.outcome == "refused" and s.rtt_ms is None for s in samples)


@pytest.mark.asyncio
async def test_probe_tcp_timeout_counted_as_loss_no_early_abort() -> None:
    async def hanging_connect(*_args: object, **_kwargs: object) -> tuple[object, object]:
        await asyncio.sleep(5.0)
        raise AssertionError("should have timed out")

    with patch("spongebob.diagnose.probes.asyncio.open_connection", side_effect=hanging_connect):
        samples = await probe_tcp(
            host="127.0.0.1",
            port=443,
            count=4,
            interval_ms=100,
            timeout_ms=100,
        )

    assert len(samples) == 4
    assert all(s.outcome == "timeout" and s.rtt_ms is None for s in samples)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "exc_type"),
    [
        ({"host": "127.0.0.1", "count": 201}, ValueError),
        ({"host": "127.0.0.1", "count": 0}, ValueError),
        ({"host": "127.0.0.1", "interval_ms": 50}, ValueError),
        ({"host": "127.0.0.1", "timeout_ms": 0}, ValueError),
        ({"host": "127.0.0.1", "timeout_ms": 5001}, ValueError),
        ({"host": "127.0.0.1", "port": 0}, ValueError),
        ({"host": "127.0.0.1", "port": 70000}, ValueError),
        ({"host": "127.0.0.1,127.0.0.2"}, ValueError),
        ({"host": ""}, ValueError),
    ],
)
async def test_probe_tcp_limit_validation(
    kwargs: dict[str, object], exc_type: type[Exception]
) -> None:
    with pytest.raises(exc_type):
        await probe_tcp(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("user_input", ["n", "N", "", "no", "maybe"])
def test_runner_consent_aborts_without_probing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], user_input: str
) -> None:
    called = False

    async def fake_probe_tcp(**_kwargs: object) -> list[Sample]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("spongebob.diagnose.__main__.probe_tcp", fake_probe_tcp)
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{user_input}\n"))

    exit_code = diagnose_main(["127.0.0.1", "--port", "443", "--count", "5", "--interval-ms", "100"])

    assert exit_code == 0
    assert called is False
    out = capsys.readouterr().out
    assert "This will contact 127.0.0.1:443 5 times. Continue? [y/N]" in out
    assert "Aborted." in out


def test_runner_consent_proceeds_on_y(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_samples = [
        Sample(seq=0, sent_at_ms=10.0, rtt_ms=1.5, outcome="ok"),
        Sample(seq=1, sent_at_ms=210.0, rtt_ms=None, outcome="timeout"),
    ]
    mock_probe = AsyncMock(return_value=fake_samples)
    monkeypatch.setattr("spongebob.diagnose.__main__.probe_tcp", mock_probe)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))

    exit_code = diagnose_main(["127.0.0.1", "--port", "8443", "--count", "2", "--interval-ms", "100"])

    assert exit_code == 0
    mock_probe.assert_awaited_once()
    out = capsys.readouterr().out
    assert "ok=1 timeout=1 errors=0" in out
    assert "rtt_ms: min=1.50 avg=1.50 max=1.50" in out


@pytest.mark.asyncio
async def test_probe_dns_ok_error_and_timeout() -> None:
    loop = asyncio.get_running_loop()

    async def ok_getaddrinfo(*_args: object, **_kwargs: object) -> list[object]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    with patch.object(loop, "getaddrinfo", side_effect=ok_getaddrinfo):
        ok_samples = await probe_dns("localhost", count=2, interval_ms=100, timeout_ms=500)
    assert len(ok_samples) == 2
    assert all(s.outcome == "ok" and s.rtt_ms is not None for s in ok_samples)

    async def err_getaddrinfo(*_args: object, **_kwargs: object) -> list[object]:
        raise socket.gaierror("Name or service not known")

    with patch.object(loop, "getaddrinfo", side_effect=err_getaddrinfo):
        err_samples = await probe_dns("nonexistent.invalid", count=5, interval_ms=100, timeout_ms=500)
    assert len(err_samples) == 3
    assert all(s.outcome == "dns_error" and s.rtt_ms is None for s in err_samples)

    async def slow_getaddrinfo(*_args: object, **_kwargs: object) -> list[object]:
        await asyncio.sleep(5.0)
        return []

    with patch.object(loop, "getaddrinfo", side_effect=slow_getaddrinfo):
        to_samples = await probe_dns("slow.invalid", count=2, interval_ms=100, timeout_ms=100)
    assert len(to_samples) == 2
    assert all(s.outcome == "timeout" and s.rtt_ms is None for s in to_samples)
