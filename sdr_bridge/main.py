"""Entry point CLI : charge bridge.yaml, lance le serveur rigctld."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

import yaml

from . import __version__
from .rigctld_server import RigctldServer
from .sdr_console import SdrConsoleBackend


DEFAULT_CONFIG = {
    "rigctld": {
        "host": "127.0.0.1",
        "port": 4532,
    },
    "sdr_console": {
        "mode": "tcp",       # 'tcp' ou 'serial'
        "host": "127.0.0.1",
        "port": 7300,
        # Si mode = 'serial' : port = 'COM5', baud = 9600
    },
    "log_level": "INFO",
}


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_file():
        logging.warning(f"Config {path} introuvable, defaults utilises.")
        return DEFAULT_CONFIG
    with open(cfg_path, "r", encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}
    # Merge avec defaults (1 niveau)
    merged = {**DEFAULT_CONFIG, **user_cfg}
    for k, v in DEFAULT_CONFIG.items():
        if isinstance(v, dict):
            merged[k] = {**v, **user_cfg.get(k, {})}
    return merged


async def run(cfg: dict) -> None:
    backend = SdrConsoleBackend.from_config(cfg["sdr_console"])

    # Tentative de connexion initiale, mais ne pas planter si KO :
    # le serveur rigctld doit demarrer pour que WSJT-X puisse s'y attacher,
    # et on retentera la connexion backend en background.
    try:
        await backend.connect()
    except Exception as e:
        logging.warning(f"Backend SDR Console non joignable au demarrage : {e}")
        logging.warning("Le serveur rigctld demarre quand meme, retry backend en arriere-plan.")

    server = RigctldServer(
        host=cfg["rigctld"]["host"],
        port=int(cfg["rigctld"]["port"]),
        backend=backend,
    )
    await server.start()

    # Reconnexion backend en arriere-plan (retry toutes les 5s tant que down)
    async def reconnect_loop():
        while True:
            if not backend.connected:
                try:
                    await backend.connect()
                except Exception as e:
                    logging.debug(f"Retry backend echec : {e}")
            await asyncio.sleep(5.0)

    reconnect_task = asyncio.create_task(reconnect_loop())

    try:
        await server.serve_forever()
    finally:
        reconnect_task.cancel()
        await backend.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SDR Bridge — pont rigctld vers SDR Console")
    parser.add_argument("--config", "-c", default="bridge.yaml",
                        help="Chemin du fichier de config YAML (defaut: bridge.yaml)")
    parser.add_argument("--version", "-V", action="version",
                        version=f"sdr-bridge {__version__}")
    args = parser.parse_args()

    # Logging initial avant load_config (peut emettre des warnings)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(args.config)
    logging.getLogger().setLevel(getattr(logging, cfg.get("log_level", "INFO").upper()))

    logging.info(f"SDR Bridge v{__version__} demarre")
    logging.info(f"  rigctld   : {cfg['rigctld']['host']}:{cfg['rigctld']['port']}")
    sc = cfg["sdr_console"]
    if sc["mode"] == "tcp":
        logging.info(f"  SDR Console : TCP {sc['host']}:{sc['port']}")
    else:
        logging.info(f"  SDR Console : serie {sc['port']} @ {sc.get('baud', 9600)}")

    # Signaux propres (Ctrl+C)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main_task = loop.create_task(run(cfg))

    def stop():
        logging.info("Arret demande, fermeture...")
        main_task.cancel()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, stop)
        loop.add_signal_handler(signal.SIGTERM, stop)

    try:
        loop.run_until_complete(main_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.close()
        logging.info("Termine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
