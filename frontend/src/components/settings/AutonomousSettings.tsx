import React from 'react';

export interface RiskCeilingsView {
  max_capital_per_trade_rate: string;
  max_futures_leverage: number;
  max_total_exposure_rate: string;
  rolling_24h_loss_limit_rate: string;
}

export interface AutonomousProfileView {
  execution_mode?: string;
  spot_enabled: boolean;
  futures_enabled: boolean;
  risk: RiskCeilingsView;
}

const DEFAULT_PROFILE: AutonomousProfileView = {
  execution_mode: 'paper',
  spot_enabled: true,
  futures_enabled: true,
  risk: {
    max_capital_per_trade_rate: '0.005',
    max_futures_leverage: 5,
    max_total_exposure_rate: '0.20',
    rolling_24h_loss_limit_rate: '0.03',
  },
};

export interface AutonomousSettingsProps {
  initialProfile?: AutonomousProfileView;
  equityUsdt?: string | null;
}

function formatUsdt(value: number): string {
  const fixed = value.toFixed(2);
  const [whole, fraction] = fixed.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${grouped}.${fraction}`;
}

function usdtEquivalent(rateText: string, equity: number): number {
  const rate = Number(rateText);
  if (!Number.isFinite(rate) || !Number.isFinite(equity)) {
    return 0;
  }
  return equity * rate;
}

export const AutonomousSettings: React.FC<AutonomousSettingsProps> = ({
  initialProfile,
  equityUsdt = null,
}) => {
  const profile = initialProfile ?? DEFAULT_PROFILE;
  const equity = equityUsdt == null || equityUsdt === '' ? Number.NaN : Number(equityUsdt);
  const equityKnown = Number.isFinite(equity);
  const capitalUsdt = equityKnown ? usdtEquivalent(profile.risk.max_capital_per_trade_rate, equity) : 0;
  const exposureUsdt = equityKnown ? usdtEquivalent(profile.risk.max_total_exposure_rate, equity) : 0;
  const lossUsdt = equityKnown ? usdtEquivalent(profile.risk.rolling_24h_loss_limit_rate, equity) : 0;
  const capitalPercent = (Number(profile.risk.max_capital_per_trade_rate) * 100).toFixed(2);
  const exposurePercent = (Number(profile.risk.max_total_exposure_rate) * 100).toFixed(2);
  const lossPercent = (Number(profile.risk.rolling_24h_loss_limit_rate) * 100).toFixed(2);

  const fieldStyle: React.CSSProperties = {
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--radius-sm)',
    padding: '8px 10px',
    color: 'var(--text-main)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    width: '100%',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  };

  const hintStyle: React.CSSProperties = {
    fontSize: '11px',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
  };

  return (
    <section
      style={{
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <header>
        <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '15px' }}>
          Autonomous risk ceilings
        </h3>
        <p style={{ margin: '6px 0 0', color: 'var(--text-muted)', fontSize: '12px' }}>
          Percentages are hard ceilings. AI may only select values below them. Shown USDT
          equivalents use current paper equity
          {equityKnown ? ` (${formatUsdt(equity)} USDT)` : ' (equity unavailable)'}.
        </p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label htmlFor="max-capital-per-trade" style={labelStyle}>
            Max Capital per Trade
          </label>
          <input
            id="max-capital-per-trade"
            readOnly
            value={`${capitalPercent}%`}
            style={fieldStyle}
          />
          <span style={hintStyle}>
            {equityKnown
              ? `${formatUsdt(capitalUsdt)} USDT maximum for one trade`
              : 'USDT equivalent unavailable until equity is observed'}
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label htmlFor="max-total-exposure" style={labelStyle}>
            Max Total Exposure
          </label>
          <input
            id="max-total-exposure"
            readOnly
            value={`${exposurePercent}%`}
            style={fieldStyle}
          />
          <span style={hintStyle}>
            {equityKnown
              ? `${formatUsdt(exposureUsdt)} USDT maximum total exposure`
              : 'USDT equivalent unavailable until equity is observed'}
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label htmlFor="rolling-24h-loss" style={labelStyle}>
            Rolling 24-Hour Loss Limit
          </label>
          <input
            id="rolling-24h-loss"
            readOnly
            value={`${lossPercent}%`}
            style={fieldStyle}
          />
          <span style={hintStyle}>
            {equityKnown
              ? `${formatUsdt(lossUsdt)} USDT rolling 24-hour loss limit`
              : 'USDT equivalent unavailable until equity is observed'}
          </span>
        </div>

        {profile.futures_enabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label htmlFor="max-futures-leverage" style={labelStyle}>
              Max Futures Leverage
            </label>
            <input
              id="max-futures-leverage"
              readOnly
              value={`${profile.risk.max_futures_leverage}x`}
              style={fieldStyle}
            />
            <span style={hintStyle}>Shown only while USD-M Futures is enabled.</span>
          </div>
        )}
      </div>
    </section>
  );
};
