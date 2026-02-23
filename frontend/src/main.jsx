import React from "react";
import ReactDOM from "react-dom/client";
import App from "./pages/App.jsx";
import "./i18n";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
