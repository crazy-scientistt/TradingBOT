import { atr, ema, last } from "./indicators";
import type { Candle, PatternHit, Side } from "./types";

type Swing = { i: number; px: number; kind: "H" | "L" };

function swings(cs: Candle[], left = 3): Swing[] {
  const out: Swing[] = [];
  for (let i = left; i < cs.length - left; i++) {
    const w = cs.slice(i - left, i + left + 1);
    const hi = Math.max(...w.map((c) => c.h));
    const lo = Math.min(...w.map((c) => c.l));
    if (cs[i].h === hi && cs[i].h > cs[i - 1].h && cs[i].h >= cs[i + 1].h) out.push({ i, px: cs[i].h, kind: "H" });
    if (cs[i].l === lo && cs[i].l < cs[i - 1].l && cs[i].l <= cs[i + 1].l) out.push({ i, px: cs[i].l, kind: "L" });
  }
  return out;
}

function structure(sw: Swing[]): { bias: "UP" | "DOWN" | "RANGE"; detail: string } {
  const hs = sw.filter((s) => s.kind === "H").slice(-3);
  const ls = sw.filter((s) => s.kind === "L").slice(-3);
  if (hs.length >= 2 && ls.length >= 2) {
    const hh = hs.at(-1)!.px > hs.at(-2)!.px;
    const hl = ls.at(-1)!.px > ls.at(-2)!.px;
    const lh = hs.at(-1)!.px < hs.at(-2)!.px;
    const ll = ls.at(-1)!.px < ls.at(-2)!.px;
    if (hh && hl) return { bias: "UP", detail: "Higher highs and higher lows (uptrend structure)" };
    if (lh && ll) return { bias: "DOWN", detail: "Lower highs and lower lows (downtrend structure)" };
  }
  return { bias: "RANGE", detail: "No clear HH/HL or LH/LL — chop. HOLD is the default." };
}

function hourBias(cs: Candle[]): "UP" | "DOWN" | "RANGE" {
  const sampled = cs.filter((_, i) => i % 4 === 0).map((c) => c.c);
  if (sampled.length < 30) return "RANGE";
  const f = last(ema(sampled, 12));
  const s = last(ema(sampled, 26));
  if (!f || !s) return "RANGE";
  if (f > s * 1.0004) return "UP";
  if (f < s * 0.9996) return "DOWN";
  return "RANGE";
}

function doubleTopBottom(cs: Candle[], sw: Swing[], a: number): PatternHit | null {
  const hs = sw.filter((s) => s.kind === "H");
  const ls = sw.filter((s) => s.kind === "L");
  const lastC = cs[cs.length - 1];
  const tol = Math.max(a * 0.35, lastC.c * 0.002);
  if (hs.length >= 2) {
    const aH = hs.at(-1)!;
    const bH = hs.at(-2)!;
    if (Math.abs(aH.px - bH.px) <= tol && aH.i - bH.i >= 6) {
      const valley = ls.filter((s) => s.i > bH.i && s.i < aH.i).sort((x, y) => x.px - y.px)[0];
      if (valley && lastC.c < valley.px && (bH.px - valley.px) > a * 0.8) {
        return {
          id: "double-top",
          name: "Double top",
          kind: "reversal",
          side: "SHORT",
          score: 0.72,
          detail: "Two peaks within tolerance; close below the trough/neckline (ChartSchool confirmation).",
        };
      }
    }
  }
  if (ls.length >= 2) {
    const aL = ls.at(-1)!;
    const bL = ls.at(-2)!;
    if (Math.abs(aL.px - bL.px) <= tol && aL.i - bL.i >= 6) {
      const peak = hs.filter((s) => s.i > bL.i && s.i < aL.i).sort((x, y) => y.px - x.px)[0];
      if (peak && lastC.c > peak.px && (peak.px - bL.px) > a * 0.8) {
        return {
          id: "double-bottom",
          name: "Double bottom",
          kind: "reversal",
          side: "LONG",
          score: 0.72,
          detail: "Two troughs within tolerance; close above the peak/neckline.",
        };
      }
    }
  }
  return null;
}

