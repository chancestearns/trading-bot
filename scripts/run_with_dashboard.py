"""Run the trading bot with web dashboard UI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.api.server import run_server, set_bot_instance
from bot.brokers.paper import PaperBroker
from bot.config import Config, load_config
from bot.data_providers.mock import MockDataProvider
from bot.engine.logging_config import setup_logging
from bot.engine.loop import TradingEngine
from bot.risk.enhanced import EnhancedRiskConfig, EnhancedRiskManager
from bot.strategies.example_sma import SimpleMovingAverageStrategy


def _build_components(config: Config):
    """Build all bot components."""
    data_provider = MockDataProvider(**config.engine.data_provider.params)
    broker = PaperBroker(starting_cash=config.engine.broker.starting_cash)
    strategy = SimpleMovingAverageStrategy()
    
    # Use enhanced risk manager with production features
    risk_cfg = EnhancedRiskConfig(
        max_position_size=config.engine.risk.max_position_size,
        max_daily_loss=config.engine.risk.max_daily_loss,
        max_total_exposure=config.engine.risk.max_total_exposure,
        max_open_positions=config.engine.risk.max_open_positions,
        starting_cash=config.engine.broker.starting_cash,
        enforce_pdt_rules=True,
        enable_circuit_breaker=True,
    )
    risk_manager = EnhancedRiskManager(risk_cfg)
    
    return data_provider, broker, strategy, risk_manager


async def run_bot(config: Config, iterations: int | None = None) -> None:
    """Run the trading bot."""
    data_provider, broker, strategy, risk_manager = _build_components(config)
    engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)
    
    # Set bot instance for API access
    set_bot_instance(engine)
    
    # Add start time for uptime tracking
    import datetime
    engine.start_time = datetime.datetime.utcnow()
    
    await engine.run(iterations=iterations)


def start_api_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the API server in a separate thread."""
    logging.info(f"Starting API server on {host}:{port}")
    run_server(host=host, port=port)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run the trading bot with web dashboard."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config JSON file"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API server port (default: 8000)"
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Run bot only, without web dashboard"
    )
    parser.add_argument(
        "--ui-only",
        action="store_true",
        help="Run UI server only, without bot (for development)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config(args.config)
        # Convert string level to logging constant
        log_level = getattr(logging, config.engine.logging.level.upper(), logging.INFO)
        setup_logging(log_level)
        logger = logging.getLogger(__name__)
        logger.info("Configuration loaded successfully")
    except Exception as e:
        print(f"ERROR: Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        if args.ui_only:
            # Run only the UI server (for development/testing)
            logger.info("Running in UI-only mode")
            start_api_server(args.host, args.port)
        elif args.bot_only:
            # Run only the bot without UI
            logger.info("Running in bot-only mode")
            asyncio.run(run_bot(config))
        else:
            # Run both bot and UI server
            logger.info("Starting trading bot with web dashboard")
            logger.info(f"Dashboard will be available at http://{args.host}:{args.port}")
            
            # Build bot components first
            data_provider, broker, strategy, risk_manager = _build_components(config)
            engine = TradingEngine(config, data_provider, broker, strategy, risk_manager)
            
            # Set bot instance for API access BEFORE starting server
            set_bot_instance(engine)
            
            # Add start time for uptime tracking
            import datetime
            engine.start_time = datetime.datetime.utcnow()
            
            # Start API server in background thread
            api_thread = threading.Thread(
                target=start_api_server,
                args=(args.host, args.port),
                daemon=True
            )
            api_thread.start()
            
            # Give the API server time to start
            import time
            time.sleep(2)
            
            # Run the bot in main thread
            logger.info("Bot initialization complete, starting main loop")
            asyncio.run(engine.run(iterations=None))
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
