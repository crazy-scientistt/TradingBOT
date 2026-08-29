import assert from "node:assert/strict";
import test from "node:test";
import type { Candle } from "./types.ts";
import { patternAllows, scanPatterns } from "./patterns.ts";

function series(values: number[]): Candle[] {
  return values.map((c, i) => ({
    t: 1_000_000 + i * 900_000,
    o: c,
    h: c + 0.4,
    l: c - 0.4,
    c,
    v: 10,
  }));
}

function ramp(n: number, start: number, step: number): number[] {
  return Array.from({ length: n }, (_, i) => start + i * step);
}

test("uptrend 15m does not allow a 15m short fade against 1h", () => {
  const cs = series(ramp(80, 100, 0.4));
  const hits = scanPatterns(cs);
  const htf = hits.find((h) => h.id === "htf");
  assert.ok(htf);
  const gate = patternAllows(hits, "SHORT");
  assert.equal(gate.ok, false);
  assert.match(gate.reason, /HOLD|fade|1h/i);
});

test("higher-high / higher-low uptrend allows a long, not a short", () => {
  const values: number[] = [];
  let px = 100;
  for (let cycle = 0; cycle < 8; cycle++) {
    for (let i = 0; i < 7; i++) {
      px += 0.55;
      values.push(px);
    }
    for (let i = 0; i < 3; i++) {
      px -= 0.18;
      values.push(px);
    }
  }
  const hits = scanPatterns(series(values));
  assert.equal(patternAllows(hits, "LONG").ok, true);
  assert.equal(patternAllows(hits, "SHORT").ok, false);
});

test("chop without a confirmed pattern stays HOLD", () => {
  const base = 100;
  const values = Array.from({ length: 80 }, (_, i) => base + Math.sin(i / 2) * 0.15);
  const hits = scanPatterns(series(values));
  const st = hits.find((h) => h.id === "structure");
  assert.ok(st);
  const long = patternAllows(hits, "LONG");
  const short = patternAllows(hits, "SHORT");
  assert.equal(long.ok || short.ok, false);
});
