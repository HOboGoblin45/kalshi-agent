import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    message: "",
  };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error.message || "Unknown error",
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Unhandled UI error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen w-full flex items-center justify-center bg-bg-base text-text-primary p-4">
          <div className="card max-w-md w-full text-center">
            <h1 className="text-lg font-bold mb-2">Dashboard Error</h1>
            <p className="text-xs text-text-secondary mb-3">
              The UI encountered an unexpected issue and could not continue.
            </p>
            <p className="text-[11px] font-mono text-text-tertiary mb-3 break-words">
              {this.state.message}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="h-8 px-3 rounded-md text-xs font-semibold text-white"
              style={{ background: "var(--accent-color)" }}
            >
              Reload App
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
