'use client';

import React, { Component, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary] Uncaught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] px-6 text-center" role="alert">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" className="mb-4" aria-hidden="true">
            <circle cx="32" cy="32" r="28" stroke="var(--accent, #0078D4)" strokeWidth="2.5" fill="none" />
            <path d="M32 20v16" stroke="var(--accent, #0078D4)" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="32" cy="44" r="2" fill="var(--accent, #0078D4)" />
          </svg>
          <h2 className="text-lg font-semibold text-[var(--text-primary,#323130)] mb-2">
            Something went wrong
          </h2>
          <p className="text-sm text-[var(--text-secondary,#605E5C)] mb-6 max-w-md">
            An unexpected error occurred. Please try again, or refresh the page if the problem persists.
          </p>
          <button
            onClick={this.handleRetry}
            className="px-5 py-2.5 bg-[var(--accent,#0078D4)] text-white rounded-lg text-sm font-semibold hover:bg-[var(--accent-hover,#106EBE)] transition-colors focus-visible:outline-2 focus-visible:outline-[var(--accent,#0078D4)] focus-visible:outline-offset-2"
          >
            Try Again
          </button>
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <pre className="mt-6 p-4 bg-[var(--bg-secondary,#FAF9F8)] border border-[var(--border,#E1DFDD)] rounded text-left text-xs text-[var(--text-secondary,#605E5C)] max-w-lg overflow-auto max-h-48">
              {this.state.error.message}
              {'\n'}
              {this.state.error.stack}
            </pre>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
