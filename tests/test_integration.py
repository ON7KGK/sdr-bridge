"""Test integration end-to-end : mock console + bridge + client rigctld TCP.

Lance les deux serveurs en background, simule un client WSJT-X qui envoie
des commandes rigctld, verifie que les changements arrivent jusqu'au mock.
"""

import asyncio
import contextlib

import pytest

from sdr_bridge.mock_console import MockConsole
from sdr_bridge.rigctld_server import RigctldServer
from sdr_bridge.sdr_console import TcpBackend


MOCK_PORT = 17300       # ports decales pour eviter les conflits si vrai SDR tourne
BRIDGE_PORT = 14532


@contextlib.asynccontextmanager
async def running_stack():
    """Demarre mock + bridge, yield, puis cleanup."""
    mock = MockConsole("127.0.0.1", MOCK_PORT)
    mock_task = asyncio.create_task(mock.start())
    await asyncio.sleep(0.1)   # laisse le mock binder

    backend = TcpBackend("127.0.0.1", MOCK_PORT)
    await backend.connect()
    bridge = RigctldServer("127.0.0.1", BRIDGE_PORT, backend)
    await bridge.start()
    bridge_task = asyncio.create_task(bridge.serve_forever())
    await asyncio.sleep(0.1)

    try:
        yield mock
    finally:
        bridge_task.cancel()
        mock_task.cancel()
        await backend.close()
        with contextlib.suppress(asyncio.CancelledError, BaseException):
            await bridge_task
        with contextlib.suppress(asyncio.CancelledError, BaseException):
            await mock_task


async def send_rigctld(cmd: str) -> str:
    reader, writer = await asyncio.open_connection("127.0.0.1", BRIDGE_PORT)
    writer.write((cmd + "\n").encode())
    await writer.drain()
    # Lire jusqu'a 'RPRT' present dans la reponse
    data = b""
    while b"RPRT" not in data:
        chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
        if not chunk:
            break
        data += chunk
    writer.close()
    await writer.wait_closed()
    return data.decode()


@pytest.mark.asyncio
async def test_set_then_get_freq():
    async with running_stack() as mock:
        # WSJT-X envoie F <hz>
        resp = await send_rigctld("F 50313000")
        assert "RPRT 0" in resp
        # Verifier que le mock a bien recu
        await asyncio.sleep(0.05)
        assert mock.state.freq_a_hz == 50313000

        # Get freq retourne la valeur
        resp = await send_rigctld("f")
        # Reponse : "50313000\nRPRT 0\n"
        assert resp.startswith("50313000")
        assert "RPRT 0" in resp


@pytest.mark.asyncio
async def test_set_then_get_mode():
    async with running_stack() as mock:
        resp = await send_rigctld("M CW 500")
        assert "RPRT 0" in resp
        await asyncio.sleep(0.05)
        assert mock.state.mode == "3"   # CW

        resp = await send_rigctld("m")
        assert resp.startswith("CW")
        assert "RPRT 0" in resp


@pytest.mark.asyncio
async def test_dump_state_returns_capabilities():
    async with running_stack():
        resp = await send_rigctld("\\dump_state")
        # Doit contenir des chiffres de la dump_state + RPRT 0
        assert "1800000.000000" in resp     # plage HF dans la dump_state
        assert "RPRT 0" in resp


@pytest.mark.asyncio
async def test_chk_vfo():
    async with running_stack():
        resp = await send_rigctld("\\chk_vfo")
        assert "CHKVFO: 0" in resp
        assert "RPRT 0" in resp


@pytest.mark.asyncio
async def test_ptt_accepted_in_rx_only():
    async with running_stack():
        # v1 RX-only : T 1 accepte (RPRT 0) mais non transmis
        resp = await send_rigctld("T 1")
        assert "RPRT 0" in resp
        resp = await send_rigctld("t")
        assert resp.startswith("1")     # etat memorise
