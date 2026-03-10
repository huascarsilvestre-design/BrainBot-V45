// ============================================================
// BrainBotV45_PRO.cs
// Scalping Bot V45 PRO - USDJPY - Price Action & Candlestick Patterns
// Capital: $100 | Consume senales de: http://localhost:5000/signal
// ============================================================

using System;
using System.Net.Http;
using System.Threading.Tasks;
using System.Text.Json;
using cAlgo.API;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class BrainBotV45 : Robot
    {
        [Parameter("Risk % per Trade", DefaultValue = 1.0, MinValue = 0.1, MaxValue = 5.0)]
        public double RiskPercent { get; set; }

        [Parameter("Max Spread (pips)", DefaultValue = 1.5, MinValue = 0.5)]
        public double MaxSpread { get; set; }

        private HttpClient _httpClient;
        private string _lastTimestamp = "";

        private class SignalData
        {
            public string signal { get; set; }
            public double price { get; set; }
            public double sl { get; set; }
            public double tp { get; set; }
            public string reason { get; set; }
            public string timestamp { get; set; }
            public bool updated { get; set; }
        }

        protected override void OnStart()
        {
            _httpClient = new HttpClient();
            Timer.Start(30);
            Print("BrainBot V45 PRO - Iniciado con Price Action");
        }

        protected override void OnTimer()
        {
            CheckSignal();
        }

        private async void CheckSignal()
        {
            try
            {
                var response = await _httpClient.GetStringAsync("http://localhost:5000/signal");
                var data = JsonSerializer.Deserialize<SignalData>(response);

                if (data != null && data.updated && data.timestamp != _lastTimestamp)
                {
                    _lastTimestamp = data.timestamp;
                    ProcessSignal(data);
                }
            }
            catch (Exception ex) { Print(ex.Message); }
        }

        private void ProcessSignal(SignalData data)
        {
            if (Symbol.Spread / Symbol.PipSize > MaxSpread) return;

            var tradeType = data.signal == "BUY" ? TradeType.Buy : data.signal == "SELL" ? TradeType.Sell : (TradeType?)null;
            if (tradeType == null) return;

            // Gestion de Riesgo
            double volume = CalculateVolume(data.sl);
            
            ExecuteMarketOrder(tradeType.Value, SymbolName, Symbol.NormalizeVolumeInUnits(volume), "V45_PRO", data.sl, data.tp);
            Print("OPERACION: {0} | MOTIVO: {1}", data.signal, data.reason);
        }

        private double CalculateVolume(double slPrice)
        {
            var riskAmount = Account.Balance * (RiskPercent / 100.0);
            var slPips = Math.Abs(Symbol.Ask - slPrice) / Symbol.PipSize;
            if (slPips == 0) return Symbol.VolumeInUnitsMin;
            var volume = riskAmount / (slPips * Symbol.PipValue);
            return volume;
        }
    }
}
