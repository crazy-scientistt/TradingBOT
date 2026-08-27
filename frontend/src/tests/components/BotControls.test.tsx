import React from 'react';
import '../../test/setup';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BotProvider, useBot } from '../../context/BotContext';
import { TopHeader } from '../../components/layout/TopHeader';
import { App } from '../../App';

const envelope = <T,>(data: T, availability = 'available') => ({
  availability,
  source: 'test',
  observed_at: '2026-08-27T00:00:00Z',
  stale: availability !== 'available',
  detail: availability === 'available' ? null : 'test data is unavailable',
  data,
});

const dashboard = (ready: boolean, running = false) => ({
  generated_at: '2026-08-27T00:00:00Z',
  health: { status: 'ok', database: 'ok', bot_running: running },
  status: envelope({
    environment: 'test',
    mode: 'paper',
    symbol: 'PAXGUSDT',
    bot_running: running,
    full_autonomy: true,
    active_genome_id: 'trend-pullback-v1',
    paper_balance: '100',
    live_enabled: false,
  }),
  kpi: envelope(null, 'unavailable'),
  quote: envelope(null, 'unavailable'),
  candles: envelope([], 'unavailable'),
  position: envelope({ hasPosition: false, position: null, pipelineSteps: [] }),
  equity: envelope([], 'unavailable'),
  context: envelope([], 'unavailable'),
  genomes: envelope([]),
  providers: envelope([]),
  catalog: envelope([]),
  routes: envelope([]),
  quota: envelope(null, 'unavailable'),
  reflections: envelope([], 'unavailable'),
  botState: envelope({
    state: running ? 'RUNNING_FLAT' : 'PAPER_READY',
    full_autonomy: true,
    daily_loss_percent: 0,
    daily_loss_limit: 3,
    circuit_breaker_tripped: false,
    active_genome_id: 'trend-pullback-v1',
  }),
  agentEvents: envelope([], 'unavailable'),
  preflight: {
    ready,
    checks: ready ? [{ id: 'runtime', label: 'Runtime', status: 'pass', detail: 'Ready.' }] : [
      { id: 'market_data', label: 'Market data', status: 'fail', detail: 'Waiting for verified data.' },
    ],
    blocking: ready ? [] : ['market_data'],
    observed_at: '2026-08-27T00:00:00Z',
  },
  promotionCanary: envelope(null, 'unavailable'),
});

function ControlsHarness() {
  const {
    runtimeStatus,
    preflight,
    startPaperTrading,
    pauseTrading,
    emergencyStop,
  } = useBot();
  return (
    <>
      <div data-testid="runtime-state">{runtimeStatus?.state ?? 'loading'}</div>
      <div data-testid="preflight">{preflight?.ready ? 'ready' : 'blocked'}</div>
      <button onClick={startPaperTrading}>Start paper trading</button>
      <button onClick={pauseTrading}>Pause new entries</button>
      <button onClick={emergencyStop}>Emergency stop</button>
    </>
  );
}

function stubApi(snapshot: ReturnType<typeof dashboard>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/api/dashboard')) {
      return new Response(JSON.stringify(snapshot), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.endsWith('/api/bot/start') || url.endsWith('/api/bot/pause') || url.endsWith('/api/bot/stop')) {
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.endsWith('/api/agent/events/stream')) {
      return new Response('', { status: 200 });
    }
    return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('paper trading controls', () => {
  it('shows a truthful flat state without fabricated market values', async () => {
    stubApi(dashboard(false));
    render(
      <BotProvider>
        <ControlsHarness />
      </BotProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('runtime-state')).toHaveTextContent('PAPER_READY'));
    expect(screen.getByTestId('preflight')).toHaveTextContent('blocked');
  });

  it('keeps the header paper-first and does not offer a live-mode toggle', async () => {
    stubApi(dashboard(false));
    render(
      <BotProvider>
        <TopHeader />
      </BotProvider>,
    );

    await waitFor(() => expect(screen.getByText(/PAPER MODE/i)).toBeInTheDocument());
    expect(screen.queryByText(/LIVE CAPABILITY/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /START PAPER TRADING/i })).toBeInTheDocument();
  });

  it('does not start when preflight reports a blocking check', async () => {
    const fetchMock = stubApi(dashboard(false));
    render(
      <BotProvider>
        <ControlsHarness />
      </BotProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('preflight')).toHaveTextContent('blocked'));

    fireEvent.click(screen.getByRole('button', { name: 'Start paper trading' }));
    expect(fetchMock).not.toHaveBeenCalledWith('/api/bot/start', expect.anything());
  });

  it('renders the flat overview without dereferencing unavailable numbers', async () => {
    stubApi(dashboard(false));
    render(<App />);
    await waitFor(() => expect(screen.getByText('No open paper position')).toBeInTheDocument());
    expect(screen.getByText(/Waiting for a real paper-account snapshot/i)).toBeInTheDocument();
  });
});
