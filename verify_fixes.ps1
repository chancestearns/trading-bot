# Test Fixes Verification Script
# Run this in PowerShell to verify the 3 bug fixes

Write-Host "Testing bug fixes..." -ForegroundColor Cyan
Write-Host ""

# Change to project directory
Set-Location "C:\Users\Chance\Documents\trading-bot-main"

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

Write-Host "Running Position.update() tests..." -ForegroundColor Yellow
pytest tests\test_enhanced_models.py::TestPositionManagement::test_position_update_reduce -v
pytest tests\test_enhanced_models.py::TestPositionManagement::test_position_reversal -v

Write-Host ""
Write-Host "Running EnhancedRiskManager position size test..." -ForegroundColor Yellow  
pytest tests\test_risk_enhanced.py::TestEnhancedRiskManager::test_position_size_limit -v

Write-Host ""
Write-Host "Running all tests..." -ForegroundColor Yellow
pytest tests\ -v

Write-Host ""
Write-Host "Test verification complete!" -ForegroundColor Green
