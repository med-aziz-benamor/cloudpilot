import { AlertTriangle } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// React error boundaries must be class components — there is no hook
// equivalent for getDerivedStateFromError/componentDidCatch.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error in the app tree:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-3 bg-neutral-50 p-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-status-danger/10 text-status-danger">
            <AlertTriangle size={22} />
          </div>
          <h1 className="text-h3 font-semibold text-neutral-900">Something went wrong</h1>
          <p className="max-w-sm text-body-sm text-neutral-500">
            This part of CloudPilot hit an unexpected error. Reloading usually fixes it.
          </p>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
