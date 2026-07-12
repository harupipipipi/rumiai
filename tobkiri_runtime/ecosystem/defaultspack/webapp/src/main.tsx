import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import {
  cleanupLegacyApprovalCredentialsEarly,
} from "./lib/authorityApprovalBrowserToken";
import { installGlobalClientDiagnostics } from "./lib/clientDiagnostics";
import "./index.css";

cleanupLegacyApprovalCredentialsEarly();

installGlobalClientDiagnostics();

// Wave 3 compatibility projection. Product surfaces live in a separate chunk;
// the root host bundle imports no feature screen. Wave 10 removes this alias
// after every builtin screen is represented by a profile-scoped contribution.
const CompatibilitySurface = lazy(() => import("./App"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <Suspense fallback={<main role="status">Loading selected interface…</main>}>
        <CompatibilitySurface />
      </Suspense>
    </AppErrorBoundary>
  </React.StrictMode>,
);
