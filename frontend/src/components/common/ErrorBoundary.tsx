import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Keeps a malformed live section from taking down the whole cockpit silently. */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep the detail in the console for operators while the UI remains useful.
    console.error('GoldGuard UI disconnected from live data', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          style={{
            margin: '24px',
            padding: '18px',
            border: '1px solid rgba(239, 68, 68, 0.45)',
            borderRadius: '8px',
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            color: '#fecaca',
          }}
        >
          <strong style={{ display: 'block', marginBottom: '6px' }}>Live dashboard disconnected</strong>
          <span style={{ color: '#fca5a5', fontSize: '13px' }}>
            A dashboard section failed to render. Refresh the page after the service is healthy.
          </span>
        </div>
      );
    }
    return this.props.children;
  }
}