function flag(cs: Candle[], a: number): PatternHit | null {
  if (cs.length < 24) return null;
  const impulse = cs.slice(-22, -8);
  const flagBars = cs.slice(-8);
  const impRange = Math.max(...impulse.map((c) => c.h)) - Math.min(...impulse.map((c) => c.l));
  const flagRange = Math.max(...flagBars.map((c) => c.h)) - Math.min(...flagBars.map((c) => c.l));
  if (impRange < a * 2.2 || flagRange <= 0 || flagRange > impRange * 0.45) return null;
  const impDir = impulse[impulse.length - 1].c >= impulse[0].c ? "UP" : "DOWN";
  const lastC = cs[cs.length - 1];
  const flagHigh = Math.max(...flagBars.map((c) => c.h));
  const flagLow = Math.min(...flagBars.map((c) => c.l));
  if (impDir === "UP" && lastC.c > flagHigh) {
    return {
      id: "bull-flag",
      name: "Bull flag",
      kind: "continuation",
      side: "LONG",
      score: 0.78,
      detail: "Impulse up, tight pause, close above the flag high (continuation, not a new trend guess).",
    };
  }
  if (impDir === "DOWN" && lastC.c < flagLow) {
    return {
      id: "bear-flag",
      name: "Bear flag",
      kind: "continuation",
      side: "SHORT",
      score: 0.78,
      detail: "Impulse down, tight pause, close below the flag low.",
    };
  }
  return null;
}

export function scanPatterns(cs: Candle[]): PatternHit[] {
  if (cs.length < 40) return [];
  const a = last(atr(cs, 14)) ?? 0;
  const sw = swings(cs);
  const st = structure(sw);
  const h1 = hourBias(cs);
  const hits: PatternHit[] = [
    {
      id: "structure",
      name: `15m structure ${st.bias}`,
      kind: "structure",
      side: st.bias === "UP" ? "LONG" : st.bias === "DOWN" ? "SHORT" : "FLAT",
      score: st.bias === "RANGE" ? 0.4 : 0.7,
      detail: st.detail,
    },
    {
      id: "htf",
      name: `1h EMA bias ${h1}`,
      kind: "structure",
      side: h1 === "UP" ? "LONG" : h1 === "DOWN" ? "SHORT" : "FLAT",
      score: h1 === "RANGE" ? 0.35 : 0.74,
      detail: "BabyPips multiple-timeframe: do not fade a clear 1h slope on 15m noise.",
    },
  ];
  const dt = doubleTopBottom(cs, sw, a);
  if (dt) hits.push(dt);
  const fl = flag(cs, a);
  if (fl) hits.push(fl);
  return hits;
}

export function patternAllows(hits: PatternHit[], side: Side): { ok: boolean; reason: string } {
  const htf = hits.find((h) => h.id === "htf");
  const st = hits.find((h) => h.id === "structure");
  if (htf && htf.side !== "FLAT" && htf.side !== side) {
    return { ok: false, reason: `1h bias is ${htf.side} — 15m ${side} is a fade. HOLD.` };
  }
  if (st && st.side === "FLAT" && !hits.some((h) => h.kind !== "structure")) {
    return { ok: false, reason: "Range / no confirmed pattern. HOLD." };
  }
  if (st && st.side !== "FLAT" && st.side !== side && !hits.some((h) => h.kind === "reversal" && h.side === side && h.score >= 0.7)) {
    return { ok: false, reason: `15m structure is ${st.side}; ${side} needs a confirmed reversal close.` };
  }
  const confirmed = hits.filter((h) => h.side === side && (h.kind === "continuation" || h.kind === "reversal") && h.score >= 0.7);
  const trendPullback = st?.side === side && htf?.side === side;
  if (!trendPullback && confirmed.length === 0) {
    return { ok: false, reason: "EMA pullback without structure or a confirmed flag/neckline. HOLD." };
  }
  return { ok: true, reason: confirmed[0]?.name ?? "Trend-aligned pullback" };
}
