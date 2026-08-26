import pytest

from manuedge.config import AgentConfig
from manuedge.drivers import build_driver
from manuedge.drivers.ads1263 import ADS1263Driver


def _cfg(**overrides):
    cfg = {
        "channels": [
            {"ain": 0, "modality": "bench_pot"},
            {"ain": 1, "modality": "bench_ldr"},
        ],
    }
    cfg.update(overrides)
    return cfg


def test_build_driver_selects_ads1263():
    driver = build_driver("ads1263", _cfg())
    assert isinstance(driver, ADS1263Driver)


def test_ads1263_describe_matches_channels():
    driver = build_driver("ads1263", _cfg(loop_hz=100))
    specs = driver.describe()
    assert [s.modality for s in specs] == ["bench_pot", "bench_ldr"]
    assert [s.stream_id for s in specs] == ["ads1263:ain0", "ads1263:ain1"]
    assert all(s.hz == 100 for s in specs)


def test_ads1263_rejects_unsupported_gain():
    with pytest.raises(ValueError):
        build_driver("ads1263", _cfg(gain=3))


def test_build_driver_unknown_name_raises():
    with pytest.raises(ValueError):
        build_driver("does-not-exist", {})


def test_agent_config_pi_model_defaults_and_parses():
    default_cfg = AgentConfig.from_dict({"node_id": "n1"})
    assert default_cfg.pi_model == "pi4"

    pi3_cfg = AgentConfig.from_dict({"node_id": "n1", "pi_model": "pi3"})
    assert pi3_cfg.pi_model == "pi3"
