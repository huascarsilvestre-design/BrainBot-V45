# BRAIN5 V45 - Iniciar Servidor
# Doble click en este archivo para arrancar

$host.UI.RawUI.WindowTitle = "BRAIN5 V45 - CORRIENDO"
Set-Location $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  BRAIN5 V45 - Scalping Bot USDJPY" -ForegroundColor Green
Write-Host "  Capital: $100 | Lotes: 0.01" -ForegroundColor Green
Write-Host "  SL: 16 pips | TP: 25 pips | Trail: 8 pips" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nInstalando dependencias..." -ForegroundColor Yellow
py -m pip install -r requirements.txt

Write-Host "`nArranque del servidor BRAIN5 V45..." -ForegroundColor Green
Write-Host "Abre: http://127.0.0.1:8000/health" -ForegroundColor Cyan
Write-Host "Abre: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$env:PY_SYMBOL     = "USDJPY"
$env:PY_API_KEY    = ""
$env:PY_CAPITAL    = "100"
$env:PY_SL_PIPS    = "16"
$env:PY_TP_PIPS    = "25"
$env:PY_TRAIL      = "8"
$env:PY_LOTS       = "0.01"
$env:PY_MAX_SIGNAL = "20"
$env:PY_MAX_DAY    = "100"
$env:PY_LOSS_DAY   = "15.0"
$env:PY_LOSS_BATCH = "10.0"
$env:PY_GAIN_DAY   = "20.0"
$env:PY_SPREAD     = "1.2"
$env:PY_COOLDOWN   = "120"
$env:PY_CIRCUIT    = "3"
$env:PY_CIRC_MIN   = "30"

py -m uvicorn python_signal_server_v45:app --host 127.0.0.1 --port 8000 --reload
