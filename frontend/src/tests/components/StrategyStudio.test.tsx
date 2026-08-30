import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { api } from '../../api/client';
import { StrategyStudio } from '../../components/strategy/StrategyStudio';
import { StrategyGenome } from '../../types';

const baselineGenome: StrategyGenome = {
  genome_id: 'trend-pullback-v1',
  title: 'Hourly Trend 15m Pullback Recovery',
  hypothesis: 'Trading in the direction of the 1h EMA50 slope during pullbacks produces positive expectancy.',
  evidence_refs: ['doc-trend-pullback-v1', 'report-dev-baseline'],
  regime: [],
  guard: {
    min_atr_rate: '0.0005',
    max_atr_rate: '0.0150',
    max_spread_rate: '0.0015',
  },
  entry: [
    {
      left: { indicator: 'rsi', timeframe: '15m', period: 14 },
      op: '>',
      right: '45',
    },
    {
      left: { indicator: 'volume_ratio', timeframe: '15m', period: 20 },
      op: '>=',
      right: '0.80',
    },
  ],
  exit: {
    regime_invalidation: true,
    r_multiple_min: '2.0',
    stop_atr_multiple: '1.5',
    max_hold_bars: null,
  },
  status: 'active',
};

const candidateGenome: StrategyGenome = {
  ...baselineGenome,
  genome_id: 'hermes-candidate-01',
  title: 'Hermes Volume Filter Refinement',
  status: 'candidate',
  entry: [
    {
      left: { indicator: 'rsi', timeframe: '15m', period: 14 },
      op: '>',
      right: '45',
    },
    {
      left: { indicator: 'volume_ratio', timeframe: '15m', period: 20 },
      op: '>=',
      right: '1.10',
    },
  ],
};

describe('StrategyStudio', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders active baseline genome title and status badge', () => {
    render(<StrategyStudio initialGenomes={[baselineGenome]} activeGenomeId="trend-pullback-v1" />);
    const titles = screen.getAllByText(/Hourly Trend 15m Pullback Recovery/i);
    expect(titles.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText(/Auto-promote waits on Start/i)).toBeInTheDocument();
  });

  it('allows switching between genomes and displays candidate diff against active', () => {
    render(
      <StrategyStudio
        initialGenomes={[baselineGenome, candidateGenome]}
        activeGenomeId="trend-pullback-v1"
      />
    );
    const candidateBtn = screen.getByText(/Hermes Volume Filter Refinement/i);
    fireEvent.click(candidateBtn);

    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText(/Diff vs Active/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Promote candidate/i })).not.toBeInTheDocument();
  });

  it('triggers inline backtest and displays performance metrics', async () => {
    const runBacktest = vi.spyOn(api, 'runBacktest').mockResolvedValue({
      net_pnl: '10.00',
      gross_pnl: '12.00',
      fee_drag: '2.00',
      net_return: '1.00%',
      trade_count: 10,
      win_rate: '60.0%',
      profit_factor: '1.50',
      maximum_drawdown: '2.00%',
      sharpe_ratio: '1.20',
    });
    render(
      <StrategyStudio
        initialGenomes={[baselineGenome]}
        activeGenomeId="trend-pullback-v1"
      />
    );
    const runBtn = screen.getByRole('button', { name: /Inspect backtest/i });
    fireEvent.click(runBtn);

    expect(await screen.findByText(/Win Rate/i)).toBeInTheDocument();
    expect(screen.getByText(/Profit Factor/i)).toBeInTheDocument();
    expect(runBacktest).toHaveBeenCalledWith(baselineGenome);
  });
});
