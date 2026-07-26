"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSettings, updateSettings, getApiKeys, updateApiKeys, triggerResearchNow, triggerMatchNow, triggerCleanupSkipped, getHunterUsage } from "@/lib/api";
import { useState, useEffect } from "react";
import { Save, Plus, Trash2, Key, RefreshCw, Settings2 } from "lucide-react";

const TABS = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "api-keys", label: "API Keys", icon: Key },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState("general");
  const { data, isLoading } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const { data: apiKeyData } = useQuery({ queryKey: ["api-keys"], queryFn: getApiKeys });
  const [form, setForm] = useState<any>({});
  const [saved, setSaved] = useState(false);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [googlePlacesAccounts, setGooglePlacesAccounts] = useState<{ email: string; key: string }[]>([{ email: "", key: "" }]);
  const [apifyAccounts, setApifyAccounts] = useState<{ email: string; key: string }[]>([{ email: "", key: "" }]);
  const [apolloAccounts, setApolloAccounts] = useState<{ email: string; key: string }[]>([{ email: "", key: "" }]);
  const [lushaAccounts, setLushaAccounts] = useState<{ email: string; key: string }[]>([{ email: "", key: "" }]);
  const [hunterAccounts, setHunterAccounts] = useState<{ email: string; key: string }[]>([{ email: "", key: "" }]);
  const [apiSaved, setApiSaved] = useState(false);
  const [researching, setResearching] = useState(false);
  const [matching, setMatching] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const { data: hunterUsageData } = useQuery({ queryKey: ["hunter-usage"], queryFn: getHunterUsage, staleTime: 60_000 });

  const parseAccounts = (raw: string) => {
    const parts = (raw || "").split(",").map((s) => s.trim()).filter(Boolean);
    return parts.map((p) => {
      const [email, key] = p.split("|");
      return { email: email || "", key: key || "" };
    });
  };
  const serializeAccounts = (accounts: { email: string; key: string }[]) =>
    accounts.filter((a) => a.key.trim()).map((a) => `${a.email.trim()}|${a.key.trim()}`).join(",");

  useEffect(() => { if (data) setForm(data); }, [data]);
  useEffect(() => {
    if (apiKeyData) {
      const apollo = parseAccounts(apiKeyData.apollo_api_keys || "");
      const lusha = parseAccounts(apiKeyData.lusha_api_keys || "");
      const hunter = parseAccounts(apiKeyData.hunter_api_keys || "");
      setApolloAccounts(apollo.length ? apollo : [{ email: "", key: "" }]);
      setLushaAccounts(lusha.length ? lusha : [{ email: "", key: "" }]);
      setHunterAccounts(hunter.length ? hunter : [{ email: "", key: "" }]);
      setAnthropicKey(apiKeyData.anthropic_api_key || "");
      setOpenaiKey(apiKeyData.openai_api_key || "");
      setGroqKey(apiKeyData.groq_api_key || "");
      const googlePlaces = parseAccounts(apiKeyData.google_places_api_key || "");
      setGooglePlacesAccounts(googlePlaces.length ? googlePlaces : [{ email: "", key: "" }]);
      const apify = parseAccounts(apiKeyData.apify_token || "");
      setApifyAccounts(apify.length ? apify : [{ email: "", key: "" }]);
    }
  }, [apiKeyData]);

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); setSaved(true); setTimeout(() => setSaved(false), 2000); },
  });

  const apiKeyMutation = useMutation({
    mutationFn: updateApiKeys,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["api-keys"] }); setApiSaved(true); setTimeout(() => setApiSaved(false), 2000); },
  });

  const handleSaveApiKeys = () => {
    apiKeyMutation.mutate({
      apollo_api_keys: serializeAccounts(apolloAccounts),
      lusha_api_keys: serializeAccounts(lushaAccounts),
      hunter_api_keys: serializeAccounts(hunterAccounts),
      anthropic_api_key: anthropicKey || undefined,
      openai_api_key: openaiKey || undefined,
      groq_api_key: groqKey || undefined,
      apify_token: serializeAccounts(apifyAccounts) || undefined,
      google_places_api_key: serializeAccounts(googlePlacesAccounts) || undefined,
    });
  };

  const handleResearchNow = async () => {
    setResearching(true);
    await triggerResearchNow();
    setTimeout(() => setResearching(false), 3000);
  };

  const handleCleanupNow = async () => {
    setCleaning(true);
    await triggerCleanupSkipped();
    setTimeout(() => setCleaning(false), 3000);
  };

  const handleMatchNow = async () => {
    setMatching(true);
    await triggerMatchNow();
    setTimeout(() => setMatching(false), 3000);
  };

  if (isLoading) return <div className="text-gray-500">Loading...</div>;

  const Toggle = ({ label, field, description }: { label: string; field: string; description?: string }) => (
    <div className="flex items-start justify-between py-4 border-b border-gray-100 last:border-0">
      <div>
        <p className="text-sm font-medium text-gray-900">{label}</p>
        {description && <p className="text-xs text-gray-500 mt-0.5">{description}</p>}
      </div>
      <button
        onClick={() => setForm((f: any) => ({ ...f, [field]: !f[field] }))}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ml-4 ${form[field] ? "bg-blue-600" : "bg-gray-300"}`}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${form[field] ? "translate-x-6" : "translate-x-1"}`} />
      </button>
    </div>
  );

  const AccountList = ({
    accounts, setAccounts, keyPlaceholder,
  }: { accounts: { email: string; key: string }[]; setAccounts: (a: { email: string; key: string }[]) => void; keyPlaceholder: string }) => (
    <div className="space-y-2">
      {accounts.map((acc, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs text-gray-400 w-5 text-right flex-shrink-0">{i + 1}.</span>
          <input
            type="email"
            value={acc.email}
            onChange={(e) => { const n = [...accounts]; n[i] = { ...n[i], email: e.target.value }; setAccounts(n); }}
            placeholder="account@email.com"
            className="w-44 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="password"
            value={acc.key}
            onChange={(e) => { const n = [...accounts]; n[i] = { ...n[i], key: e.target.value }; setAccounts(n); }}
            placeholder={keyPlaceholder}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {accounts.length > 1 && (
            <button onClick={() => setAccounts(accounts.filter((_, j) => j !== i))} className="text-gray-300 hover:text-red-400 transition-colors flex-shrink-0">
              <Trash2 size={14} />
            </button>
          )}
        </div>
      ))}
      <button
        onClick={() => setAccounts([...accounts, { email: "", key: "" }])}
        className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1 pt-1"
      >
        <Plus size={12} /> Add account
      </button>
    </div>
  );

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Configure automation behavior and API integrations</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* General Tab */}
      {activeTab === "general" && (
        <div className="space-y-5">
          <div className="flex justify-end">
            <button
              onClick={() => mutation.mutate(form)}
              className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700"
            >
              <Save size={15} />
              {saved ? "Saved!" : "Save Changes"}
            </button>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Approval Flow</h2>
            <p className="text-xs text-gray-400 mb-3">When enabled, all emails require manual approval before sending.</p>
            <Toggle label="Require approval for Job Applications" field="approval_enabled_jobs" description="All job application emails will wait for approval" />
            <Toggle label="Require approval for B2B Outreach" field="approval_enabled_b2b" description="All B2B outreach emails will wait for approval" />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Automation</h2>
            <Toggle label="Auto-scrape platforms" field="auto_scrape_enabled" description="Automatically scrape job platforms on schedule" />
            <Toggle label="Auto-apply to matched jobs" field="auto_apply_enabled" description="Automatically start application process for matched jobs" />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">CV Tailoring</h2>
            <p className="text-xs text-gray-400 mb-3">When enabled, the AI rewrites each CV for the specific job before attaching it to the email. Disabled by default — the original CV is sent as-is.</p>
            <Toggle label="AI CV tailoring per job" field="cv_tailoring_enabled" description="Rewrite summary, reorder skills, and tweak experience bullets to match each job description" />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Follow-up Schedule</h2>
            <p className="text-xs text-gray-500 mb-3">Days after initial email to send follow-ups (business days only).</p>
            <div className="flex gap-3">
              {[1, 2, 3].map((n) => (
                <div key={n}>
                  <label className="text-xs text-gray-500 block mb-1">Follow-up {n}</label>
                  <input
                    type="number"
                    min={1}
                    value={(form.followup_days || [2, 4, 6])[n - 1] || ""}
                    onChange={(e) => {
                      const days = [...(form.followup_days || [2, 4, 6])];
                      days[n - 1] = parseInt(e.target.value);
                      setForm((f: any) => ({ ...f, followup_days: days }));
                    }}
                    className="w-20 border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Excluded Countries</h2>
            <p className="text-xs text-gray-400 mb-3">Jobs and leads from these countries will be skipped (comma-separated).</p>
            <textarea
              value={(form.excluded_countries || []).join(", ")}
              onChange={(e) => setForm((f: any) => ({
                ...f,
                excluded_countries: e.target.value.split(",").map((c: string) => c.trim()).filter(Boolean),
              }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none"
              rows={2}
              placeholder="e.g. Russia, China, Iran"
            />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Send Time Window</h2>
            <p className="text-xs text-gray-400 mb-3">Emails will be scheduled within this window (recipient's local time).</p>
            <div className="flex items-center gap-3">
              <div>
                <label className="text-xs text-gray-500 block mb-1">From</label>
                <input
                  type="time"
                  value={form.send_time_start || "09:00"}
                  onChange={(e) => setForm((f: any) => ({ ...f, send_time_start: e.target.value }))}
                  className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">To</label>
                <input
                  type="time"
                  value={form.send_time_end || "11:00"}
                  onChange={(e) => setForm((f: any) => ({ ...f, send_time_end: e.target.value }))}
                  className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                />
              </div>
            </div>
          </div>

          {/* Rate limiting */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-1">Email Rate Limits</h3>
            <p className="text-xs text-gray-400 mb-4">Prevent spam flags by limiting how fast emails go out per sender account.</p>
            <div className="flex items-center gap-6">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Max emails per day <span className="text-gray-400">(per sender)</span></label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={form.daily_email_limit ?? 15}
                  onChange={(e) => setForm((f: any) => ({ ...f, daily_email_limit: parseInt(e.target.value) || 15 }))}
                  className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-24"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Min gap between emails <span className="text-gray-400">(minutes)</span></label>
                <input
                  type="number"
                  min={1}
                  max={120}
                  value={form.min_gap_minutes ?? 5}
                  onChange={(e) => setForm((f: any) => ({ ...f, min_gap_minutes: parseInt(e.target.value) || 5 }))}
                  className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-24"
                />
              </div>
            </div>
          </div>

          {/* Profile matching schedule */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-gray-800 mb-1">Profile Matching Schedule</h3>
                <p className="text-xs text-gray-400 mb-4">
                  How often the system scans all new &amp; skipped jobs and assigns them to the best matching profile.
                  Also runs automatically whenever you add or update a profile.
                </p>
              </div>
              <button
                onClick={handleMatchNow}
                disabled={matching}
                className="flex items-center gap-1.5 text-xs bg-blue-50 text-blue-700 border border-blue-200 px-3 py-2 rounded-lg hover:bg-blue-100 disabled:opacity-50 flex-shrink-0 ml-4"
              >
                <RefreshCw size={12} className={matching ? "animate-spin" : ""} />
                {matching ? "Running..." : "Match Now"}
              </button>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={1}
                max={24}
                value={form.profile_match_interval_hours ?? 1}
                onChange={(e) => setForm((f: any) => ({ ...f, profile_match_interval_hours: parseInt(e.target.value) || 1 }))}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-24"
              />
              <span className="text-sm text-gray-500">hours between automatic profile syncs</span>
            </div>
            <p className="text-[11px] text-gray-400 mt-2">Note: interval changes take effect after the Celery beat worker restarts. Use "Match Now" for an immediate run.</p>
          </div>

          {/* Auto-delete skipped jobs */}
          <div className="border border-gray-100 rounded-xl p-4 bg-gray-50">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700">Auto-Delete Skipped Jobs</h3>
              <button
                onClick={handleCleanupNow}
                disabled={cleaning}
                className="flex items-center gap-1.5 text-xs bg-red-50 text-red-700 border border-red-200 px-3 py-2 rounded-lg hover:bg-red-100 disabled:opacity-50"
              >
                <RefreshCw size={12} className={cleaning ? "animate-spin" : ""} />
                {cleaning ? "Running..." : "Run Now"}
              </button>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={0}
                max={365}
                value={form.skipped_job_retention_days ?? 0}
                onChange={(e) => setForm((f: any) => ({ ...f, skipped_job_retention_days: parseInt(e.target.value) || 0 }))}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-24"
              />
              <span className="text-sm text-gray-500">days — keep skipped jobs from last N days, delete the rest</span>
            </div>
            <p className="text-[11px] text-gray-400 mt-2">Set to 0 to disable. Runs automatically twice daily (2:00 AM &amp; 2:00 PM UTC). Only "Skipped" status jobs are removed.</p>
          </div>
        </div>
      )}

      {/* API Keys Tab */}
      {activeTab === "api-keys" && (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">Add multiple accounts per service — system rotates through all keys to maximise credits.</p>
            <div className="flex items-center gap-2">
              <button
                onClick={handleResearchNow}
                disabled={researching}
                className="flex items-center gap-1.5 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-2 rounded-lg hover:bg-emerald-100 disabled:opacity-50"
              >
                <RefreshCw size={12} className={researching ? "animate-spin" : ""} />
                {researching ? "Queued..." : "Research Now"}
              </button>
              <button
                onClick={handleSaveApiKeys}
                className="flex items-center gap-1.5 text-xs bg-blue-600 text-white px-3 py-2 rounded-lg hover:bg-blue-700"
              >
                <Save size={12} />
                {apiSaved ? "Saved!" : "Save Keys"}
              </button>
            </div>
          </div>

          {/* Apollo */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-orange-500 flex items-center justify-center text-white text-[11px] font-bold">A</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Apollo.io</p>
                <p className="text-xs text-gray-400">Primary — finds name, email, phone & LinkedIn</p>
              </div>
            </div>
            <div className="flex gap-2 text-[11px] text-gray-400 mb-2 pl-7">
              <span className="w-5" />
              <span className="w-44">Email (label only)</span>
              <span>API Key</span>
            </div>
            <AccountList accounts={apolloAccounts} setAccounts={setApolloAccounts} keyPlaceholder="Apollo API key..." />
          </div>

          {/* Lusha */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-purple-500 flex items-center justify-center text-white text-[11px] font-bold">L</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Lusha</p>
                <p className="text-xs text-gray-400">Fallback when Apollo doesn't find a result</p>
              </div>
            </div>
            <div className="flex gap-2 text-[11px] text-gray-400 mb-2 pl-7">
              <span className="w-5" />
              <span className="w-44">Email (label only)</span>
              <span>API Key</span>
            </div>
            <AccountList accounts={lushaAccounts} setAccounts={setLushaAccounts} keyPlaceholder="Lusha API key..." />
          </div>

          {/* Hunter */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-yellow-500 flex items-center justify-center text-white text-[11px] font-bold">H</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Hunter.io <span className="ml-1 text-[11px] bg-emerald-50 text-emerald-600 border border-emerald-200 px-2 py-0.5 rounded-full font-normal">✓ Working</span></p>
                <p className="text-xs text-gray-400">Finds emails by company domain — 50 free searches/month per account</p>
              </div>
            </div>
            <div className="flex gap-2 text-[11px] text-gray-400 mb-2 pl-7">
              <span className="w-5" />
              <span className="w-44">Email (label only)</span>
              <span className="flex-1">API Key</span>
              <span className="w-40 text-right">Usage / Resets</span>
            </div>
            <AccountList accounts={hunterAccounts} setAccounts={setHunterAccounts} keyPlaceholder="Hunter API key..." />
            {/* Usage stats per key */}
            {(hunterUsageData?.keys || []).length > 0 && (
              <div className="mt-3 space-y-1.5 pl-7">
                {(hunterUsageData.keys as any[]).map((k: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="text-gray-400 w-44 truncate">{k.email || k.key_prefix}</span>
                    <div className="flex-1 flex items-center gap-1.5">
                      {/* usage bar */}
                      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${k.exhausted ? "bg-red-400" : k.used / k.available > 0.7 ? "bg-amber-400" : "bg-emerald-400"}`}
                          style={{ width: `${Math.min(100, ((k.used ?? 0) / (k.available ?? 50)) * 100)}%` }}
                        />
                      </div>
                      <span className={`font-medium ${k.exhausted ? "text-red-500" : "text-gray-600"}`}>
                        {k.used ?? "?"}/{k.available ?? 50}
                      </span>
                      {k.exhausted && (
                        <span className="text-red-400 font-medium">· Exhausted</span>
                      )}
                    </div>
                    {k.reset_date && (
                      <span className="text-gray-400 whitespace-nowrap">
                        Resets {new Date(k.reset_date).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Google */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-blue-500 flex items-center justify-center text-white text-[11px] font-bold">G</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">
                  Google Search
                  <span className="ml-2 text-[11px] bg-emerald-50 text-emerald-600 border border-emerald-200 px-2 py-0.5 rounded-full font-normal">Always active · no key needed</span>
                </p>
                <p className="text-xs text-gray-400 mt-0.5">Last fallback — finds LinkedIn profile URL from public Google results</p>
              </div>
            </div>
          </div>

          {/* Groq */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-orange-400 flex items-center justify-center text-white text-[10px] font-bold">G</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Groq <span className="ml-1 text-[11px] bg-emerald-50 text-emerald-600 border border-emerald-200 px-2 py-0.5 rounded-full font-normal">✓ Active · Free</span></p>
                <p className="text-xs text-gray-400">Email generation & job summaries — free 14,400 requests/day</p>
              </div>
            </div>
            <input
              type="password"
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              placeholder="gsk_..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* OpenAI */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center text-white text-[10px] font-bold">AI</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">OpenAI (GPT-4o-mini)</p>
                <p className="text-xs text-gray-400">Fallback AI — used if Groq is unavailable</p>
              </div>
            </div>
            <input
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-proj-..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Anthropic */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-slate-700 flex items-center justify-center text-white text-[10px] font-bold">CL</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Anthropic (Claude)</p>
                <p className="text-xs text-gray-400">Fallback AI — used if Groq and OpenAI are unavailable</p>
              </div>
            </div>
            <input
              type="password"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Apify */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-[#FF9012] flex items-center justify-center text-white text-[10px] font-bold">AP</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Apify <span className="ml-1 text-[11px] bg-blue-50 text-blue-600 border border-blue-200 px-2 py-0.5 rounded-full font-normal">LinkedIn Scraper</span></p>
                <p className="text-xs text-gray-400">Used to scrape LinkedIn Jobs — free tier gives $5/month credit (~500 job scrapes)</p>
              </div>
            </div>
            <AccountList accounts={apifyAccounts} setAccounts={setApifyAccounts} keyPlaceholder="apify_api_..." />
            <p className="text-[11px] text-gray-400 mt-2">Get your token at apify.com → Settings → Integrations → Personal API tokens. Add multiple accounts to rotate across them.</p>
          </div>

          {/* Google Places */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-[#4285F4] flex items-center justify-center text-white text-[10px] font-bold">GP</div>
              <div>
                <p className="text-sm font-semibold text-gray-800">Google Places <span className="ml-1 text-[11px] bg-green-50 text-green-600 border border-green-200 px-2 py-0.5 rounded-full font-normal">B2B Enrichment</span></p>
                <p className="text-xs text-gray-400">Used to find business phone numbers and verified domains for B2B leads</p>
              </div>
            </div>
            <AccountList accounts={googlePlacesAccounts} setAccounts={setGooglePlacesAccounts} keyPlaceholder="AIza..." />
            <p className="text-[11px] text-gray-400 mt-2">Get your key at console.cloud.google.com → APIs &amp; Services → Enable "Places API". Free tier: $200/month credit (~4,000 lookups). Add multiple accounts to rotate across them.</p>
          </div>
        </div>
      )}
    </div>
  );
}
