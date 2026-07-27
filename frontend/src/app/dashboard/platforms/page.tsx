"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPlatforms, createPlatform, updatePlatform, deletePlatform, triggerScrape, triggerScrapeAll, getHasDataUsage, getApifyUsage } from "@/lib/api";
import {
  Plus, Play, Globe, Pencil, Trash2, Check, X,
  RefreshCw, Clock, Briefcase, ToggleLeft, ToggleRight, ChevronDown, ChevronUp
} from "lucide-react";
import { useState } from "react";

const SCRAPE_TYPES = ["indeed", "linkedin", "weworkremotely", "wellfound", "remoteok", "remotive", "shine", "nauk", "bark", "custom"];

const TYPE_COLORS: Record<string, string> = {
  indeed:        "bg-blue-100 text-blue-700",
  linkedin:      "bg-sky-100 text-sky-700",
  weworkremotely:"bg-violet-100 text-violet-700",
  wellfound:     "bg-orange-100 text-orange-700",
  shine:         "bg-pink-100 text-pink-700",
  nauk:          "bg-teal-100 text-teal-700",
  bark:          "bg-green-100 text-green-700",
  custom:        "bg-gray-100 text-gray-600",
};

const PLATFORM_ICONS: Record<string, string> = {
  indeed: "IN", linkedin: "LI", weworkremotely: "WR", wellfound: "WF",
  shine: "SH", nauk: "NK", bark: "BK", custom: "CU",
};

const EMPTY_FORM = { name: "", url: "", scrape_type: "custom", keywords: "", scrape_frequency_hours: 24, extra_urls: [] as string[], api_keys: [] as {key: string, email: string, renew_date: string}[], scrapedo_token: "" };

