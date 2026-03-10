# =============================================================
# python_signal_server_v45.py
# BrainBot V45 - Servidor de Senales USDJPY Scalping
# Cuantified Price Action - Capital $100
# Puerto: 5000 | Framework: Flask + TA-Lib + yfinance
# =============================================================

import time
import threading
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import pandas as pd
import numpy as np

# --- Intentar importar librerias opcionales ---
try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False

try:
    import talib
    TALIB_OK = True
except ImportError:
    TALIB_OK = False

# =============================================================
# CONFIGURACION GLOBAL
# =============================================================

SYMBOL          = "USDJPY=X"
INTERVAL        = "1m"
PERIOD          = "1d"
UPDATE_SECONDS  = 30        # refrescar datos cada 30 seg
PORT            = 5000

# Parametros de la estrategia V45
EMA_FAST        = 8
EMA_SLOW        = 21
RSI_PERIOD      = 7
RSI_OB          = 70        # sobrecompra
RSI_OS          = 30        # sobreventa
ATR_PERIOD      = 14
BB_PERIOD       = 20
BB_STD          = 2.0
MIN_ATR_PIPS    = 0.03      # ATR minimo en pips para operar
SL_ATR_MULT     = 1.5       # SL = ATR * multiplicador
TP_ATR_MULT     = 2.5       # TP = ATR * multiplicador

# =============================================================
# LOGGING
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================
# ESTADO GLOBAL DE LA SENAL
# =============================================================

signal_state = {
    "signal"    : "FLAT",   # BUY | SELL | FLAT
    "price"     : 0.0,
    "sl"        : 0.0,
    "tp"        : 0.0,
    "atr"       : 0.0,
    "rsi"       : 0.0,
    "ema_fast"  : 0.0,
    "ema_slow"  : 0.0,
    "bb_upper"  : 0.0,
    "bb_lower"  : 0.0,
    "timestamp" : "",
    "updated"   : False
}
state_lock = threading.Lock()

# =============================================================
# FUNCIONES DE INDICADORES (sin TA-Lib si no esta disponible)
# =============================================================

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series: pd.Series, period: int) -> pd.Series:
    delta  = series.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_g  = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l  = loss.ewm(com=period - 1, adjust=False).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()

def calc_bb(series: pd.Series, period: int, std_mult: float):
    ma    = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    return ma + std_mult * sigma, ma - std_mult * sigma

# =============================================================
# DESCARGA DE DATOS
# =============================================================

def fetch_data() -> pd.DataFrame | None:
    if not YFINANCE_OK:
        logger.warning("yfinance no disponible - usando datos simulados")
        return _simulated_data()
    try:
        df = yf.download(
            SYMBOL, interval=INTERVAL,
            period=PERIOD, progress=False,
            auto_adjust=True
        )
        if df is None or len(df) < 50:
            logger.warning("Datos insuficientes de yfinance")
            return None
        df.columns = [c.lower() for c in df.columns]
        df.dropna(inplace=True)
        return df
    except Exception as e:
        logger.error(f"Error descargando datos: {e}")
        return None

def _simulated_data() -> pd.DataFrame:
    """Genera OHLCV simulado para pruebas sin internet."""
    np.random.seed(int(time.time()) % 1000)
    n     = 200
    close = 145.0 + np.cumsum(np.random.randn(n) * 0.02)
    high  = close + np.random.rand(n) * 0.05
    low   = close - np.random.rand(n) * 0.05
    vol   = np.random.randint(1000, 5000, n).astype(float)
    idx   = pd.date_range(end=pd.Timestamp.utcnow(), periods=n, freq='1min', tz='UTC')
    return pd.DataFrame({'open': close, 'high': high,
                         'low': low,   'close': close,
                         'volume': vol}, index=idx)

# =============================================================
# LOGICA DE SENAL
# =============================================================

