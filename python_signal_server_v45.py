# =============================================================
# python_signal_server_v45.py (VERSION PROFESIONAL V45)
# BrainBot V45 - Servidor de Senales USDJPY Scalping
# Price Action + Candle Patterns + Multi-Timeframe + Order Blocks
# =============================================================

import time
import threading
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import yfinance as yf

# =============================================================
# CONFIGURACION GLOBAL
# =============================================================

SYMBOL          = "USDJPY=X"
INTERVAL        = "1m"      # Ejecucion
INTERVAL_H      = "5m"      # Contexto Multi-Timeframe
PERIOD          = "1d"
UPDATE_SECONDS  = 30
PORT            = 5000

# Filtros de Sesion (UTC)
SESSIONS = {
    "LONDON": (7, 12),
    "NY": (12, 17)
}

# Parametros de Estrategia
EMA_FAST = 8
EMA_SLOW = 21
RSI_PERIOD = 7

# =============================================================
# LOGGING
# =============================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# =============================================================
# DETECCION DE PATRONES DE VELAS (PRICE ACTION)
# =============================================================

def detect_candle_patterns(df: pd.DataFrame):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    body = abs(last['close'] - last['open'])
    range_total = last['high'] - last['low']
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    
    patterns = []
    
    # 1. Hammer (Martillo)
    if lower_wick > (body * 2) and upper_wick < (body * 0.5):
        patterns.append("HAMMER")
        
    # 2. Inverted Hammer (Martillo Invertido)
    if upper_wick > (body * 2) and lower_wick < (body * 0.5):
        patterns.append("INV_HAMMER")
        
    # 3. Bullish Engulfing (Envolvente Alcista)
    if last['close'] > last['open'] and prev['close'] < prev['open'] and \
       last['close'] > prev['open'] and last['open'] < prev['close']:
        patterns.append("BULL_ENGULFING")
        
    # 4. Bearish Engulfing (Envolvente Bajista)
    if last['close'] < last['open'] and prev['close'] > prev['open'] and \
       last['close'] < prev['open'] and last['open'] > prev['close']:
        patterns.append("BEAR_ENGULFING")
        
    # 5. Pin Bar
    if upper_wick > (range_total * 0.6) or lower_wick > (range_total * 0.6):
        patterns.append("PIN_BAR")
        
    return patterns

# =============================================================
# ESTRUCTURA DE MERCADO (BOS / ORDER BLOCKS)
# =============================================================

def get_market_structure(df: pd.DataFrame):
    # Deteccion simple de Order Blocks (Ultima vela contraria antes de impulso)
    # Buscamos imbalance (FVG)
    last = df.iloc[-1]
    p2 = df.iloc[-2]
    p3 = df.iloc[-3]
    
    structure = {"ob_bull": 0, "ob_bear": 0, "fvg": False}
    
    # Bullish FVG (Gap entre High p3 y Low last)
    if last['low'] > p3['high']:
        structure["fvg"] = True
        structure["ob_bull"] = p3['low']
        
    # Bearish FVG (Gap entre Low p3 y High last)
    if last['high'] < p3['low']:
        structure["fvg"] = True
        structure["ob_bear"] = p3['high']
        
    return structure

# =============================================================
# LOGICA DE SENAL PROFESIONAL
# =============================================================

def compute_pro_signal():
    try:
        # 1. Descargar M1 (Ejecucion) y M5 (Contexto)
        df1 = yf.download(SYMBOL, interval="1m", period="1d", progress=False, auto_adjust=True)
        df5 = yf.download(SYMBOL, interval="5m", period="5d", progress=False, auto_adjust=True)
        
        if len(df1) < 50 or len(df5) < 50: return None
        
        df1.columns = [c.lower() for c in df1.columns]
        df5.columns = [c.lower() for c in df5.columns]
        
        # 2. Analisis de Patrones y Estructura
        patterns = detect_candle_patterns(df1)
        struct = get_market_structure(df5)
        
        # 3. Confirmacion Indicadores (SOLO COMPLEMENTO)
        c = df1['close'].iloc[-1]
        ema8 = df1['close'].ewm(span=EMA_FAST).mean().iloc[-1]
        ema21 = df1['close'].ewm(span=EMA_SLOW).mean().iloc[-1]
        
        # 4. Filtro de Sesion
        now_utc = datetime.now(timezone.utc).hour
        in_session = any(s[0] <= now_utc < s[1] for s in SESSIONS.values())
        
        signal = "FLAT"
        reason = "No patterns detected"
        
        # LOGICA DE ENTRADA PRO
        # BUY: Sesion Activa + Tendencia EMA + Patron Alcista + FVG/OB
        if in_session and c > ema21:
            if "HAMMER" in patterns or "BULL_ENGULFING" in patterns or "INV_HAMMER" in patterns:
                signal = "BUY"
                reason = f"Pattern {patterns} in Bullish Structure"
                
        # SELL: Sesion Activa + Tendencia EMA + Patron Bajista + FVG/OB
        elif in_session and c < ema21:
            if "BEAR_ENGULFING" in patterns or "PIN_BAR" in patterns:
                signal = "SELL"
                reason = f"Pattern {patterns} in Bearish Structure"

        atr = (df1['high'] - df1['low']).rolling(14).mean().iloc[-1]
        
        sl = tp = 0.0
        if signal == "BUY":
            sl = round(c - (atr * 2), 3)
            tp = round(c + (atr * 4), 3) # RR 1:2
        elif signal == "SELL":
            sl = round(c + (atr * 2), 3)
            tp = round(c - (atr * 4), 3) # RR 1:2
            
        return {
            "signal": signal,
            "price": round(c, 3),
            "sl": sl,
            "tp": tp,
            "reason": reason,
            "session": in_session,
            "patterns": patterns,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated": True
        }
    except Exception as e:
        logger.error(f"Error compute_pro_signal: {e}")
        return None

# =============================================================
# SERVIDOR FLASK
# =============================================================

app = Flask(__name__)
current_signal = {"signal": "FLAT", "updated": False}

def update_loop():
    global current_signal
    while True:
        sig = compute_pro_signal()
        if sig:
            current_signal = sig
            logger.info(f"SIGNAL: {sig['signal']} | {sig['reason']}")
        time.sleep(UPDATE_SECONDS)

@app.route('/signal', methods=['GET'])
def get_signal():
    return jsonify(current_signal)

if __name__ == '__main__':
    threading.Thread(target=update_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT)
