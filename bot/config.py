"""Configuration loading and validation utilities for the trading bot."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Optional


CONFIG_ENV_PREFIX = "TRADING_BOT__"
DEFAULT_CONFIG_PATHS = (
    Path("config.json"),
    Path("config.yaml"),
    Path("config.yml"),
    Path("config.example.json"),
)


@dataclass(slots=True)
class DataProviderConfig:
    """Configuration for a data provider implementation."""

    name: str = "mock"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrokerConfig:
    """Configuration for a broker/execution implementation."""

    name: str = "paper"
    starting_cash: float = 100_000.0
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RiskConfig:
    """Risk management related configuration values."""

    max_position_size: float = 1_000.0
    max_daily_loss: float = 5_000.0
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyConfig:
    """Configuration for a trading strategy."""

    name: str = "example_sma"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EngineConfig:
    """Runtime configuration for the trading engine."""

    mode: str = "backtest"  # backtest | paper | live (placeholder for live)
    symbols: List[str] = field(default_factory=lambda: ["AAPL"])
    timeframe: str = "1m"
    data_provider: DataProviderConfig = field(default_factory=DataProviderConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)


@dataclass(slots=True)
class Config:
    """Top level configuration container."""

    engine: EngineConfig = field(default_factory=EngineConfig)


def load_config(path: Optional[Path | str] = None) -> Config:
    """Load configuration from JSON and environment overrides.

    Parameters
    ----------
    path:
        Optional path to a JSON configuration file. If not provided the loader
        will search ``DEFAULT_CONFIG_PATHS`` in order.
    """

    raw_config = _load_config_from_file(path)
    env_overrides = _extract_env_overrides()
    merged = _deep_merge(raw_config, env_overrides)
    return _dict_to_config(merged)


def _load_config_from_file(path: Optional[Path | str]) -> Dict[str, Any]:
    if path is not None:
        return _read_config(Path(path))

    for candidate in DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return _read_config(candidate)

    return {"engine": {}}


def _read_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        content = handle.read().strip()
        if not content:
            return {"engine": {}}
        if path.suffix.lower() == ".json":
            return json.loads(content)
        msg = (
            "Only JSON configuration files are supported in the reference "
            "implementation. Please convert your YAML file to JSON or extend "
            "the loader."
        )
        raise ValueError(msg)


def _extract_env_overrides() -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    prefix_length = len(CONFIG_ENV_PREFIX)
    for env_key, value in os.environ.items():
        if not env_key.startswith(CONFIG_ENV_PREFIX):
            continue
        path_parts = env_key[prefix_length:].split("__")
        if not path_parts:
            continue
        _insert_override(overrides, path_parts, value)
    return overrides


def _insert_override(overrides: MutableMapping[str, Any], path_parts: List[str], value: str) -> None:
    current: MutableMapping[str, Any] = overrides
    for part in path_parts[:-1]:
        key = part.lower()
        next_node = current.get(key)
        if not isinstance(next_node, MutableMapping):
            next_node = {}
            current[key] = next_node
        current = next_node
    current[path_parts[-1].lower()] = _parse_env_value(value)


def _parse_env_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _deep_merge(original: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = dict(original)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_config(data: Dict[str, Any]) -> Config:
    engine_data = data.get("engine", {})
    return Config(
        engine=EngineConfig(
            mode=engine_data.get("mode", "backtest"),
            symbols=list(engine_data.get("symbols", ["AAPL"])),
            timeframe=engine_data.get("timeframe", "1m"),
            data_provider=_make_dataclass(DataProviderConfig, engine_data.get("data_provider", {})),
            broker=_make_dataclass(BrokerConfig, engine_data.get("broker", {})),
            strategy=_make_dataclass(StrategyConfig, engine_data.get("strategy", {})),
            risk=_make_dataclass(RiskConfig, engine_data.get("risk", {})),
        )
    )


def _make_dataclass(model_cls, values: Dict[str, Any]):
    if not isinstance(values, dict):
        raise TypeError(f"Expected mapping for {model_cls.__name__}, got {type(values)!r}")
    return model_cls(**values)
