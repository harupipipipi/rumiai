import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import {
  cleanupLegacyApprovalCredentialsEarly,
} from "./lib/authorityApprovalBrowserToken";
import { installGlobalClientDiagnostics } from "./lib/clientDiagnostics";
import "./index.css";

cleanupLegacyApprovalCredentialsEarly();

installGlobalClientDiagnostics();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </React.StrictMode>,
);
