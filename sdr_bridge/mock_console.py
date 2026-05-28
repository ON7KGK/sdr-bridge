"""Faux SDR Console — repond a quelques commandes CAT TS-2000 sur TCP.

Permet de tester sdr-bridge sans avoir SDR Console installe / configure.

Lancement :
    python -m sdr_bridge.mock_console --port 7300

Etat persistant (frequence, mode) garde en memoire pendant l'execution.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

log = logging.getLogger("mock_console")


@dataclass
class FakeRadioState:
    freq_a_hz: int = 14074000
    freq_b_hz: int = 14074000
    mode: str = "2"            # 2 = USB en encodage TS-2000
    tx: bool = False


class MockConsole:
    """Serveur TCP qui simule un TS-2000 minimal."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.state = FakeRadioState()

    async def start(self) -> None:
        server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info(f"Mock SDR Console : ecoute sur {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info(f"Client connecte : {peer}")
        buf = b""
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
                buf += chunk
                # Traiter chaque commande terminee par ';'
                while b";" in buf:
                    cmd, _, buf = buf.partition(b";")
                    cmd_str = cmd.decode("ascii", errors="replace").strip()
                    if not cmd_str:
                        continue
                    resp = self._dispatch(cmd_str + ";")
                    if resp:
                        log.debug(f"<< {cmd_str};   >> {resp.rstrip(';')!r}")
                        writer.write(resp.encode("ascii"))
                        await writer.drain()
                    else:
                        log.debug(f"<< {cmd_str};   (no response)")
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            log.info(f"Client deconnecte : {peer}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _dispatch(self, cmd: str) -> str:
        """Renvoie la reponse CAT, ou '' si la commande ne demande pas de reponse."""
        s = cmd.rstrip(";")

        # Get freq A : 'FA;' -> 'FA<11 digits>;'
        if s == "FA":
            return f"FA{self.state.freq_a_hz:011d};"
        # Get freq B
        if s == "FB":
            return f"FB{self.state.freq_b_hz:011d};"
        # Set freq A : 'FA00014074000;' -> ack par renvoyer la valeur ? TS-2000
        # n'envoie pas d'ack ; on reste silencieux.
        if s.startswith("FA") and len(s) >= 13:
            try:
                self.state.freq_a_hz = int(s[2:13])
                log.info(f"VFO A -> {self.state.freq_a_hz} Hz")
            except ValueError:
                pass
            return ""
        if s.startswith("FB") and len(s) >= 13:
            try:
                self.state.freq_b_hz = int(s[2:13])
                log.info(f"VFO B -> {self.state.freq_b_hz} Hz")
            except ValueError:
                pass
            return ""

        # Get mode : 'MD;' -> 'MD<n>;'
        if s == "MD":
            return f"MD{self.state.mode};"
        # Set mode : 'MD2;'
        if s.startswith("MD") and len(s) == 3:
            self.state.mode = s[2]
            log.info(f"Mode -> {s[2]}")
            return ""

        # TX / RX
        if s == "TX":
            self.state.tx = True
            log.info("PTT -> TX")
            return ""
        if s == "RX":
            self.state.tx = False
            log.info("PTT -> RX")
            return ""

        # ID; -> 'ID019;' (TS-2000 = 19)
        if s == "ID":
            return "ID019;"

        # Inconnu : on log et on repond rien (comportement TS-2000)
        log.debug(f"Commande inconnue ignoree : {s!r}")
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock SDR Console (TS-2000)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7300)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        asyncio.run(MockConsole(args.host, args.port).start())
    except KeyboardInterrupt:
        log.info("Arret demande.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
