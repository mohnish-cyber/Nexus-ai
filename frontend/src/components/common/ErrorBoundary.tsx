import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorNotice } from "./ui";

interface Props {
  children: ReactNode;
  scope?: string;
}

interface State {
  error: Error | null;
}

/** Catches rendering errors so one broken panel never takes down the whole command centre. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[NEXUS] ${this.props.scope ?? "UI"} crashed`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-4">
          <ErrorNotice
            title={`${this.props.scope ?? "This view"} failed to display.`}
            reason={this.state.error.message}
            nextStep="Try again. If it keeps happening, reload the page."
            onRetry={() => this.setState({ error: null })}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
