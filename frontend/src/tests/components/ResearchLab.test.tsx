import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ResearchLab } from '../../components/research/ResearchLab';
import { ResearchQuota, TradeReflection } from '../../types';

const mockQuota: ResearchQuota = {
  date: '2026-08-26',
  backtests_used: 12,
  backtests_limit: 50,
  web_calls_used: 6,
  web_calls_limit: 20,
};

const mockReflections: TradeReflection[] = [
  {
    id: 'ref-1',
    trade_id: 't-101',
    namespace: 'forward',
    lesson_code: 'CHOP_WHIPSAW',
    lesson: 'Achieved positive excursion then reversed into stop; volume requirement adjusted.',
    regime_tags: ['trend', 'low-volatility'],
    net_pnl: '-1.45',
    fee_drag: '0.25',
    exit_reason: 'STOP_LOSS',
    created_at: '2026-08-26T14:30:00Z',
  },
  {
    id: 'ref-2',
    trade_id: 't-102',
    namespace: 'forward',
    lesson_code: 'TP_CLEAN',
    lesson: 'Target reached cleanly with hourly trend momentum.',
    regime_tags: ['trend', 'normal-volatility'],
    net_pnl: '+2.80',
    fee_drag: '0.22',
    exit_reason: 'TAKE_PROFIT',
    created_at: '2026-08-26T16:00:00Z',
  },
];

describe('ResearchLab', () => {
  it('renders research quota meters and daily limits', () => {
    render(<ResearchLab quota={mockQuota} reflections={mockReflections} isRunning={false} />);
    expect(screen.getByText('12 / 50')).toBeInTheDocument();
    expect(screen.getByText('6 / 20')).toBeInTheDocument();
  });

  it('renders trade post-mortems and lesson tags', () => {
    render(<ResearchLab quota={mockQuota} reflections={mockReflections} isRunning={false} />);
    expect(screen.getByText('CHOP_WHIPSAW')).toBeInTheDocument();
    expect(screen.getByText('TP_CLEAN')).toBeInTheDocument();
  });

  it('triggers manual research step when button is clicked', () => {
    const handleStep = vi.fn();
    render(
      <ResearchLab
        quota={mockQuota}
        reflections={mockReflections}
        isRunning={false}
        onRunStep={handleStep}
      />
    );
    const stepBtn = screen.getByRole('button', { name: /Run research now/i });
    fireEvent.click(stepBtn);
    expect(handleStep).toHaveBeenCalled();
  });
});
