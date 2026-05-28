"""Tests unitaires du traducteur rigctld <-> Kenwood TS-2000."""

import pytest

from sdr_bridge.translator import Translator


def test_set_freq_vfo_a():
    assert Translator.set_freq_cat(14074000, "VFOA") == "FA00014074000;"


def test_set_freq_vfo_a_default():
    assert Translator.set_freq_cat(50313000) == "FA00050313000;"


def test_set_freq_vfo_b():
    assert Translator.set_freq_cat(14074000, "VFOB") == "FB00014074000;"


def test_set_freq_uhf():
    # 432.123 MHz
    assert Translator.set_freq_cat(432_123_000, "VFOA") == "FA00432123000;"


def test_get_freq_cmd():
    assert Translator.get_freq_cat("VFOA") == "FA;"
    assert Translator.get_freq_cat("VFOB") == "FB;"


def test_parse_freq_resp():
    assert Translator.parse_freq_resp("FA00014074000;") == 14074000
    assert Translator.parse_freq_resp("FB00432123000;") == 432123000


def test_parse_freq_invalid():
    with pytest.raises(ValueError):
        Translator.parse_freq_resp("XX;")
    with pytest.raises(ValueError):
        Translator.parse_freq_resp("FA123;")  # trop court


def test_set_mode_usb():
    assert Translator.set_mode_cat("USB") == "MD2;"


def test_set_mode_lsb():
    assert Translator.set_mode_cat("LSB") == "MD1;"


def test_set_mode_pktusb_data_to_usb():
    # WSJT-X envoie souvent PKTUSB -> on traduit en USB cote SDR
    assert Translator.set_mode_cat("PKTUSB") == "MD2;"


def test_set_mode_unknown_fallback():
    # Mode inconnu -> fallback USB (warning logge)
    assert Translator.set_mode_cat("BIZARRE") == "MD2;"


def test_parse_mode_resp_usb():
    assert Translator.parse_mode_resp("MD2;") == "USB"


def test_parse_mode_resp_cw():
    assert Translator.parse_mode_resp("MD3;") == "CW"


def test_parse_mode_resp_invalid():
    with pytest.raises(ValueError):
        Translator.parse_mode_resp("ZZ;")


def test_translator_state_defaults():
    t = Translator()
    assert t.ptt_state == 0
    assert t.split_state == 0
    assert t.current_vfo == "VFOA"
    assert t.cached_mode == "USB"
