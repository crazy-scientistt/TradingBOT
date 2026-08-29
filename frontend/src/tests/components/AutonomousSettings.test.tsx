import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  AutonomousProfileView,
  AutonomousSettings,
} from '../../components/settings/AutonomousSettings';

const spotOnlyProfile: AutonomousProfileView = {
  execution_mode: 'paper',
  spot_enabled: true,
  futures_enabled: false,
  risk: {
    max_capital_per_trade_rate: '0.005',
    max_futures_leverage: 5,
    max_total_exposure_rate: '0.20',
    rolling_24h_loss_limit_rate: '0.03',
  },
};

describe('AutonomousSettings', () => {
  it('shows USDT equivalents beneath percentage ceilings', async () => {
    render(<AutonomousSettings equityUsdt="10000" />);
    expect(await screen.findByText('50.00 USDT maximum for one trade')).toBeInTheDocument();
    expect(screen.getByText('2,000.00 USDT maximum total exposure')).toBeInTheDocument();
  });

  it('does not invent equity when none is observed', async () => {
    render(<AutonomousSettings />);
    expect(
      await screen.findAllByText('USDT equivalent unavailable until equity is observed'),
    ).not.toHaveLength(0);
  });

  it('hides leverage when futures is disabled', async () => {
    render(<AutonomousSettings initialProfile={spotOnlyProfile} />);
    expect(screen.queryByLabelText('Max Futures Leverage')).not.toBeInTheDocument();
  });
});
