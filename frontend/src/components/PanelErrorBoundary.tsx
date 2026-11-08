import React from 'react';

interface Props {
  /** Shown in the fallback so the user knows which panel failed. */
  label: string;
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

/** Isolates one panel: if it throws while rendering, the rest of the workspace
 *  (tab bar, other panels) stays alive instead of React unmounting the root. */
export class PanelErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[react-panel:${this.props.label}]`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="vx-empty-state" role="alert" data-testid="panel-error">
        <strong>{this.props.label}</strong> could not be displayed for this chart.{' '}
        <button type="button" className="btn-ghost" onClick={() => this.setState({ error: null })}>
          Retry
        </button>
      </div>
    );
  }
}
