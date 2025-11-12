"""Enhanced configuration with comprehensive validation."""

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


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


@dataclass(slots=True)
class DataProviderConfig:
    """Configuration for a data provider implementation."""

    name: str = "mock"
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ConfigValidationError("data_provider.name cannot be empty")


@dataclass(slots=True)
class BrokerConfig:
    """Configuration for a broker/execution implementation."""

    name: str = "paper"
    starting_cash: float = 100_000.0
    commission_per_share: float = 0.0
    commission_percent: float = 0.0
    slippage_percent: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ConfigValidationError("broker.name cannot be empty")
        if self.starting_cash <= 0:
            raise ConfigValidationError(
                f"broker.starting_cash must be positive, got {self.starting_cash}"
            )
        if self.commission_per_share < 0:
            raise ConfigValidationError("commission_per_share cannot be negative")
        if self.commission_percent < 0:
            raise ConfigValidationError("commission_percent cannot be negative")
        if self.slippage_percent < 0:
            raise ConfigValidationError("slippage_percent cannot be negative")


@dataclass(slots=True)
class RiskConfig:
    """Risk management related configuration values."""

    max_position_size: float = 1_000.0
    max_daily_loss: float = 5_000.0
    max_total_exposure: float = 50_000.0
    max_open_positions: int = 5
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.max_position_size < 0:
            raise ConfigValidationError("max_position_size cannot be negative")
        if self.max_daily_loss < 0:
            raise ConfigValidationError("max_daily_loss cannot be negative")
        if self.max_total_exposure < 0:
            raise ConfigValidationError("max_total_exposure cannot be negative")
        if self.max_open_positions < 1:
            raise ConfigValidationError("max_open_positions must be at least 1")


@dataclass(slots=True)
class StrategyConfig:
    """Configuration for a trading strategy."""

    name: str = "example_sma"
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ConfigValidationError("strategy.name cannot be empty")


@dataclass(slots=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "standard"
    file: Optional[str] = None

    def __post_init__(self):
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in valid_levels:
            raise ConfigValidationError(
                f"logging.level must be one of {valid_levels}, got {self.level}"
            )


@dataclass(slots=True)
class EngineConfig:
    """Runtime configuration for the trading engine."""

    mode: str = "backtest"
    symbols: List[str] = field(default_factory=lambda: ["AAPL"])
    timeframe: str = "1m"
    data_provider: DataProviderConfig = field(default_factory=DataProviderConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self):
        valid_modes = {"backtest", "paper", "live"}
        if self.mode not in valid_modes:
            raise ConfigValidationError(
                f"engine.mode must be one of {valid_modes}, got {self.mode}"
            )

        if not self.symbols:
            raise ConfigValidationError("engine.symbols cannot be empty")

        for symbol in self.symbols:
            if not symbol or not symbol.strip():
                raise ConfigValidationError(f"Invalid symbol: '{symbol}'")

        valid_timeframes = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
        if self.timeframe not in valid_timeframes:
            raise ConfigValidationError(
                f"engine.timeframe must be one of {valid_timeframes}, got {self.timeframe}"
            )


@dataclass(slots=True)
class Config:
    """Top level configuration container."""

    engine: EngineConfig = field(default_factory=EngineConfig)

    def validate(self) -> None:
        """Perform cross-field validation."""
        if self.engine.risk.max_daily_loss > self.engine.broker.starting_cash:
            raise ConfigValidationError(
                "risk.max_daily_loss cannot exceed broker.starting_cash"
            )

        if self.engine.risk.max_total_exposure > self.engine.broker.starting_cash * 2:
            raise ConfigValidationError(
                "risk.max_total_exposure seems unreasonably high relative to starting_cash"
            )


def load_config(path: Optional[Path | str] = None) -> Config:
    """Load configuration from JSON and environment overrides."""
    raw_config = _load_config_from_file(path)
    env_overrides = _extract_env_overrides()
    merged = _deep_merge(raw_config, env_overrides)
    config = _dict_to_config(merged)
    config.validate()
    return config


def _load_config_from_file(path: Optional[Path | str]) -> Dict[str, Any]:
    if path is not None:
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        return _read_config(path_obj)

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
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise ConfigValidationError(f"Invalid JSON in {path}: {e}")
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


def _insert_override(
    overrides: MutableMapping[str, Any], path_parts: List[str], value: str
) -> None:
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
    """Parse environment variable value to appropriate type."""
    if value.startswith("env:"):
        env_var = value[4:]
        return os.getenv(env_var, "")

    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

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
            data_provider=_make_dataclass(
                DataProviderConfig, engine_data.get("data_provider", {})
            ),
            broker=_make_dataclass(BrokerConfig, engine_data.get("broker", {})),
            strategy=_make_dataclass(StrategyConfig, engine_data.get("strategy", {})),
            risk=_make_dataclass(RiskConfig, engine_data.get("risk", {})),
            logging=_make_dataclass(LoggingConfig, engine_data.get("logging", {})),
        )
    )


def _make_dataclass(model_cls, values: Dict[str, Any]):
    if not isinstance(values, dict):
        raise TypeError(
            f"Expected mapping for {model_cls.__name__}, got {type(values)!r}"
        )

    import inspect

    sig = inspect.signature(model_cls)
    valid_fields = set(sig.parameters.keys())
    filtered_values = {k: v for k, v in values.items() if k in valid_fields}

    try:
        return model_cls(**filtered_values)
    except Exception as e:
        raise ConfigValidationError(f"Failed to create {model_cls.__name__}: {e}")


def mask_secrets(config: Config) -> Dict[str, Any]:
    """Create a dict representation with secrets masked for logging."""
    import copy
    import dataclasses

    def mask_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, value in d.items():
            key_lower = key.lower()
            if any(
                secret in key_lower for secret in ["key", "secret", "password", "token"]
            ):
                result[key] = "***"
            elif isinstance(value, dict):
                result[key] = mask_dict(value)
            elif dataclasses.is_dataclass(value):
                result[key] = mask_dict(dataclasses.asdict(value))
            else:
                result[key] = value
        return result

    return mask_dict(dataclasses.asdict(config))
