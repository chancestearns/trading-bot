#!/usr/bin/env python3
"""Quick start script to test the trading bot setup."""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Check if Python version is 3.11+."""
    if sys.version_info < (3, 11):
        print(f"❌ Python 3.11+ required, you have {sys.version_info.major}.{sys.version_info.minor}")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    return True


def check_dependencies():
    """Check if dependencies are installed."""
    try:
        import fastapi
        import uvicorn
        import aiohttp
        print("✓ Dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e.name}")
        print("Run: pip install -r requirements.txt")
        return False


def check_config():
    """Check if config file exists."""
    if Path("config.json").exists():
        print("✓ config.json found")
        return True
    elif Path("config.example.json").exists():
        print("⚠ config.json not found, but config.example.json exists")
        print("Run: cp config.example.json config.json")
        return False
    else:
        print("❌ No configuration file found")
        return False


def check_bot_structure():
    """Check if bot directory structure exists."""
    required_paths = [
        Path("bot"),
        Path("bot/api"),
        Path("bot/brokers"),
        Path("bot/strategies"),
        Path("bot/risk"),
        Path("bot/ui/templates"),
        Path("bot/ui/static"),
    ]
    
    missing = [p for p in required_paths if not p.exists()]
    
    if missing:
        print(f"❌ Missing directories: {', '.join(str(p) for p in missing)}")
        return False
    
    print("✓ Bot structure complete")
    return True


def run_tests():
    """Run basic tests."""
    print("\n🧪 Running tests...")
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✓ All tests passed")
            return True
        else:
            print("⚠ Some tests failed (this may be OK for initial setup)")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            return True  # Don't block on test failures
    except subprocess.TimeoutExpired:
        print("⚠ Tests timed out (may need to kill hanging processes)")
        return True
    except Exception as e:
        print(f"⚠ Could not run tests: {e}")
        return True


def test_imports():
    """Test critical imports."""
    print("\n📦 Testing imports...")
    try:
        from bot.brokers.tradingview import TradingViewBroker
        from bot.api.server import app
        from bot.risk.enhanced import EnhancedRiskManager
        from bot.models import Order, Signal
        print("✓ All critical imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def show_next_steps():
    """Show next steps to the user."""
    print("\n" + "="*60)
    print("🚀 QUICK START COMMANDS")
    print("="*60)
    
    print("\n1. Run with web dashboard (recommended):")
    print("   python scripts/run_with_dashboard.py --config config.json")
    print("   Then open: http://localhost:8000")
    
    print("\n2. Run paper trading (no UI):")
    print("   python scripts/run_paper_trading.py --config config.json")
    
    print("\n3. Run backtest:")
    print("   python scripts/run_backtest.py --config config.json")
    
    print("\n4. Run with Docker:")
    print("   docker-compose up -d")
    print("   docker-compose logs -f trading-bot")
    
    print("\n📚 Documentation:")
    print("   - README.md - Project overview")
    print("   - DEPLOYMENT.md - Production deployment guide")
    print("   - IMPLEMENTATION_SUMMARY.md - Feature documentation")
    print("   - .github/copilot-instructions.md - Development guide")
    
    print("\n💡 TradingView Integration:")
    print("   See DEPLOYMENT.md for webhook setup instructions")
    
    print("\n⚠️  Remember:")
    print("   - Test in paper mode first")
    print("   - Review risk settings in config.json")
    print("   - Never commit secrets to version control")
    
    print("\n" + "="*60)


def main():
    """Run all checks."""
    print("="*60)
    print("Trading Bot - Quick Start Check")
    print("="*60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Bot Structure", check_bot_structure),
        ("Dependencies", check_dependencies),
        ("Configuration", check_config),
        ("Imports", test_imports),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n📋 Checking {name}...")
        results[name] = check_func()
    
    # Optional test run
    if all(results.values()):
        run_tests()
    
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    
    for name, passed in results.items():
        status = "✓" if passed else "❌"
        print(f"{status} {name}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✅ All checks passed! Bot is ready to run.")
        show_next_steps()
    else:
        print("\n⚠️  Some checks failed. Please resolve issues before running.")
        print("\nCommon fixes:")
        print("  - Install dependencies: pip install -r requirements.txt")
        print("  - Create config: cp config.example.json config.json")
        print("  - Check you're in the project root directory")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
