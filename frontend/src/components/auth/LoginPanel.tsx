import React, { FormEvent, useState } from 'react';

export interface LoginPanelProps {
  onSubmit?: (password: string, totp: string) => void | Promise<void>;
  error?: string | null;
  busy?: boolean;
}

export const LoginPanel: React.FC<LoginPanelProps> = ({
  onSubmit,
  error = null,
  busy = false,
}) => {
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    // Session secret stays server-side (HttpOnly cookie). Nothing is stored here.
    await onSubmit?.(password, totp);
  };

  const fieldStyle: React.CSSProperties = {
    width: '100%',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--radius-sm)',
    padding: '10px 12px',
    color: 'var(--text-main)',
    fontFamily: 'var(--font-sans)',
    fontSize: '13px',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        width: '100%',
        maxWidth: '360px',
        backgroundColor: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
      }}
    >
      <div>
        <h2
          style={{
            margin: 0,
            color: 'var(--gold-primary)',
            fontSize: '16px',
            fontWeight: 700,
          }}
        >
          GoldGuard
        </h2>
        <p style={{ margin: '6px 0 0', color: 'var(--text-muted)', fontSize: '12px' }}>
          Sign in with password and authenticator code. The session secret is never stored
          in the browser.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <label htmlFor="login-password" style={labelStyle}>
          Password
        </label>
        <input
          id="login-password"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          style={fieldStyle}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <label htmlFor="login-totp" style={labelStyle}>
          TOTP
        </label>
        <input
          id="login-totp"
          type="text"
          name="totp"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={totp}
          onChange={(event) => setTotp(event.target.value.replace(/\s/g, ''))}
          required
          maxLength={16}
          placeholder="6-digit code"
          style={fieldStyle}
        />
      </div>

      {error && (
        <div role="alert" style={{ color: 'var(--red-bear)', fontSize: '12px' }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        style={{
          backgroundColor: 'var(--gold-primary)',
          color: '#111111',
          border: 'none',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 14px',
          fontWeight: 700,
          fontSize: '13px',
          cursor: busy ? 'wait' : 'pointer',
        }}
      >
        Sign in
      </button>
    </form>
  );
};
