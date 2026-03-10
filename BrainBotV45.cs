// ============================================================
// BrainBotV45.cs
// Scalping Bot V45 - USDJPY - Price Action Cuantificado
// Capital: $100 | Framework: cTrader C# API
// Consume senales de: http://localhost:5000/signal
// ============================================================

using System;
using System.Net.Http;
using System.Threading.Tasks;
using System.Text.Json;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class BrainBotV45 : Robot
    {
        // ===================================================
        // PARAMETROS DE CONFIGURACION
        // ===================================================

        [Parameter("Risk % per Trade", DefaultValue = 1.0, MinValue = 0.1, MaxValue = 5.0)]
        public double RiskPercent { get; set; }

        [Parameter("Max Spread (pips)", DefaultValue = 2.0, MinValue = 0.5, MaxValue = 10.0)]
        public double MaxSpreadPips { get; set; }

        [Parameter("Signal Server URL", DefaultValue = "http://localhost:5000/signal")]
        public string SignalServerUrl { get; set; }

        [Parameter("Update Interval (sec)", DefaultValue = 30, MinValue = 10, MaxValue = 300)]
        public int UpdateIntervalSec { get; set; }

        [Parameter("Trade Label", DefaultValue = "BrainV45")]
        public string TradeLabel { get; set; }

        [Parameter("Enable Trailing Stop", DefaultValue = true)]
        public bool EnableTrailingStop { get; set; }

        [Parameter("Trailing Start (pips)", DefaultValue = 15.0, MinValue = 5.0)]
        public double TrailingStartPips { get; set; }

        [Parameter("Trailing Step (pips)", DefaultValue = 5.0, MinValue = 1.0)]
        public double TrailingStepPips { get; set; }

        // ===================================================
        // VARIABLES PRIVADAS
        // ===================================================

        private HttpClient _httpClient;
        private DateTime _lastSignalCheck;
        private string _lastSignal = "FLAT";
        private double _lastPrice = 0.0;
        private Timer _timer;

        // ===================================================
        // CLASE PARA DESERIALIZAR JSON DE PYTHON
        // ===================================================

        private class SignalData
        {
            public string signal { get; set; }      // BUY | SELL | FLAT
            public double price { get; set; }
            public double sl { get; set; }
            public double tp { get; set; }
            public double atr { get; set; }
            public double rsi { get; set; }
            public double ema_fast { get; set; }
            public double ema_slow { get; set; }
            public double bb_upper { get; set; }
            public double bb_lower { get; set; }
            public string timestamp { get; set; }
            public bool updated { get; set; }
        }

        // ===================================================
        // METODOS DEL CICLO DE VIDA
        // ===================================================

        protected override void OnStart()
        {
            Print("=============================================");
            Print("  BrainBot V45 - USDJPY Scalping Bot");
            Print("  Capital: $100 | Risk: {0}%", RiskPercent);
            Print("  Signal Server: {0}", SignalServerUrl);
            Print("=============================================");

            _httpClient = new HttpClient();
            _httpClient.Timeout = TimeSpan.FromSeconds(10);
            _lastSignalCheck = DateTime.MinValue;

            // Timer para consultar senales periodicamente
            _timer = new Timer(TimeSpan.FromSeconds(UpdateIntervalSec), OnTimerTick);
            _timer.Start();

            Print("[OK] Bot iniciado correctamente.");
            Print("[INFO] Consultando servidor cada {0} segundos...", UpdateIntervalSec);
        }

        protected override void OnStop()
        {
            _timer?.Stop();
            _timer?.Dispose();
            _httpClient?.Dispose();

            Print("=============================================");
            Print("  BrainBot V45 detenido.");
            Print("=============================================");
        }

        protected override void OnTick()
        {
            // Actualizar trailing stop si esta habilitado
            if (EnableTrailingStop)
            {
                UpdateTrailingStops();
            }
        }

        // ===================================================
        // TIMER: CONSULTAR SENALES DEL SERVIDOR PYTHON
        // ===================================================

        private void OnTimerTick()
        {
            Task.Run(async () =>
            {
                try
                {
                    var signalData = await FetchSignalAsync();
                    if (signalData != null && signalData.updated)
                    {
                        BeginInvokeOnMainThread(() => ProcessSignal(signalData));
                    }
                }
                catch (Exception ex)
                {
                    Print("[ERROR] Error consultando servidor: {0}", ex.Message);
                }
            });
        }

        // ===================================================
        // CONSULTAR SERVIDOR PYTHON VIA HTTP
        // ===================================================

        private async Task<SignalData> FetchSignalAsync()
        {
            try
            {
                var response = await _httpClient.GetAsync(SignalServerUrl);
                if (!response.IsSuccessStatusCode)
                {
                    Print("[WARN] Respuesta HTTP: {0}", response.StatusCode);
                    return null;
                }

                var jsonString = await response.Content.ReadAsStringAsync();
                var signalData = JsonSerializer.Deserialize<SignalData>(jsonString);

                return signalData;
            }
            catch (Exception ex)
            {
                Print("[ERROR] FetchSignalAsync: {0}", ex.Message);
                return null;
            }
        }

        // ===================================================
        // PROCESAR SENAL Y EJECUTAR OPERACIONES
        // ===================================================

        private void ProcessSignal(SignalData data)
        {
            if (data == null) return;

            Print("[SIGNAL] {0} | Price: {1} | SL: {2} | TP: {3} | RSI: {4} | ATR: {5}",
                  data.signal, data.price, data.sl, data.tp, data.rsi, data.atr);

            // Filtro de spread
            var currentSpread = Symbol.Spread / Symbol.PipSize;
            if (currentSpread > MaxSpreadPips)
            {
                Print("[SKIP] Spread muy alto: {0:F2} pips (max: {1})", currentSpread, MaxSpreadPips);
                return;
            }

            // Si hay senal nueva diferente a FLAT
            if (data.signal != _lastSignal && data.signal != "FLAT")
            {
                // Cerrar posiciones opuestas
                CloseOppositePositions(data.signal);

                // Abrir nueva posicion si no hay posiciones abiertas del mismo lado
                if (!HasOpenPosition(data.signal))
                {
                    OpenPosition(data.signal, data.sl, data.tp);
                }

                _lastSignal = data.signal;
            }
            else if (data.signal == "FLAT")
            {
                // Opcionalmente cerrar todas las posiciones cuando FLAT
                // CloseAllPositions();
                _lastSignal = "FLAT";
            }

            _lastPrice = data.price;
        }

        // ===================================================
        // ABRIR POSICION CON GESTION DE RIESGO
        // ===================================================

        private void OpenPosition(string signal, double slPrice, double tpPrice)
        {
            var tradeType = signal == "BUY" ? TradeType.Buy : TradeType.Sell;
            var volumeLots = CalculateVolume(slPrice, tradeType);

            if (volumeLots <= 0)
            {
                Print("[ERROR] Volumen calculado invalido: {0}", volumeLots);
                return;
            }

            var result = ExecuteMarketOrder(tradeType, SymbolName, Symbol.NormalizeVolumeInUnits(volumeLots),
                                            TradeLabel, null, null);

            if (result.IsSuccessful)
            {
                var position = result.Position;

                // Ajustar SL y TP
                ModifyPosition(position, slPrice, tpPrice);

                Print("[OPEN] {0} | Vol: {1} | SL: {2} | TP: {3}",
                      signal, volumeLots, slPrice, tpPrice);
            }
            else
            {
                Print("[ERROR] Fallo al abrir posicion: {0}", result.Error);
            }
        }

        // ===================================================
        // CALCULAR VOLUMEN BASADO EN RIESGO %
        // ===================================================

        private double CalculateVolume(double slPrice, TradeType tradeType)
        {
            var balance = Account.Balance;
            var riskAmount = balance * (RiskPercent / 100.0);

            var currentPrice = tradeType == TradeType.Buy ? Symbol.Ask : Symbol.Bid;
            var slDistancePips = Math.Abs(currentPrice - slPrice) / Symbol.PipSize;

            if (slDistancePips <= 0)
                return Symbol.VolumeInUnitsMin;

            var pipValue = Symbol.PipValue;
            var volumeLots = riskAmount / (slDistancePips * pipValue);

            // Normalizar volumen
            volumeLots = Math.Max(volumeLots, Symbol.VolumeInUnitsMin);
            volumeLots = Math.Min(volumeLots, Symbol.VolumeInUnitsMax);

            return Symbol.NormalizeVolumeInUnits(volumeLots);
        }

        // ===================================================
        // CERRAR POSICIONES OPUESTAS
        // ===================================================

        private void CloseOppositePositions(string signal)
        {
            var targetType = signal == "BUY" ? TradeType.Sell : TradeType.Buy;

            foreach (var pos in Positions)
            {
                if (pos.Label == TradeLabel && pos.TradeType == targetType)
                {
                    ClosePosition(pos);
                    Print("[CLOSE] Posicion opuesta cerrada: {0}", pos.TradeType);
                }
            }
        }

        // ===================================================
        // VERIFICAR SI HAY POSICION ABIERTA DEL MISMO TIPO
        // ===================================================

        private bool HasOpenPosition(string signal)
        {
            var targetType = signal == "BUY" ? TradeType.Buy : TradeType.Sell;

            foreach (var pos in Positions)
            {
                if (pos.Label == TradeLabel && pos.TradeType == targetType)
                    return true;
            }

            return false;
        }

        // ===================================================
        // CERRAR TODAS LAS POSICIONES
        // ===================================================

        private void CloseAllPositions()
        {
            foreach (var pos in Positions)
            {
                if (pos.Label == TradeLabel)
                {
                    ClosePosition(pos);
                }
            }
        }

        // ===================================================
        // TRAILING STOP DINAMICO
        // ===================================================

        private void UpdateTrailingStops()
        {
            foreach (var pos in Positions)
            {
                if (pos.Label != TradeLabel)
                    continue;

                var trailingStartPrice = pos.TradeType == TradeType.Buy
                    ? pos.EntryPrice + TrailingStartPips * Symbol.PipSize
                    : pos.EntryPrice - TrailingStartPips * Symbol.PipSize;

                var currentPrice = pos.TradeType == TradeType.Buy ? Symbol.Bid : Symbol.Ask;

                if (pos.TradeType == TradeType.Buy && currentPrice >= trailingStartPrice)
                {
                    var newSL = currentPrice - TrailingStepPips * Symbol.PipSize;
                    if (pos.StopLoss == null || newSL > pos.StopLoss)
                    {
                        ModifyPosition(pos, newSL, pos.TakeProfit);
                    }
                }
                else if (pos.TradeType == TradeType.Sell && currentPrice <= trailingStartPrice)
                {
                    var newSL = currentPrice + TrailingStepPips * Symbol.PipSize;
                    if (pos.StopLoss == null || newSL < pos.StopLoss)
                    {
                        ModifyPosition(pos, newSL, pos.TakeProfit);
                    }
                }
            }
        }
    }
}
