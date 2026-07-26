"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLeads, uploadLeads, exportLeads, approveLead, updateLead, deleteLead, createLead, scrapeLeads } from "@/lib/api";
import {
  Upload, Download, CheckCircle, XCircle, Globe, Building2, TrendingUp,
  Link2, Phone, Mail, Calendar, Clock, Pencil, Trash2, Plus, X,
  ExternalLink, Users, Send, RefreshCw,
} from "lucide-react";
import { useRef, useState, useCallback, useEffect } from "react";

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  new:              { label: "New",           cls: "bg-gray-100 text-gray-600" },
  pending_approval: { label: "Pending",       cls: "bg-amber-100 text-amber-700" },
  approved:         { label: "Approved",      cls: "bg-cyan-100 text-cyan-700" },
  scheduled:        { label: "Scheduled",     cls: "bg-blue-100 text-blue-700" },
  sending:          { label: "Sending…",      cls: "bg-indigo-100 text-indigo-600" },
  sent:             { label: "Sent",          cls: "bg-violet-100 text-violet-700" },
  opened:           { label: "Opened",        cls: "bg-indigo-100 text-indigo-700" },
  replied:          { label: "Replied",       cls: "bg-emerald-100 text-emerald-700" },
  cold:             { label: "Cold",          cls: "bg-gray-100 text-gray-400" },
  failed:           { label: "Failed",        cls: "bg-red-100 text-red-500" },
  interested:       { label: "Interested 🔥", cls: "bg-orange-100 text-orange-700" },
  won:              { label: "Won ✓",         cls: "bg-green-100 text-green-800" },
  lost:             { label: "Lost",          cls: "bg-red-100 text-red-500" },
};

const INDUSTRIES = [
  "SaaS / Tech", "E-Commerce", "Healthcare / MedTech", "Real Estate / PropTech",
  "Fintech", "EdTech", "Marketing / AdTech", "Logistics", "Other",
];

const EMPTY_LEAD = {
  company_name: "", company_website: "", company_linkedin: "", industry: "",
  company_size: "", country: "", company_description: "",
  contact_name: "", contact_title: "", contact_linkedin: "",
  contact_email: "", contact_phone: "", source: "manual",
};

const dash = <span className="text-gray-300">—</span>;

function fmt(dt?: string | null) {
  if (!dt) return null;
  return new Date(dt).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}
