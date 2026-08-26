import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StrategyStudio } from '../../components/strategy/StrategyStudio';
import { StrategyGenome } from '../../types';

const baselineGenome: StrategyGenome = {
  genome_id: 'trend-pullback-v1',
  title: 'Hourly Trend 15m Pullback Recovery',
  hypothesis: 'Trading in the direction of the 1h EMA50 slope during pullbacks produces positive expectancy.',
  evidence_refs: ['doc-trend-pullback-v1', 'report-dev-baseline'],
  regime: ['trend', 'normal-volatility'],
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
    take_profit_r_multiple: '2.0',
    stop_loss_atr_multiple: '1.5',
    invalidation: [
      {
        left: 'consecutive_closes_below_ema50',
        op: '>=',
        right: 2,
      },
    ],
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
  it('renders active baseline genome title and status badge', () => {
    render(<StrategyStudio initialGenomes={[baselineGenome]} activeGenomeId="trend-pullback-v1" />);
    const titles = screen.getAllByText(/Hourly Trend 15m Pullback Recovery/i);
    expect(titles.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('active')).toBeInTheDocument();
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
  });

  it('triggers inline backtest and displays performance metrics', async () => {
    render(
      <StrategyStudio
        initialGenomes={[baselineGenome]}
        activeGenomeId="trend-pullback-v1"
      />
    );
    const runBtn = screen.getByRole('button', { name: /Run Backtest/i });
    fireEvent.click(runBtn);

    expect(await screen.findByText(/Win Rate/i)).toBeInTheDocument();
    expect(screen.getByText(/Profit Factor/i)).toBeInTheDocument();
  });
});
