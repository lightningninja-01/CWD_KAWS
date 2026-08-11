import { useState } from "react";
import { api } from "../../api/client";
import { useTenantStore } from "../../store/tenantStore";
import type { BroadcastResult } from "../../types";

interface BroadcastDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BroadcastDrawer({ isOpen, onClose }: BroadcastDrawerProps) {
  const { activeTenant } = useTenantStore();
  const [templateName, setTemplateName] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [paramsInput, setParamsInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<BroadcastResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSend = async () => {
    if (!activeTenant || !templateName.trim()) return;
    setIsSending(true);
    setError(null);
    setResult(null);
    try {
      const job = await api.sendBroadcast({
        tenant_id: activeTenant.id,
        target_tags: tagsInput.split(",").map((t) => t.trim()).filter(Boolean),
        template_name: templateName.trim(),
        template_params: paramsInput.split(",").map((p) => p.trim()).filter(Boolean),
      });
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        const status = await api.getBroadcastStatus(activeTenant.id, job.job_id);
        if (status.status === "completed" && status.result) {
          setResult(status.result);
          return;
        }
        if (status.status === "failed") throw new Error(status.last_error || "Broadcast job failed");
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      throw new Error("Broadcast is still processing. Check again shortly.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Broadcast failed to send");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-ink/20 transition-opacity ${
          isOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-surface shadow-xl transition-transform ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
        role="dialog"
        aria-label="Broadcast campaign"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-display text-lg">New broadcast</h2>
          <button onClick={onClose} className="text-sm text-ink-muted hover:text-ink" aria-label="Close">
            Close
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <p className="text-sm text-ink-muted">
            Sending as <span className="font-medium text-ink">{activeTenant?.company_name ?? "—"}</span>. Broadcasts
            use a Meta-approved message template — free text isn't allowed for customer-initiated outreach.
          </p>

          <label className="block">
            <span className="text-sm font-medium text-ink">Template name</span>
            <input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="new_catalog_promo"
              className="mt-1.5 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-transparent"
              style={{ boxShadow: "none" }}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-ink">Target cohort (tags, comma-separated)</span>
            <input
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="vip, furniture_interest"
              className="mt-1.5 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-ink">Template parameters (comma-separated, optional)</span>
            <input
              value={paramsInput}
              onChange={(e) => setParamsInput(e.target.value)}
              placeholder="20% off, this weekend"
              className="mt-1.5 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none"
            />
          </label>

          {error && (
            <div className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{error}</div>
          )}

          {result && (
            <div className="rounded-lg border border-border bg-canvas px-3 py-3 text-sm">
              <p className="font-medium text-ink">
                Sent {result.total_sent} of {result.total_targeted}
              </p>
              {result.total_failed > 0 && (
                <p className="mt-1 text-ink-muted">
                  {result.total_failed} failed: {result.failed_numbers.join(", ")}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="border-t border-border px-5 py-4">
          <button
            onClick={handleSend}
            disabled={isSending || !templateName.trim() || !activeTenant}
            className="w-full rounded-lg py-2.5 text-sm font-semibold text-white transition-opacity disabled:opacity-40"
            style={{ backgroundColor: "var(--tenant-accent, #2563EB)" }}
          >
            {isSending ? "Sending…" : "Send broadcast"}
          </button>
        </div>
      </aside>
    </>
  );
}
