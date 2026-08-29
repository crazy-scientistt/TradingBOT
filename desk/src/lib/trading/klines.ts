import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import type { Candle, Interval } from "./types";

const Input = z.object({
  symbol: z.string().min(3).max(20),
  interval: z.enum(["1m", "5m", "15m", "1h", "4h"]),
  limit: z.number().int().min(50).max(500),
});

const MIRRORS = [
  "https://data-api.binance.vision",
  "https://api.binance.com",
];

export const fetchPublicKlines = createServerFn({ method: "GET" })
  .validator(Input)
  .handler(async ({ data }): Promise<{ candles: Candle[]; source: "binance-public" | "synthetic" }> => {
    for (const origin of MIRRORS) {
      try {
        const url = `${origin}/api/v3/klines?symbol=${encodeURIComponent(data.symbol)}&interval=${data.interval}&limit=${data.limit}`;
        const res = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(6000) });
        if (!res.ok) continue;
        const raw = (await res.json()) as unknown;
        if (!Array.isArray(raw)) continue;
        const candles: Candle[] = raw.map((row) => {
          const r = row as Array<number | string>;
          return {
            t: Number(r[0]),
            o: Number(r[1]),
            h: Number(r[2]),
            l: Number(r[3]),
            c: Number(r[4]),
            v: Number(r[5]),
          };
        });
        if (candles.length < 30) continue;
        return { candles, source: "binance-public" };
      } catch {
        /* next mirror */
      }
    }
    return { candles: syntheticGold(data.limit, data.interval), source: "synthetic" };
  });

export const fetchPublicTicker = createServerFn({ method: "GET" })
  .validator(z.object({ symbol: z.string().min(3).max(20) }))
  .handler(async ({ data }): Promise<{ last: number | null; source: "binance-public" | "synthetic" }> => {
    for (const origin of MIRRORS) {
      try {
        const res = await fetch(
          `${origin}/api/v3/ticker/price?symbol=${encodeURIComponent(data.symbol)}`,
          { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(4000) },
        );
        if (!res.ok) continue;
        const json = (await res.json()) as { price?: string };
        const last = Number(json.price);
        if (Number.isFinite(last) && last > 0) return { last, source: "binance-public" };
      } catch {
        /* next */
      }
    }
    return { last: null, source: "synthetic" };
  });

const STEP: Record<Interval, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
};

function syntheticGold(limit: number, interval: Interval): Candle[] {
  const now = Date.now();
  const step = STEP[interval];
  let price = 4458;
  const candles: Candle[] = [];
  for (let i = limit; i >= 0; i--) {
    const drift = Math.sin(i / 18) * 1.6 + Math.sin(i / 47) * 3.4;
    const shock = ((i * 17) % 11) - 5;
    const change = drift * 0.08 + shock * 0.12;
    const o = price;
    const c = Math.max(3200, o + change);
    const h = Math.max(o, c) + Math.abs(shock) * 0.18;
    const l = Math.min(o, c) - Math.abs(drift) * 0.12;
    candles.push({
      t: now - i * step,
      o: round(o),
      h: round(h),
      l: round(l),
      c: round(c),
      v: 12 + (i % 9),
    });
    price = c;
  }
  return candles;
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
