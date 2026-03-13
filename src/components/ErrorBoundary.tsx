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
            <p className="text-accent-red font-bold text-sm mb-2">[ERR] DASHBOARD CRASH</p>
            <p className="text-xs text-text-secondary mb-3">
              the UI encountered an unexpected error
            </p>
            <p className="text-[10px] text-text-tertiary mb-3 break-words bg-bg-elevated border border-border-subtle p-2">
              {this.state.message}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="h-7 px-3 border border-accent-green text-accent-green text-[10px] font-bold hover:bg-accent-green hover:text-bg-base transition-colors uppercase"
            >
              [ RELOAD ]
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
