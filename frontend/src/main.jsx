import React from "react";
import ReactDOM from "react-dom/client";
import App from "./pages/App.jsx";
import "./i18n";
import "./styles.css";

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: String(error?.message || error || "Unknown error") };
  }

  componentDidCatch(error, info) {
    // Keep details in console for debugging while showing a visible fallback in UI.
    console.error("Root render error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 24, fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
          <h2 style={{ marginTop: 0 }}>Application Error</h2>
          <p>An unexpected error prevented the app from rendering.</p>
          <pre style={{ whiteSpace: "pre-wrap", background: "#111", color: "#eee", padding: 12, borderRadius: 8 }}>
            {this.state.message}
          </pre>
          <p>Reload the page after fixing the error source.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>
);
