"""Traducteur rigctld <-> Kenwood TS-2000.

rigctld parle un protocole texte tres simple (man 1 rigctl). On implemente
les commandes que WSJT-X envoie reellement :

  f / F <freq>          get/set frequency (Hz)
  m / M <mode> <bw>     get/set mode
  v / V <vfo>           get/set VFO
  s / S <split> <vfo>   get/set split
  t / T <ptt>           get/set PTT
  i / I <freq>          get/set split frequency
  \\dump_state           rig capability dump (WSJT-X l'envoie au connect)
  \\chk_vfo              0 = pas de targeting VFO requis

Format Kenwood TS-2000 (decoupe ; final) :
  FA00014074000;        set VFO A freq (11 digits Hz)
  FA;                   get VFO A freq -> reponse FA<11>;
  MD<n>;                set mode (1=LSB 2=USB 3=CW 4=FM 5=AM 6=FSK 7=CW-R 9=FSK-R)
  TX; / RX;             PTT on/off
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# rigctld mode name <-> TS-2000 numeric code
RIGCTLD_TO_TS2000 = {
    "LSB":   "1",
    "USB":   "2",
    "CW":    "3",
    "FM":    "4",
    "AM":    "5",
    "RTTY":  "6",
    "CWR":   "7",
    "FSK":   "6",
    "PKTUSB": "2",   # WSJT-X data mode -> USB cote SDR
    "PKTLSB": "1",
    "DATA-U": "2",
    "DATA-L": "1",
}
TS2000_TO_RIGCTLD = {
    "1": "LSB",
    "2": "USB",
    "3": "CW",
    "4": "FM",
    "5": "AM",
    "6": "RTTY",
    "7": "CWR",
    "9": "RTTYR",
}


# Reponse \dump_state minimale pour satisfaire WSJT-X.
# Documente le rig comme un TS-2000 generique avec freq 1.8 a 470 MHz,
# modes USB/LSB/CW/FM/AM/RTTY, 1 VFO, capacite split.
DUMP_STATE = """\
0
2
2
150000.000000 1500000000.000000 0x1ff -1 -1 0x10000003 0x3
0 0 0 0 0 0 0
0 0 0 0 0 0 0
1800000.000000 2000000000.000000 0x1ff 1000 100000 0x10000003 0x3
0 0 0 0 0 0 0
0 0 0 0 0 0 0
0x1ff 1
0x1ff 0
0 0
0x1e 2400
0x2 500
0x1 8000
0x1 2400
0x20 15000
0x20 8000
0x40 230000
0 0
9990
9990
10000
0
10
10 20 30
0x3effffff
0x3effffff
0x7fffffff
0x7fffffff
0x7fffffff
0x7fffffff
"""


class Translator:
    """Maintient l'etat partage (PTT, split, vfo courante) et traduit."""

    def __init__(self):
        self.ptt_state = 0           # rigctld ne peut pas toujours lire le PTT cote SDR
        self.split_state = 0
        self.split_freq_hz = 0
        self.current_vfo = "VFOA"
        self.cached_mode = "USB"
        self.cached_bw = 2400

    # ── Commandes vers SDR Console ──

    @staticmethod
    def set_freq_cat(hz: int, vfo: str = "VFOA") -> str:
        target = "FA" if vfo in ("VFO", "VFOA", "currVFO", "Main") else "FB"
        return f"{target}{int(hz):011d};"

    @staticmethod
    def get_freq_cat(vfo: str = "VFOA") -> str:
        return "FA;" if vfo in ("VFO", "VFOA", "currVFO", "Main") else "FB;"

    @staticmethod
    def set_mode_cat(mode_name: str) -> str:
        code = RIGCTLD_TO_TS2000.get(mode_name.upper())
        if code is None:
            log.warning(f"Mode rigctld inconnu '{mode_name}', fallback USB")
            code = "2"
        return f"MD{code};"

    @staticmethod
    def get_mode_cat() -> str:
        return "MD;"

    @staticmethod
    def parse_freq_resp(resp: str) -> int:
        """Parse 'FA00014074000;' ou 'FB00014074000;' -> int Hz."""
        s = resp.strip().rstrip(";")
        if len(s) < 13 or s[:2] not in ("FA", "FB"):
            raise ValueError(f"Reponse freq invalide : {resp!r}")
        return int(s[2:13])

    @staticmethod
    def parse_mode_resp(resp: str) -> str:
        """Parse 'MD2;' -> 'USB'."""
        s = resp.strip().rstrip(";")
        if len(s) < 3 or not s.startswith("MD"):
            raise ValueError(f"Reponse mode invalide : {resp!r}")
        return TS2000_TO_RIGCTLD.get(s[2], "USB")
