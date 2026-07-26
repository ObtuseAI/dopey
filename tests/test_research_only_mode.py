"""Tests: research-only default mode + import smoke (tests 1, 2, 12)."""
import dopey_core, dopey_options, dopey_edge, dopey_data, dopey_strategy_lab
import dopey_execution, dopey_governor, dopey_oss_miner
from dopey_core.config import load_config, default_config_path


def test_dopey_imports():
    assert dopey_core.DOPEY_VERSION == "0.1.0"
    assert dopey_core.BLUNDER_LINEAGE_VERSION == "1.0.0"


def test_default_mode_is_research():
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["robinhood_mcp_discovery_enabled"] is False
