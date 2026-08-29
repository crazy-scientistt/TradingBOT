import { useMemo } from "react";
import type { Interval } from "@/lib/trading/types";

const TV_INTERVAL: Record<Interval, string> = {
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "4h": "240",
};

type Props = {
  interval: Interval;
};

export function TradingViewWidget({ interval }: Props) {
  const src = useMemo(() => {
    const params = new URLSearchParams({
      frameElementId: "tv-paxg",
      symbol: "BINANCE:PAXGUSDT",
      interval: TV_INTERVAL[interval],
      hidesidetoolbar: "0",
      symboledit: "0",
      saveimage: "0",
      toolbarbg: "000000",
      studies: JSON.stringify(["STD;EMA"]),
      theme: "dark",
      style: "1",
      timezone: "Etc/UTC",
      withdateranges: "1",
      hideideas: "1",
      hidevolume: "0",
      hotlist: "0",
      locale: "en",
      backgroundColor: "rgba(0,0,0,1)",
      gridColor: "rgba(28,36,54,1)",
    });
    return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
  }, [interval]);

  return (
    <iframe
      title="TradingView PAXGUSDT"
      src={src}
      className="h-full w-full border-0 bg-bg"
      referrerPolicy="no-referrer-when-downgrade"
    />
  );
}
