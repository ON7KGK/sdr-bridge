"""Backend SDR Console : client CAT (TS-2000 style) sur serie ou TCP.

SDR Console expose son moteur radio via une emulation TS-2000 a configurer
dans Tools -> External Radio (ou equivalent selon version). Le port peut
etre serie (COM virtuel via com0com) ou TCP (selon options de SDR Console).

Ce module masque la difference et expose une API async unique.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger(__name__)


class SdrConsoleBackend:
    """Client CAT TS-2000 vers SDR Console.

    Usage :
        backend = SdrConsoleBackend.from_config(cfg["sdr_console"])
        await backend.connect()
        resp = await backend.query("FA;")   # "FA00014074000;"
        await backend.send("TX;")           # fire-and-forget
        await backend.close()
    """

    def __init__(self, mode: str):
        self.mode = mode
        self._connected = False
        self._lock = asyncio.Lock()

    @staticmethod
    def from_config(cfg: dict) -> "SdrConsoleBackend":
        mode = cfg.get("mode", "tcp").lower()
        if mode == "tcp":
            return TcpBackend(host=cfg["host"], port=int(cfg["port"]))
        if mode == "serial":
            return SerialBackend(
                port=cfg["port"],
                baud=int(cfg.get("baud", 9600)),
            )
        raise ValueError(f"Mode SDR Console inconnu : {mode!r} (attendu 'tcp' ou 'serial')")

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

    async def query(self, cmd: str) -> str:
        """Envoie une commande CAT terminee par ';' et attend la reponse."""
        raise NotImplementedError

    async def send(self, cmd: str) -> None:
        """Envoie sans attendre de reponse (TX;, RX;)."""
        raise NotImplementedError


class TcpBackend(SdrConsoleBackend):
    def __init__(self, host: str, port: int):
        super().__init__("tcp")
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect(self) -> None:
        log.info(f"SDR Console TCP : connexion a {self.host}:{self.port}")
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._connected = True
        log.info("SDR Console TCP : connecte")

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._connected = False
        self._reader = self._writer = None

    async def query(self, cmd: str) -> str:
        async with self._lock:
            self._writer.write(cmd.encode("ascii"))
            await self._writer.drain()
            data = await asyncio.wait_for(self._reader.readuntil(b";"), timeout=1.0)
            return data.decode("ascii", errors="replace")

    async def send(self, cmd: str) -> None:
        async with self._lock:
            self._writer.write(cmd.encode("ascii"))
            await self._writer.drain()


class SerialBackend(SdrConsoleBackend):
    """Backend serie (pyserial dans un executor).

    pyserial n'est pas natif async ; on l'enrobe dans run_in_executor pour
    ne pas bloquer l'event loop.
    """

    def __init__(self, port: str, baud: int):
        super().__init__("serial")
        self.port = port
        self.baud = baud
        self._ser = None

    async def connect(self) -> None:
        import serial  # import lazy : pas d'erreur d'import si on n'utilise pas serial
        loop = asyncio.get_running_loop()
        log.info(f"SDR Console serie : ouverture {self.port} @ {self.baud} baud")
        self._ser = await loop.run_in_executor(
            None, lambda: serial.Serial(self.port, self.baud, timeout=1.0))
        self._connected = True
        log.info("SDR Console serie : ouvert")

    async def close(self) -> None:
        if self._ser:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ser.close)
        self._connected = False
        self._ser = None

    async def query(self, cmd: str) -> str:
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ser.write, cmd.encode("ascii"))
            data = await loop.run_in_executor(None, self._ser.read_until, b";")
            return data.decode("ascii", errors="replace")

    async def send(self, cmd: str) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ser.write, cmd.encode("ascii"))
