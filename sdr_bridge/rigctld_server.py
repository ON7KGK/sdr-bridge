"""Serveur rigctld TCP (port 4532) parle a WSJT-X / FlDigi / fldigi etc.

Protocole texte ligne par ligne :
  Une commande par ligne -> une reponse terminee par 'RPRT <code>\\n'
  (0 = OK, negatif = erreur). Pour les commandes 'get', la valeur est
  envoyee AVANT le RPRT.

Reference : man 1 rigctl, et code source hamlib/tests/rigctl_parse.c
"""

from __future__ import annotations

import asyncio
import logging

from .sdr_console import SdrConsoleBackend
from .translator import Translator, DUMP_STATE

log = logging.getLogger(__name__)

RPRT_OK = "RPRT 0\n"
RPRT_ERR = "RPRT -1\n"
RPRT_NOT_IMPL = "RPRT -11\n"   # RIG_ENIMPL


class RigctldServer:
    def __init__(self, host: str, port: int, backend: SdrConsoleBackend):
        self.host = host
        self.port = port
        self.backend = backend
        self.translator = Translator()
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port)
        log.info(f"rigctld : ecoute sur {self.host}:{self.port}")

    async def serve_forever(self) -> None:
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info(f"Client connecte : {peer}")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                raw = line.decode("ascii", errors="replace").strip()
                if not raw:
                    continue
                log.info(f"<< {raw}")
                try:
                    response = await self._dispatch(raw)
                except Exception as e:
                    log.exception(f"Erreur dispatch '{raw}' : {e}")
                    response = RPRT_ERR
                # Resume court : 1ere ligne + nombre total de lignes
                first = response.split("\n", 1)[0]
                nlines = response.count("\n")
                log.info(f">> {first!r} ({nlines} lignes)")
                writer.write(response.encode("ascii"))
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            log.info(f"Client deconnecte : {peer}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, line: str) -> str:
        """Parse une ligne rigctld et retourne la reponse (avec '\\n' final)."""
        # Forme longue (\set_freq) ou courte (F) -- on normalise
        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        # Commandes avec backslash : \dump_state, \chk_vfo, \get_powerstat etc.
        if cmd == "\\dump_state":
            return DUMP_STATE + RPRT_OK
        if cmd == "\\chk_vfo":
            return "CHKVFO: 0\n" + RPRT_OK
        if cmd in ("\\get_powerstat", ):
            return "1\n" + RPRT_OK

        # set_freq / F
        if cmd in ("F", "\\set_freq", "set_freq"):
            if not args:
                return RPRT_ERR
            hz = int(float(args[0]))
            vfo = args[1] if len(args) > 1 else self.translator.current_vfo
            await self.backend.send(self.translator.set_freq_cat(hz, vfo))
            return RPRT_OK

        # get_freq / f
        if cmd in ("f", "\\get_freq", "get_freq"):
            vfo = args[0] if args else self.translator.current_vfo
            resp = await self.backend.query(self.translator.get_freq_cat(vfo))
            hz = self.translator.parse_freq_resp(resp)
            return f"{hz}\n" + RPRT_OK

        # set_mode / M <mode> <bw>
        if cmd in ("M", "\\set_mode", "set_mode"):
            if not args:
                return RPRT_ERR
            mode = args[0]
            bw = int(args[1]) if len(args) > 1 else 0
            self.translator.cached_mode = mode.upper()
            self.translator.cached_bw = bw
            await self.backend.send(self.translator.set_mode_cat(mode))
            return RPRT_OK

        # get_mode / m -> retourne MODE\nBW\n + RPRT
        if cmd in ("m", "\\get_mode", "get_mode"):
            try:
                resp = await self.backend.query(self.translator.get_mode_cat())
                mode = self.translator.parse_mode_resp(resp)
                self.translator.cached_mode = mode
            except Exception:
                mode = self.translator.cached_mode
            return f"{mode}\n{self.translator.cached_bw}\n" + RPRT_OK

        # set_ptt / T 0|1
        if cmd in ("T", "\\set_ptt", "set_ptt"):
            if not args:
                return RPRT_ERR
            state = int(args[0])
            self.translator.ptt_state = state
            # v1 : pas de TX (RX seul). On accepte sans relayer pour ne pas
            # perturber le SDR cote RX. v2 enverra TX;/RX; au backend.
            log.info(f"PTT request : {state} (ignore en v1 RX-only)")
            return RPRT_OK

        # get_ptt / t
        if cmd in ("t", "\\get_ptt", "get_ptt"):
            return f"{self.translator.ptt_state}\n" + RPRT_OK

        # set_vfo / V
        if cmd in ("V", "\\set_vfo", "set_vfo"):
            if args:
                self.translator.current_vfo = args[0]
            return RPRT_OK

        # get_vfo / v
        if cmd in ("v", "\\get_vfo", "get_vfo"):
            return f"{self.translator.current_vfo}\n" + RPRT_OK

        # set_split_vfo / S
        if cmd in ("S", "\\set_split_vfo", "set_split_vfo"):
            if len(args) >= 1:
                self.translator.split_state = int(args[0])
            return RPRT_OK

        # get_split_vfo / s
        if cmd in ("s", "\\get_split_vfo", "get_split_vfo"):
            return (f"{self.translator.split_state}\n"
                    f"{self.translator.current_vfo}\n" + RPRT_OK)

        # set_split_freq / I
        if cmd in ("I", "\\set_split_freq", "set_split_freq"):
            if args:
                self.translator.split_freq_hz = int(float(args[0]))
            return RPRT_OK

        # get_split_freq / i
        if cmd in ("i", "\\get_split_freq", "get_split_freq"):
            return f"{self.translator.split_freq_hz}\n" + RPRT_OK

        # quit / q : on accepte, le client va fermer la connexion
        if cmd in ("q", "\\quit", "quit", "exit"):
            return RPRT_OK

        log.warning(f"Commande rigctld non implementee : '{line}'")
        return RPRT_NOT_IMPL