function PlatformForm({
  initial, onSave, onCancel, title,
}: { initial: typeof EMPTY_FORM; onSave: (d: any) => void; onCancel: () => void; title: string }) {
  const [form, setForm] = useState(initial);
  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }));

  const addUrl = () => set("extra_urls", [...form.extra_urls, ""]);
  const removeUrl = (i: number) => set("extra_urls", form.extra_urls.filter((_, idx) => idx !== i));
  const updateUrl = (i: number, v: string) => set("extra_urls", form.extra_urls.map((u, idx) => idx === i ? v : u));

  const addKey = () => set("api_keys", [...form.api_keys, { key: "", email: "", renew_date: "" }]);
  const removeKey = (i: number) => set("api_keys", form.api_keys.filter((_, idx) => idx !== i));
  const updateKey = (i: number, field: "key" | "email" | "renew_date", v: string) => set("api_keys", form.api_keys.map((k, idx) => idx === i ? { ...k, [field]: v } : k));

  const handleSave = () => {
    const extra_feeds = form.extra_urls.map(u => u.trim()).filter(Boolean);
    const api_keys = form.api_keys.filter(k => k.key.trim()).map(k => ({ key: k.key.trim(), email: k.email.trim(), renew_date: (k as any).renew_date?.trim() || "" }));
    const scrape_config: any = {};
    if (extra_feeds.length > 0) scrape_config.extra_feeds = extra_feeds;
    if (api_keys.length > 0) scrape_config.api_keys = api_keys;
    if ((form as any).scrapedo_token?.trim()) scrape_config.scrapedo_token = (form as any).scrapedo_token.trim();
    if ((form as any).bark_email?.trim()) scrape_config.email = (form as any).bark_email.trim();
    if ((form as any).bark_password?.trim()) scrape_config.password = (form as any).bark_password.trim();
    onSave({ ...form, scrape_config: Object.keys(scrape_config).length > 0 ? scrape_config : null });
  };

  return (
    <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-6 space-y-5">
      <h2 className="font-semibold text-gray-900 text-base">{title}</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Platform Name *</label>
          <input value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. Indeed UK"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Type *</label>
          <select value={form.scrape_type} onChange={e => set("scrape_type", e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            {SCRAPE_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
          </select>
        </div>

        {/* Primary URL */}
        <div className="col-span-2">
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Primary URL *</label>
          <input value={form.url} onChange={e => set("url", e.target.value)} placeholder="https://..."
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>

        {/* Extra URLs */}
        <div className="col-span-2">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium text-gray-500">Additional URLs <span className="text-gray-400">(optional — scraper fetches all)</span></label>
            <button type="button" onClick={addUrl}
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium">
              <Plus size={12} /> Add URL
            </button>
          </div>
          {form.extra_urls.length === 0 && (
            <p className="text-xs text-gray-400 italic">No extra URLs — click "Add URL" to add more feed sources</p>
          )}
          <div className="space-y-2">
            {form.extra_urls.map((u, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input value={u} onChange={e => updateUrl(i, e.target.value)} placeholder="https://..."
                  className="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                <button type="button" onClick={() => removeUrl(i)}
                  className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-xl border border-gray-200 transition-colors">
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* HasData API Keys — Indeed only */}
        {(form.scrape_type === "indeed" || form.scrape_type === "linkedin") && (
          <div className="col-span-2">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium text-gray-500">
                {form.scrape_type === "linkedin" ? "Apify API Keys" : "HasData API Keys"}{" "}
                <span className="text-gray-400">(auto-rotates when one runs out)</span>
              </label>
              <button type="button" onClick={addKey}
                className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-700 font-medium">
                <Plus size={12} /> Add Key
              </button>
            </div>
            {form.api_keys.length === 0 && (
              <p className="text-xs text-gray-400 italic">
                No API keys — click "Add Key" to add your {form.scrape_type === "linkedin" ? "Apify" : "HasData"} API key
              </p>
            )}
            <div className="space-y-3">
              {form.api_keys.map((k, i) => (
                <div key={i} className="border border-gray-100 rounded-xl p-3 bg-gray-50 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${i === 0 ? "bg-emerald-100 text-emerald-700" : "bg-gray-200 text-gray-500"}`}>
                      {i === 0 ? "Primary" : `Backup ${i}`}
                    </span>
                    <button type="button" onClick={() => removeKey(i)}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                      <X size={12} />
                    </button>
                  </div>
                  <input value={k.email} onChange={e => updateKey(i, "email", e.target.value)}
                    placeholder="Signup email" type="email"
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-500" />
                  <input value={k.key} onChange={e => updateKey(i, "key", e.target.value)}
                    placeholder={form.scrape_type === "linkedin" ? "apify_api_..." : "API Key (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"}
                    type="password"
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono bg-white focus:outline-none focus:ring-2 focus:ring-violet-500" />
                  <div className="flex items-center gap-2">
                    <label className="text-[11px] text-gray-400 whitespace-nowrap">Renews on</label>
                    <input value={(k as any).renew_date || ""} onChange={e => updateKey(i, "renew_date", e.target.value)}
                      type="date"
                      className="flex-1 border border-gray-200 rounded-xl px-3 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-violet-500" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bark.com credentials */}
        {form.scrape_type === "bark" && (
          <div className="col-span-2 space-y-3">
            <p className="text-xs text-gray-500">
              Bark.com logs in with your account and scrapes available client requests from your leads dashboard.
            </p>
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Bark.com Email</label>
              <input
                value={(form as any).bark_email || ""}
                onChange={e => set("bark_email", e.target.value)}
                placeholder="you@example.com"
                type="email"
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Bark.com Password</label>
              <input
                value={(form as any).bark_password || ""}
                onChange={e => set("bark_password", e.target.value)}
                placeholder="Your password"
                type="password"
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>
          </div>
        )}

        {/* scrape.do Token — WellFound only */}
        {form.scrape_type === "wellfound" && (
          <div className="col-span-2">
            <label className="text-xs font-medium text-gray-500 block mb-1.5">
              scrape.do Token <span className="text-gray-400">(used to bypass Cloudflare on WellFound)</span>
            </label>
            <input
              value={(form as any).scrapedo_token || ""}
              onChange={e => set("scrapedo_token", e.target.value)}
              placeholder="your-scrape-do-token"
              type="password"
              className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-500"
            />
          </div>
        )}

        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Keywords <span className="text-gray-400">(comma-separated)</span></label>
          <input value={form.keywords} onChange={e => set("keywords", e.target.value)} placeholder="wordpress, react, java"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Auto-sync every (hours)</label>
          <input type="number" min={1} max={168} value={form.scrape_frequency_hours}
            onChange={e => set("scrape_frequency_hours", parseInt(e.target.value) || 24)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={handleSave}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
          <Check size={13} /> Save
        </button>
        <button onClick={onCancel}
          className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function PlatformsPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ["platforms"], queryFn: getPlatforms });
  const { data: hasDataUsage } = useQuery({ queryKey: ["hasdata-usage"], queryFn: getHasDataUsage, staleTime: 120_000 });
  const { data: apifyUsage } = useQuery({ queryKey: ["apify-usage"], queryFn: getApifyUsage, staleTime: 120_000 });

  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<typeof EMPTY_FORM>(EMPTY_FORM);
  const [scraping, setScraping] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  const createMutation = useMutation({
    mutationFn: createPlatform,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["platforms"] }); setShowAdd(false); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updatePlatform(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["platforms"] }); setEditId(null); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePlatform(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platforms"] }),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => updatePlatform(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platforms"] }),
  });

  const scrapeMutation = useMutation({
    mutationFn: (id: string) => triggerScrape(id),
    onSuccess: (_, id) => { setScraping(id); setTimeout(() => setScraping(null), 3000); qc.invalidateQueries({ queryKey: ["platforms"] }); },
  });

  const scrapeAllMutation = useMutation({
    mutationFn: triggerScrapeAll,
    onSuccess: () => { setSyncingAll(true); setTimeout(() => setSyncingAll(false), 4000); qc.invalidateQueries({ queryKey: ["platforms"] }); },
  });

  const totalJobs = (data as any[]).reduce((sum: number, p: any) => sum + (p.total_jobs_synced || 0), 0);
  const activePlatforms = (data as any[]).filter((p: any) => p.is_active).length;

  if (isLoading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-44" />
      {[...Array(3)].map((_, i) => <div key={i} className="h-28 bg-gray-100 rounded-2xl" />)}
    </div>
  );

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Platforms</h1>
          <p className="text-gray-500 text-sm mt-1">Manage job scraping sources and sync schedules</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => scrapeAllMutation.mutate()}
            disabled={scrapeAllMutation.isPending || syncingAll}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
              syncingAll
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50 shadow-sm"
            }`}
          >
            <RefreshCw size={14} className={scrapeAllMutation.isPending ? "animate-spin" : ""} />
            {syncingAll ? "All Queued!" : "Sync All"}
          </button>
          <button onClick={() => { setShowAdd(true); setEditId(null); }}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
            <Plus size={14} /> Add Platform
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center"><Globe size={18} className="text-blue-600" /></div>
          <div><p className="text-2xl font-bold text-gray-900">{(data as any[]).length}</p><p className="text-xs text-gray-500">Total platforms</p></div>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center"><RefreshCw size={18} className="text-emerald-600" /></div>
          <div><p className="text-2xl font-bold text-gray-900">{activePlatforms}</p><p className="text-xs text-gray-500">Auto-syncing</p></div>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center"><Briefcase size={18} className="text-violet-600" /></div>
          <div><p className="text-2xl font-bold text-gray-900">{totalJobs}</p><p className="text-xs text-gray-500">Total jobs synced</p></div>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <PlatformForm
          title="Add New Platform"
          initial={EMPTY_FORM}
          onSave={(d) => createMutation.mutate(d)}
          onCancel={() => setShowAdd(false)}
        />
      )}

      {/* Platform cards */}
      <div className="space-y-3">
        {(data as any[]).map((p: any) => {
          const isEditing = editId === p.id;
          const typeColor = TYPE_COLORS[p.scrape_type] || TYPE_COLORS.custom;
          const initials = PLATFORM_ICONS[p.scrape_type] || "??";
          const lastSync = p.last_scraped_at
            ? new Date(p.last_scraped_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
            : "Never";

          return (
            <div key={p.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              {isEditing ? (
                <div className="p-6">
                  <PlatformForm
                    title={`Edit — ${p.name}`}
                    initial={{ name: p.name, url: p.url, scrape_type: p.scrape_type, keywords: p.keywords || "", scrape_frequency_hours: p.scrape_frequency_hours || 24, extra_urls: p.scrape_config?.extra_feeds || [], api_keys: (p.scrape_config?.api_keys || []).map((k: any) => typeof k === "string" ? { key: k, email: "", renew_date: "" } : { renew_date: "", ...k }), scrapedo_token: p.scrape_config?.scrapedo_token || "", bark_email: p.scrape_config?.email || "", bark_password: p.scrape_config?.password || "" } as any}
                    onSave={(d) => updateMutation.mutate({ id: p.id, data: d })}
                    onCancel={() => setEditId(null)}
                  />
                </div>
              ) : (
                <div className="p-5">
                  <div className="flex items-start gap-4">
                    {/* Icon */}
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center text-xs font-bold flex-shrink-0 ${typeColor}`}>
                      {initials}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-semibold text-gray-900 text-[15px]">{p.name}</span>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide ${typeColor}`}>
                          {p.scrape_type}
                        </span>
                        <span className={`flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${p.is_active ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${p.is_active ? "bg-emerald-500" : "bg-gray-400"}`} />
                          {p.is_active ? "Auto-sync ON" : "Auto-sync OFF"}
                        </span>
                      </div>

                      <a href={p.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-500 hover:underline truncate block max-w-md">{p.url}</a>
                      {p.scrape_config?.extra_feeds?.map((u: string, i: number) => (
                        <a key={i} href={u} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-blue-400 hover:underline truncate block max-w-md">+ {u}</a>
                      ))}
                      {p.scrape_config?.api_keys?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {p.scrape_config.api_keys.map((k: any, i: number) => {
                            const email = k.email || "";
                            const isLinkedIn = p.name === "LinkedIn Jobs";
                            const usagePool = isLinkedIn ? (apifyUsage?.keys || []) : (hasDataUsage?.keys || []);
                            const usageKey = usagePool.find((u: any) => u.email === email || u.key_prefix === (k.key || "").slice(0, isLinkedIn ? 16 : 8) + "...");
                            const renewDatePast = k.renew_date && new Date(k.renew_date) <= new Date();
                            const exhausted = usageKey?.status === "exhausted" && !renewDatePast;
                            const active = usageKey?.status === "active";
                            const renewStr = k.renew_date
                              ? renewDatePast
                                ? ` · Renewed ${new Date(k.renew_date).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`
                                : ` · Renews ${new Date(k.renew_date).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`
                              : (exhausted ? " · Renews monthly" : "");
                            return (
                              <span key={i} className={`text-[11px] px-2 py-0.5 rounded-full font-medium border flex items-center gap-1 ${
                                exhausted ? "text-red-600 bg-red-50 border-red-200" :
                                active ? "text-emerald-700 bg-emerald-50 border-emerald-200" :
                                "text-violet-600 bg-violet-50 border-violet-100"
                              }`}>
                                🔑 {i === 0 ? "Primary" : `Backup ${i}`}
                                {email ? ` — ${email}` : ""}
                                {exhausted && <span className="ml-1 text-red-500 font-semibold">· Exhausted{renewStr}</span>}
                                {active && <span className="ml-1 text-emerald-600">· Active{renewStr}</span>}
                                {!exhausted && !active && renewStr && <span className="ml-1 text-gray-400">{renewStr}</span>}
                              </span>
                            );
                          })}
                        </div>
                      )}

                      <div className="flex items-center gap-4 mt-2 flex-wrap">
                        {p.keywords && (
                          <span className="text-xs text-gray-500">
                            🔍 <span className="font-medium">{p.keywords}</span>
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-gray-400">
                          <Clock size={10} /> Every {p.scrape_frequency_hours}h
                        </span>
                        <span className="flex items-center gap-1 text-xs text-gray-400">
                          <RefreshCw size={10} /> Last: {lastSync}
                        </span>
                        <span className="flex items-center gap-1 text-xs font-semibold text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">
                          <Briefcase size={10} /> {p.total_jobs_synced ?? 0} jobs synced
                        </span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {/* Sync Now */}
                      <button
                        onClick={() => scrapeMutation.mutate(p.id)}
                        disabled={scrapeMutation.isPending}
                        className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl border transition-all ${
                          scraping === p.id
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-blue-600 text-white border-blue-600 hover:bg-blue-700 shadow-sm"
                        }`}
                        title="Sync Now"
                      >
                        <RefreshCw size={12} className={scrapeMutation.isPending ? "animate-spin" : ""} />
                        {scraping === p.id ? "Queued!" : "Sync Now"}
                      </button>

                      {/* Auto-sync toggle */}
                      <button
                        onClick={() => toggleMutation.mutate({ id: p.id, is_active: !p.is_active })}
                        className={`p-2 rounded-xl border transition-colors ${p.is_active ? "text-emerald-600 bg-emerald-50 border-emerald-200 hover:bg-emerald-100" : "text-gray-400 bg-gray-50 border-gray-200 hover:bg-gray-100"}`}
                        title={p.is_active ? "Disable auto-sync" : "Enable auto-sync"}
                      >
                        {p.is_active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                      </button>

                      {/* Edit */}
                      <button
                        onClick={() => setEditId(p.id)}
                        className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-blue-600 hover:bg-blue-50 hover:border-blue-200 transition-colors"
                        title="Edit"
                      >
                        <Pencil size={14} />
                      </button>

                      {/* Delete */}
                      <button
                        onClick={() => { if (confirm(`Delete "${p.name}"? This won't delete scraped jobs.`)) deleteMutation.mutate(p.id); }}
                        className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-red-500 hover:bg-red-50 hover:border-red-200 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {(data as any[]).length === 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
            <Globe size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-600 font-semibold">No platforms added yet</p>
            <p className="text-gray-400 text-sm mt-1">Add Indeed, LinkedIn, WeWorkRemotely or a custom URL to start scraping</p>
            <button onClick={() => setShowAdd(true)} className="mt-4 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 font-medium">
              Add Your First Platform
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
