import React, { useEffect, useState } from "react";
import axios from "axios";

interface Trade {
  id: number;
  symbol: string;
  entry_date: string;
  entry_price: string;
  quantity: string;
  direction: string;
  strategy: string;
  reason_entry?: string;
  estimates?: string;
  stop_loss?: string;
  exit_date?: string;
  exit_price?: string;
  reason_exit?: string;
  pnl_usd?: string;
  pnl_pct?: string;
  is_intraday?: boolean;
  portfolio_pct?: string; // % from portfolio
}

const TradeList: React.FC = () => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [darkMode, setDarkMode] = useState(true);

  useEffect(() => {
    axios
      .get("http://localhost:8000/trades/")
      .then((res) => setTrades(res.data))
      .catch((err) => console.error("Error fetching trades:", err));
  }, []);

  const formatDate = (dateStr: string | undefined) =>
    dateStr ? new Date(dateStr).toLocaleString() : "";

  const toggleMode = () => setDarkMode(!darkMode);

  return (
    <div className={darkMode ? "dark" : ""}>
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-white p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-4xl font-bold">📊 Trading Journal</h1>
          <button
            onClick={toggleMode}
            className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
          >
            Toggle {darkMode ? "Light" : "Dark"} Mode
          </button>
        </div>

        <h2 className="text-2xl font-semibold mb-4">Trade List</h2>

        <div className="overflow-x-auto">
          <table className="min-w-full border border-gray-600">
            <thead>
              <tr className="bg-gray-200 dark:bg-gray-800">
                {[
                  "Symbol",
                  "Entry Date",
                  "Entry Price",
                  "Quantity",
                  "Long/Short",
                  "% Portfolio",
                  "Strategy",
                  "Reason (Entry)",
                  "Estimates",
                  "Stop Loss",
                  "Exit Date",
                  "Exit Price",
                  "Reason (Exit)",
                  "PnL ($)",
                  "PnL (%)",
                  "Intraday",
                ].map((col) => (
                  <th key={col} className="border px-3 py-2">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id} className="border-t">
                  <td className="border px-3 py-2">{trade.symbol}</td>
                  <td className="border px-3 py-2">
                    {formatDate(trade.entry_date)}
                  </td>
                  <td className="border px-3 py-2">{trade.entry_price}</td>
                  <td className="border px-3 py-2">{trade.quantity}</td>
                  <td className="border px-3 py-2">{trade.direction}</td>
                  <td className="border px-3 py-2">
                    {trade.portfolio_pct || "-"}
                  </td>
                  <td className="border px-3 py-2">{trade.strategy}</td>
                  <td className="border px-3 py-2">
                    {trade.reason_entry || "-"}
                  </td>
                  <td className="border px-3 py-2">{trade.estimates || "-"}</td>
                  <td className="border px-3 py-2">{trade.stop_loss || "-"}</td>
                  <td className="border px-3 py-2">
                    {formatDate(trade.exit_date)}
                  </td>
                  <td className="border px-3 py-2">
                    {trade.exit_price || "-"}
                  </td>
                  <td className="border px-3 py-2">
                    {trade.reason_exit || "-"}
                  </td>
                  <td className="border px-3 py-2">{trade.pnl_usd || "-"}</td>
                  <td className="border px-3 py-2">{trade.pnl_pct || "-"}</td>
                  <td className="border px-3 py-2">
                    {trade.is_intraday ? "Yes" : "No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default TradeList;
