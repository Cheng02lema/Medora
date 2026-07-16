import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  onError?: (error: Error, info: string) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * 全局错误边界：捕获 React 渲染异常，显示友好错误页面而非白屏。
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
    if (this.props.onError) {
      this.props.onError(error, info.componentStack || "");
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            padding: 40,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>!</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>页面出错了</div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-2)",
              maxWidth: 500,
              marginBottom: 20,
              fontFamily: "monospace",
              background: "rgba(0,0,0,0.2)",
              padding: 12,
              borderRadius: 8,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {this.state.error?.message || "未知错误"}
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn btn-primary" onClick={this.handleReset}>
              重试
            </button>
            <button
              className="btn"
              onClick={() => window.location.reload()}
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
