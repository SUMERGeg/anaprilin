import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./app/App";
import "./app/styles.css";
import { clearLegacyServiceWorkers } from "./shared/pwa/register";

void clearLegacyServiceWorkers();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
