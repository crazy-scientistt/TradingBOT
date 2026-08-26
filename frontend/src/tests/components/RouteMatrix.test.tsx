import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RouteMatrix } from '../../components/providers/RouteMatrix';
import { AIProvider, ProviderRoute } from '../../types';

const mockProviders: AIProvider[] = [
  {
    name: 'opencodex',
    kind: 'proxy',
    base_url: 'http://localhost:10100',
    key_fingerprint: 'sk-mock-****9999',
    status: 'active',
    latency_ms: 45,
  },
  {
    name: 'google-antigravity',
    kind: 'native',
    base_url: 'https://generativelanguage.googleapis.com',
    key_fingerprint: 'sk-mock-****8888',
    status: 'active',
    latency_ms: 120,
  },
];

const mockRoutes: ProviderRoute[] = [
  {
    id: 'r-1',
    role: 'decision',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
  {
    id: 'r-2',
    role: 'context',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
  {
    id: 'r-3',
    role: 'hermes',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
];

describe('RouteMatrix', () => {
  it('renders all AI provider cards with latency and key fingerprints', () => {
    render(
      <RouteMatrix
        providers={mockProviders}
        initialRoutes={mockRoutes}
      />
    );
    expect(screen.getByText('opencodex')).toBeInTheDocument();
    expect(screen.getByText(/45 ms/i)).toBeInTheDocument();
    expect(screen.getByText('sk-mock-****9999')).toBeInTheDocument();
  });

  it('allows switching provider model routes and invokes callback', () => {
    const handleRouteChange = vi.fn();
    render(
      <RouteMatrix
        providers={mockProviders}
        initialRoutes={mockRoutes}
        onRouteChange={handleRouteChange}
      />
    );

    // Select provider dropdown for decision role
    const decisionSelect = screen.getByTestId('route-select-decision');
    fireEvent.change(decisionSelect, { target: { value: 'google-antigravity' } });

    expect(handleRouteChange).toHaveBeenCalledWith('decision', 'google-antigravity');
  });
});
