# SDR Bridge

Pont **rigctld** (Hamlib NET rigctl, port 4532) <-> **SDR Console** (CAT
emulation TS-2000, serie ou TCP).

Permet a WSJT-X (ou tout logiciel parlant Hamlib NET rigctl) de piloter
SDR Console directement, **sans Omnirig ni paire COM virtuelle**.

```
WSJT-X  --(TCP 4532, rigctld)-->  sdr-bridge  --(serie ou TCP, CAT TS-2000)-->  SDR Console
```

## Installation

```cmd
cd sdr-bridge
pip install -r requirements.txt
copy bridge.yaml.example bridge.yaml
```

Editer `bridge.yaml` selon ta config SDR Console (voir l'exemple).

## Configuration SDR Console

Dans SDR Console : `Tools -> External Radio` (ou equivalent selon version).
- Activer l'emulation **Kenwood TS-2000**.
- Choisir un port (serie COM virtuel via com0com, ou TCP integre si
  disponible dans ta version).
- Noter les parametres (port + baud si serie, host + port TCP si TCP).

Reporter ces valeurs dans `bridge.yaml` sous la cle `sdr_console`.

## Lancement

```cmd
python -m sdr_bridge.main --config bridge.yaml
```

Sortie attendue :

```
14:00:00 [INFO] root: SDR Bridge v0.1.0 demarre
14:00:00 [INFO] root:   rigctld   : 127.0.0.1:4532
14:00:00 [INFO] root:   SDR Console : TCP 127.0.0.1:7300
14:00:00 [INFO] sdr_bridge.sdr_console: SDR Console TCP : connecte
14:00:00 [INFO] sdr_bridge.rigctld_server: rigctld : ecoute sur 127.0.0.1:4532
```

## Configuration WSJT-X

`File -> Settings -> Radio` :
- **Rig** : `Hamlib NET rigctl`
- **Network Server** : `localhost:4532`
- **Poll Interval** : 1s (ou plus)
- **PTT Method** : VOX ou CAT (CAT ignoree en v1 RX-only)

Cliquer **Test CAT** : doit etre vert.

## Commandes rigctld supportees

| Commande            | Effet                                          |
|---------------------|------------------------------------------------|
| `F <hz>`            | Set frequence VFO courante                     |
| `f`                 | Get frequence                                  |
| `M <mode> <bw>`     | Set mode (USB/LSB/CW/FM/AM/RTTY/PKTUSB...)     |
| `m`                 | Get mode + bandwidth                           |
| `V <vfo>`           | Set VFO active (VFOA/VFOB)                     |
| `v`                 | Get VFO active                                 |
| `S <split> <vfo>`   | Set split (cote pont, etat seulement)          |
| `s`                 | Get split                                      |
| `T <0|1>`           | Set PTT (v1 : accepte mais ignore)             |
| `t`                 | Get PTT (etat memorise cote pont)              |
| `\dump_state`       | Capability dump (WSJT-X au connect)            |
| `\chk_vfo`          | 0 (pas de targeting VFO requis)                |

## Limites v1

- **RX uniquement** : le PTT est accepte sans etre transmis a SDR Console.
  Suffisant pour decoder WSJT-X (FT8/Q65/JT65). TX en v2.
- **Reconnexion backend** automatique toutes les 5s si SDR Console tombe.
- **Pas de GUI** : config par YAML, status par logs console. Une integration
  dans l'app tracker EME est prevue en v2.

## Test rapide sans WSJT-X

Tu peux tester le pont avec `rigctl` (client Hamlib en ligne de commande) :

```cmd
rigctl -m 2 -r 127.0.0.1:4532
Rig command: f
14074000
Rig command: F 50313000
Rig command: m
USB
2400
```

## Environnement de test (sans SDR Console)

Un **mock SDR Console** est inclus pour tester toute la chaine sans le
hardware ni le logiciel SDR Console reel. Trois terminaux :

```cmd
# Terminal 1 : faux SDR Console (port 7300, TS-2000 minimal)
python -m sdr_bridge.mock_console -v

# Terminal 2 : le pont (config par defaut pointe vers 127.0.0.1:7300)
python -m sdr_bridge.main

# Terminal 3 : WSJT-X (ou rigctl) configure pour Hamlib NET rigctl :4532
```

Tu peux faire F/f, M/m, T/t depuis WSJT-X et voir le mock loguer les
changements de frequence/mode.

## Tests automatises

```cmd
pip install pytest pytest-asyncio
pytest
```

- `tests/test_translator.py` : tests unitaires du traducteur (15 tests).
- `tests/test_integration.py` : tests end-to-end mock + bridge + client
  rigctld TCP (5 tests). Verifie que F/M/T cote rigctld arrivent bien
  jusqu'au backend simule.