def compute_signal(df: pd.DataFrame) -> dict:
    close  = df['close']
    high   = df['high']
    low    = df['low']

    ema_f  = calc_ema(close, EMA_FAST)
    ema_s  = calc_ema(close, EMA_SLOW)
    rsi    = calc_rsi(close, RSI_PERIOD)
    atr    = calc_atr(high, low, close, ATR_PERIOD)
    bb_up, bb_dn = calc_bb(close, BB_PERIOD, BB_STD)

    # Valores actuales
    c      = float(close.iloc[-1])
    ef     = float(ema_f.iloc[-1])
    es     = float(ema_s.iloc[-1])
    r      = float(rsi.iloc[-1])
    a      = float(atr.iloc[-1])
    bbu    = float(bb_up.iloc[-1])
    bbl    = float(bb_dn.iloc[-1])

    # Valores previos
    ef1    = float(ema_f.iloc[-2])
    es1    = float(ema_s.iloc[-2])

    # Filtro de volatilidad
    if a < MIN_ATR_PIPS:
        sig = "FLAT"
    elif ef > es and ef1 <= es1 and r < RSI_OB and c > bbl:
        # Cruce alcista EMA + RSI no sobrecomprado + precio sobre BB inferior
        sig = "BUY"
    elif ef < es and ef1 >= es1 and r > RSI_OS and c < bbu:
        # Cruce bajista EMA + RSI no sobrevendido + precio bajo BB superior
        sig = "SELL"
    else:
        sig = "FLAT"

    sl = tp = 0.0
    if sig == "BUY":
        sl = round(c - a * SL_ATR_MULT, 3)
        tp = round(c + a * TP_ATR_MULT, 3)
    elif sig == "SELL":
        sl = round(c + a * SL_ATR_MULT, 3)
        tp = round(c - a * TP_ATR_MULT, 3)

    return {
        "signal"   : sig,
        "price"    : round(c,   3),
        "sl"       : sl,
        "tp"       : tp,
        "atr"      : round(a,   5),
        "rsi"      : round(r,   2),
        "ema_fast" : round(ef,  3),
        "ema_slow" : round(es,  3),
        "bb_upper" : round(bbu, 3),
        "bb_lower" : round(bbl, 3),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated"  : True
    }

# =============================================================
# HILO DE ACTUALIZACION
# =============================================================

def update_loop():
    global signal_state
    while True:
        try:
            df = fetch_data()
            if df is not None and len(df) >= max(EMA_SLOW, BB_PERIOD, ATR_PERIOD) + 5:
                result = compute_signal(df)
                with state_lock:
                    signal_state.update(result)
                logger.info(
                    f"[{result['timestamp']}] SENAL={result['signal']} "
                    f"P={result['price']} SL={result['sl']} TP={result['tp']} "
                    f"RSI={result['rsi']} ATR={result['atr']:.5f}"
                )
            else:
                logger.warning("No se pudo actualizar la senal - datos insuficientes")
        except Exception as e:
            logger.error(f"Error en update_loop: {e}")
        time.sleep(UPDATE_SECONDS)

# =============================================================
# FLASK APP
# =============================================================

app = Flask(__name__)

@app.route('/signal', methods=['GET'])
def get_signal():
    with state_lock:
        data = dict(signal_state)
    return jsonify(data)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

@app.route('/status', methods=['GET'])
def status():
    with state_lock:
        data = dict(signal_state)
    return jsonify({
        "server"   : "BrainBot-V45 Signal Server",
        "symbol"   : SYMBOL,
        "interval" : INTERVAL,
        "last_sig" : data.get("signal", "FLAT"),
        "last_ts"  : data.get("timestamp", ""),
        "yfinance" : YFINANCE_OK,
        "talib"    : TALIB_OK,
    })

# =============================================================
# ENTRADA PRINCIPAL
# =============================================================

if __name__ == '__main__':
    logger.info("=== BrainBot V45 Signal Server arrancando ===")
    logger.info(f"Simbolo: {SYMBOL} | Intervalo: {INTERVAL} | Puerto: {PORT}")
    logger.info(f"yfinance: {'OK' if YFINANCE_OK else 'NO INSTALADO'}")
    logger.info(f"TA-Lib  : {'OK' if TALIB_OK   else 'NO INSTALADO (usando fallback puro)'}") 

    # Lanzar hilo de actualizacion
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()
    logger.info(f"Hilo de actualizacion iniciado (cada {UPDATE_SECONDS}s)")

    # Esperar primera actualizacion
    time.sleep(5)

    # Iniciar servidor Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
