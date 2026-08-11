import { useState } from "react";
import { apiKeyStore } from "./api/client";
import { TenantProvider } from "./store/tenantStore";
import { Dashboard } from "./pages/Dashboard";

export default function App() {
  const [authenticated, setAuthenticated] = useState(() => Boolean(apiKeyStore.get()) || import.meta.env.DEV);
  const [key, setKey] = useState("");

  if (!authenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-canvas p-6">
        <form className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-sm" onSubmit={(event) => {
          event.preventDefault();
          if (!key.trim()) return;
          apiKeyStore.set(key.trim());
          setAuthenticated(true);
        }}>
          <h1 className="font-display text-xl text-ink">Dashboard access</h1>
          <p className="mt-2 text-sm text-ink-muted">Enter your administrator or tenant API key.</p>
          <input type="password" autoComplete="current-password" value={key} onChange={(event) => setKey(event.target.value)}
            className="mt-5 w-full rounded-lg border border-border px-3 py-2" aria-label="API key" />
          <button className="mt-3 w-full rounded-lg bg-ink px-3 py-2 font-semibold text-white">Continue</button>
        </form>
      </main>
    );
  }
  return (
    <TenantProvider>
      <Dashboard />
    </TenantProvider>
  );
}
