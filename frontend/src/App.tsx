import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { apiKeyStore } from "./api/client";
import { TenantProvider } from "./store/tenantStore";
import { Dashboard } from "./pages/Dashboard";
import { Demo } from "./pages/Demo";

function AdminRoute() {
  return (
    <TenantProvider>
      <Dashboard />
    </TenantProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/admin" element={<AdminRoute />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/" element={<Navigate to="/demo" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
