import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LoginPanel } from '../../components/auth/LoginPanel';

describe('LoginPanel', () => {
  it('collects password and TOTP without storing a session secret', async () => {
    const onSubmit = vi.fn();
    render(<LoginPanel onSubmit={onSubmit} />);

    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByLabelText('TOTP')).toBeInTheDocument();
    expect(
      screen.getByText(/session secret is never stored/i),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'hunter2' } });
    fireEvent.change(screen.getByLabelText('TOTP'), { target: { value: '123456' } });
    fireEvent.submit(screen.getByRole('button', { name: /sign in/i }).closest('form')!);

    expect(onSubmit).toHaveBeenCalledWith('hunter2', '123456');
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