function fmtDate(dt?: string | null) {
  if (!dt) return null;
  return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return <>{dash}</>;
  const color = score >= 75 ? "text-emerald-700 bg-emerald-50 border-emerald-200"
    : score >= 50 ? "text-amber-700 bg-amber-50 border-amber-200"
    : "text-red-600 bg-red-50 border-red-200";
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-lg border ${color}`}>
      <TrendingUp size={9} />{score}
    </span>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="text-left px-3 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">{children}</th>;
}
function Td({ children, cls }: { children: React.ReactNode; cls?: string }) {
  return <td className={`px-3 py-3 align-top ${cls ?? ""}`}>{children}</td>;
}

function LeadModal({ initial, onClose, onSave, saving, title }: {
  initial: typeof EMPTY_LEAD & { id?: string };
  onClose: () => void;
  onSave: (data: any) => void;
  saving: boolean;
  title: string;
}) {
  const [form, setForm] = useState({ ...EMPTY_LEAD, ...initial });
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <Building2 size={15} className="text-blue-600" />
            </div>
            <h2 className="font-semibold text-gray-900">{title}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100"><X size={16} /></button>
        </div>

        <div className="p-6 space-y-5">
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Company Info</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 block mb-1">Company Name *</label>
                <input value={form.company_name} onChange={e => set("company_name", e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Website</label>
                <input value={form.company_website} onChange={e => set("company_website", e.target.value)}
                  placeholder="https://example.com"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Company LinkedIn</label>
                <input value={form.company_linkedin} onChange={e => set("company_linkedin", e.target.value)}
                  placeholder="https://linkedin.com/company/..."
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Industry</label>
                <select value={form.industry} onChange={e => set("industry", e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                  <option value="">Select industry</option>
                  {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Team Size</label>
                <input value={form.company_size} onChange={e => set("company_size", e.target.value)}
                  placeholder="e.g. 10–50"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Country</label>
                <input value={form.country} onChange={e => set("country", e.target.value)}
                  placeholder="United States"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 block mb-1">Business Summary</label>
                <textarea value={form.company_description} onChange={e => set("company_description", e.target.value)}
                  rows={3} placeholder="Brief description of what this company does…"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Contact Person</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Full Name</label>
                <input value={form.contact_name} onChange={e => set("contact_name", e.target.value)}
                  placeholder="John Smith"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Job Title</label>
                <input value={form.contact_title} onChange={e => set("contact_title", e.target.value)}
                  placeholder="CEO, CTO, Founder…"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Email Address</label>
                <input value={form.contact_email} onChange={e => set("contact_email", e.target.value)}
                  type="email" placeholder="john@example.com"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1">Phone Number</label>
                <input value={form.contact_phone} onChange={e => set("contact_phone", e.target.value)}
                  placeholder="+1 555 000 0000"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 block mb-1">Contact LinkedIn</label>
                <input value={form.contact_linkedin} onChange={e => set("contact_linkedin", e.target.value)}
                  placeholder="https://linkedin.com/in/..."
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100 sticky bottom-0 bg-white">
          <button onClick={onClose} className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">Cancel</button>
          <button onClick={() => {
            if (!form.company_name.trim()) { alert("Company name is required"); return; }
            onSave(form);
          }} disabled={saving}
            className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700 font-medium shadow-sm disabled:opacity-60">
            {saving ? "Saving…" : "Save Lead"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LeadsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [editLead, setEditLead] = useState<any>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleOne = useCallback((id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback((ids: string[]) => {
    setSelected(prev => prev.size === ids.length ? new Set() : new Set(ids));
  }, []);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const { data = [], isLoading } = useQuery({
    queryKey: ["leads", statusFilter],
    queryFn: () => getLeads(statusFilter ? { status: statusFilter } : undefined),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateLead(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["leads"] }); setEditLead(null); showToast("Lead updated"); },
    onError: () => showToast("Update failed", "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteLead(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["leads"] }); showToast("Lead deleted"); },
    onError: () => showToast("Delete failed", "error"),
  });

  const [bulkDeleting, setBulkDeleting] = useState(false);
  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selected.size} lead${selected.size !== 1 ? "s" : ""}? This cannot be undone.`)) return;
    setBulkDeleting(true);
    let failed = 0;
    for (const id of selected) {
      try { await deleteLead(id); } catch { failed++; }
    }
    setBulkDeleting(false);
    setSelected(new Set());
    qc.invalidateQueries({ queryKey: ["leads"] });
    showToast(failed ? `Deleted with ${failed} error(s)` : `Deleted ${selected.size} leads`);
  };

  const createMutation = useMutation({
    mutationFn: (data: any) => createLead(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["leads"] }); setShowAdd(false); showToast("Lead added"); },
    onError: () => showToast("Create failed", "error"),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => approveLead(id, action),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["leads"] }); showToast("Done"); },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadLeads(file),
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ["leads"] }); showToast(`Uploaded ${res.created} leads`); },
    onError: () => showToast("Upload failed", "error"),
  });

  const [scraping, setScraping] = useState(false);
  const [scrapeCountBefore, setScrapeCountBefore] = useState(0);
  const scrapeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopScrapePolling = useCallback(() => {
    if (scrapeTimerRef.current) { clearInterval(scrapeTimerRef.current); scrapeTimerRef.current = null; }
    setScraping(false);
  }, []);

  // Stop polling after 3 minutes regardless
  useEffect(() => {
    if (!scraping) return;
    const timeout = setTimeout(stopScrapePolling, 3 * 60 * 1000);
    return () => clearTimeout(timeout);
  }, [scraping, stopScrapePolling]);

  const [scrapeError, setScrapeError] = useState<string | null>(null);

  const scrapeMutation = useMutation({
    mutationFn: scrapeLeads,
    onSuccess: (res: any) => {
      setScrapeError(null);
      const currentCount = (data as any[]).length;
      setScrapeCountBefore(currentCount);
      setScraping(true);
      scrapeTimerRef.current = setInterval(() => {
        qc.invalidateQueries({ queryKey: ["leads"] });
      }, 4000);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      if (detail?.message) {
        setScrapeError(detail.message);
      } else {
        setScrapeError("Scrape failed — check that the Celery worker is running.");
      }
    },
  });

  const handleExport = async () => {
    const blob = await exportLeads();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "leads_export.xlsx"; a.click();
  };

  const leads = data as any[];
  const pending = leads.filter(l => l.status === "pending_approval").length;
  const hot     = leads.filter(l => l.status === "interested" || l.status === "replied").length;
  const sent    = leads.filter(l => l.status === "sent" || l.status === "opened").length;

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium ${toast.type === "success" ? "bg-emerald-600 text-white" : "bg-red-500 text-white"}`}>
          {toast.type === "success" ? <CheckCircle size={16} /> : <XCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {editLead && (
        <LeadModal title="Edit Lead" initial={editLead}
          onClose={() => setEditLead(null)}
          onSave={(d) => updateMutation.mutate({ id: editLead.id, data: d })}
          saving={updateMutation.isPending} />
      )}
      {showAdd && (
        <LeadModal title="Add Lead" initial={{ ...EMPTY_LEAD, id: undefined } as any}
          onClose={() => setShowAdd(false)}
          onSave={(d) => createMutation.mutate(d)}
          saving={createMutation.isPending} />
      )}

      {/* Scrape error banner */}
      {scrapeError && (
        <div className="flex items-start justify-between bg-red-50 border border-red-200 text-red-800 rounded-2xl px-5 py-3.5">
          <div className="flex items-start gap-3">
            <XCircle size={16} className="shrink-0 mt-0.5 text-red-500" />
            <div>
              <p className="font-semibold text-sm">Scraping could not start</p>
              <p className="text-red-600 text-xs mt-0.5">{scrapeError}</p>
            </div>
          </div>
          <button onClick={() => setScrapeError(null)} className="text-red-400 hover:text-red-700 ml-4">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Scraping live banner */}
      {scraping && (
        <div className="flex items-center justify-between bg-emerald-600 text-white rounded-2xl px-5 py-3.5 shadow-md">
          <div className="flex items-center gap-3">
            <RefreshCw size={16} className="animate-spin shrink-0" />
            <div>
              <p className="font-semibold text-sm">Scraping in progress…</p>
              <p className="text-emerald-100 text-xs mt-0.5">
                Apollo &amp; LinkedIn are being searched for startup leads (≤50 employees).
                {leads.length > scrapeCountBefore
                  ? ` +${leads.length - scrapeCountBefore} new lead${leads.length - scrapeCountBefore !== 1 ? "s" : ""} found so far.`
                  : " Results will appear automatically."}
              </p>
            </div>
          </div>
          <button onClick={stopScrapePolling}
            className="text-emerald-200 hover:text-white text-xs border border-emerald-400 hover:border-white px-3 py-1.5 rounded-lg transition-colors">
            Dismiss
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">B2B Leads</h1>
          <p className="text-gray-500 text-sm mt-1">
            {leads.length} leads in your pipeline
            {scraping && leads.length > scrapeCountBefore && (
              <span className="ml-2 text-emerald-600 font-semibold">
                +{leads.length - scrapeCountBefore} new
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white shadow-sm">
            <option value="">All Status</option>
            {Object.entries(STATUS_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <button onClick={() => scrapeMutation.mutate()} disabled={scrapeMutation.isPending || scraping}
            className="flex items-center gap-2 bg-emerald-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-emerald-700 shadow-sm font-medium disabled:opacity-60">
            <RefreshCw size={14} className={scraping ? "animate-spin" : ""} />
            {scraping ? "Scraping…" : "Scrape Now"}
          </button>
          <button onClick={handleExport} className="flex items-center gap-2 border border-gray-200 text-gray-700 px-3 py-2 rounded-xl text-sm bg-white shadow-sm hover:bg-gray-50">
            <Download size={14} /> Export
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={uploadMutation.isPending}
            className="flex items-center gap-2 border border-gray-200 text-gray-700 px-3 py-2 rounded-xl text-sm bg-white shadow-sm hover:bg-gray-50 disabled:opacity-60">
            <Upload size={14} /> {uploadMutation.isPending ? "Uploading…" : "Upload CSV"}
          </button>
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
            <Plus size={14} /> Add Lead
          </button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden"
            onChange={e => { if (e.target.files?.[0]) uploadMutation.mutate(e.target.files[0]); }} />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total leads",             value: leads.length, icon: Building2,  bg: "bg-blue-50",   ic: "text-blue-500" },
          { label: "Pending approval",         value: pending,      icon: Clock,      bg: "bg-amber-50",  ic: "text-amber-500" },
          { label: "Emails sent",              value: sent,         icon: Send,       bg: "bg-violet-50", ic: "text-violet-500" },
          { label: "Hot (replied/interested)", value: hot,          icon: TrendingUp, bg: "bg-orange-50", ic: "text-orange-500" },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl ${s.bg} flex items-center justify-center flex-shrink-0`}>
              <s.icon size={16} className={s.ic} />
            </div>
            <div>
              <p className="text-xl font-bold text-gray-900">{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
          <span className="text-sm font-semibold text-red-700">{selected.size} lead{selected.size !== 1 ? "s" : ""} selected</span>
          <button onClick={handleBulkDelete} disabled={bulkDeleting}
            className="flex items-center gap-1.5 text-xs font-semibold bg-red-600 text-white px-3 py-1.5 rounded-lg hover:bg-red-700 disabled:opacity-60 transition-colors">
            <Trash2 size={12} /> {bulkDeleting ? "Deleting…" : "Delete selected"}
          </button>
          <button onClick={() => setSelected(new Set())}
            className="text-xs text-red-500 hover:text-red-700 ml-auto">
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-x-auto">
        {isLoading ? (
          <div className="p-8 space-y-3 animate-pulse">
            {[...Array(5)].map((_, i) => <div key={i} className="h-14 bg-gray-100 rounded-xl" />)}
          </div>
        ) : leads.length === 0 ? (
          <div className="text-center py-20">
            <Globe size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-semibold">No leads yet</p>
            <p className="text-gray-400 text-sm mt-1">Add a lead manually or upload a CSV from Apollo / LinkedIn</p>
          </div>
        ) : (
          <table className="w-full text-sm" style={{ minWidth: 1600 }}>
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                <th className="px-3 py-3 w-10">
                  <input type="checkbox"
                    checked={selected.size === leads.length && leads.length > 0}
                    onChange={() => toggleAll(leads.map((l: any) => l.id))}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer" />
                </th>
                <Th>Company</Th>
                <Th>Website</Th>
                <Th>LinkedIn</Th>
                <Th>Contact</Th>
                <Th>Email</Th>
                <Th>Phone</Th>
                <Th>Team Size</Th>
                <Th>Country</Th>
                <Th>Scraped At</Th>
                <Th>Scheduled Send</Th>
                <Th>Sent From</Th>
                <Th>Follow-ups</Th>
                <Th>Business Summary</Th>
                <Th>Score</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {leads.map((lead: any) => {
                const cfg = STATUS_CONFIG[lead.status] || { label: lead.status, cls: "bg-gray-100 text-gray-600" };
                const websiteUrl = lead.company_website
                  ? (lead.company_website.startsWith("http") ? lead.company_website : `https://${lead.company_website}`)
                  : null;

                return (
                  <tr key={lead.id} className={`hover:bg-gray-50/70 transition-colors ${selected.has(lead.id) ? "bg-red-50/40" : ""}`}>
                    <td className="px-3 py-3 w-10">
                      <input type="checkbox"
                        checked={selected.has(lead.id)}
                        onChange={() => toggleOne(lead.id)}
                        className="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer" />
                    </td>
                    {/* Company */}
                    <Td>
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-100 to-violet-100 flex items-center justify-center flex-shrink-0">
                          <Building2 size={12} className="text-blue-600" />
                        </div>
                        <div>
                          <p className="font-semibold text-gray-900 text-sm whitespace-nowrap">{lead.company_name}</p>
                          {lead.industry && <p className="text-[10px] text-gray-400">{lead.industry}</p>}
                        </div>
                      </div>
                    </Td>

                    {/* Website */}
                    <Td>
                      {websiteUrl ? (
                        <a href={websiteUrl} target="_blank" rel="noreferrer"
                          className="flex items-center gap-1 text-blue-600 hover:underline text-xs whitespace-nowrap">
                          <Globe size={11} />
                          {lead.company_website.replace(/^https?:\/\//, "").replace(/\/$/, "").slice(0, 22)}
                          <ExternalLink size={9} />
                        </a>
                      ) : dash}
                    </Td>

                    {/* LinkedIn */}
                    <Td>
                      <div className="flex flex-col gap-1">
                        {lead.company_linkedin && (
                          <a href={lead.company_linkedin} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1 text-blue-600 hover:underline text-xs whitespace-nowrap">
                            <Link2 size={10} /> Company <ExternalLink size={9} />
                          </a>
                        )}
                        {lead.contact_linkedin && (
                          <a href={lead.contact_linkedin} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1 text-blue-600 hover:underline text-xs whitespace-nowrap">
                            <Link2 size={10} /> Contact <ExternalLink size={9} />
                          </a>
                        )}
                        {!lead.company_linkedin && !lead.contact_linkedin && dash}
                      </div>
                    </Td>

                    {/* Contact */}
                    <Td>
                      <p className="text-sm font-medium text-gray-800 whitespace-nowrap">{lead.contact_name || dash}</p>
                      {lead.contact_title && <p className="text-[11px] text-gray-400 whitespace-nowrap">{lead.contact_title}</p>}
                    </Td>

                    {/* Email */}
                    <Td>
                      {lead.contact_email ? (
                        <span className="flex items-center gap-1 text-xs text-gray-700 whitespace-nowrap">
                          <Mail size={10} className="text-gray-400 flex-shrink-0" />
                          {lead.contact_email}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Phone */}
                    <Td>
                      {lead.contact_phone ? (
                        <span className="flex items-center gap-1 text-xs text-gray-700 whitespace-nowrap">
                          <Phone size={10} className="text-gray-400 flex-shrink-0" />
                          {lead.contact_phone}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Team Size */}
                    <Td>
                      {lead.company_size ? (
                        <span className="flex items-center gap-1 text-xs text-gray-700 whitespace-nowrap">
                          <Users size={10} className="text-gray-400 flex-shrink-0" />
                          {lead.company_size}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Country */}
                    <Td>
                      <span className="text-xs text-gray-600 whitespace-nowrap">{lead.country || dash}</span>
                    </Td>

                    {/* Scraped At */}
                    <Td>
                      {fmtDate(lead.created_at) ? (
                        <span className="flex items-center gap-1 text-xs text-gray-600 whitespace-nowrap">
                          <Clock size={10} className="text-gray-400" />
                          {fmtDate(lead.created_at)}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Scheduled Send */}
                    <Td>
                      {fmt(lead.scheduled_at) ? (
                        <span className="flex items-center gap-1 text-xs text-gray-600 whitespace-nowrap">
                          <Calendar size={10} className="text-gray-400" />
                          {fmt(lead.scheduled_at)}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Sent From */}
                    <Td>
                      {lead.sender_email ? (
                        <span className="flex items-center gap-1 text-xs text-gray-700 whitespace-nowrap">
                          <Send size={10} className="text-gray-400 flex-shrink-0" />
                          {lead.sender_email}
                        </span>
                      ) : dash}
                    </Td>

                    {/* Follow-ups */}
                    <Td cls="text-center">
                      {lead.follow_up_count > 0
                        ? <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">{lead.follow_up_count}</span>
                        : dash}
                    </Td>

                    {/* Business Summary */}
                    <Td cls="max-w-[200px]">
                      {lead.company_description
                        ? <p className="text-xs text-gray-500 line-clamp-2">{lead.company_description}</p>
                        : dash}
                    </Td>

                    {/* Score */}
                    <Td><ScoreBadge score={lead.score} /></Td>

                    {/* Status */}
                    <Td>
                      <span className={`inline-flex text-[11px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${cfg.cls}`}>
                        {cfg.label}
                      </span>
                    </Td>

                    {/* Actions */}
                    <Td>
                      <div className="flex items-center gap-1 whitespace-nowrap">
                        {lead.status === "pending_approval" && (
                          <>
                            <button onClick={() => approveMutation.mutate({ id: lead.id, action: "approve" })}
                              title="Approve" className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors">
                              <CheckCircle size={14} />
                            </button>
                            <button onClick={() => approveMutation.mutate({ id: lead.id, action: "reject" })}
                              title="Reject" className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                              <XCircle size={14} />
                            </button>
                          </>
                        )}
                        <button onClick={() => setEditLead(lead)} title="Edit"
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => { if (confirm(`Delete ${lead.company_name}?`)) deleteMutation.mutate(lead.id); }}
                          title="Delete" className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
