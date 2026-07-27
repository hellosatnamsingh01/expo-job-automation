"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getJobs, createJob, uploadJobs, exportJobs, triggerApply, applyNow, updateJob, deleteJob, bulkDeleteJobs, getProfiles, getActivities, rescheduleJob as apiRescheduleJob, rescheduleFollowup as apiRescheduleFollowup, assignProfileToJob, uploadJobCV, deleteJobCV } from "@/lib/api";
import {
  Upload, Download, Briefcase, ExternalLink, Plus, MapPin,
  Mail, Pencil, Trash2, RefreshCw, Check, X, FileText, Phone,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Zap, Loader2, CheckCircle2, AlertCircle,
  Send, Eye, Reply, AlarmClock, Clock, Activity, Settings, Search
} from "lucide-react";
import { useRef, useState, useMemo } from "react";

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  new:         { label: "New",         cls: "bg-gray-100 text-gray-600 border-gray-200" },
  matched:     { label: "Matched",     cls: "bg-blue-100 text-blue-700 border-blue-200" },
  researching: { label: "Researching", cls: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  ready:       { label: "Ready",       cls: "bg-cyan-100 text-cyan-700 border-cyan-200" },
  scheduled:   { label: "Scheduled",   cls: "bg-cyan-100 text-cyan-700 border-cyan-200" },
  applied:     { label: "Applied",     cls: "bg-violet-100 text-violet-700 border-violet-200" },
  followed_up: { label: "Follow-up",   cls: "bg-orange-100 text-orange-700 border-orange-200" },
  replied:     { label: "Replied ✓",   cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  cold:        { label: "Cold",        cls: "bg-red-100 text-red-500 border-red-200" },
  skipped:     { label: "Skipped",     cls: "bg-gray-100 text-gray-400 border-gray-200" },
  blacklisted: { label: "Blacklisted", cls: "bg-red-50 text-red-400 border-red-100" },
  bounced:     { label: "Bounced ↩",   cls: "bg-rose-100 text-rose-700 border-rose-200" },
};

const STATUSES = ["new","matched","researching","ready","scheduled","applied","followed_up","replied","cold","skipped","bounced"];
const PAGE_SIZE_OPTIONS = [20, 30, 50];

function fmt(dt: string | null | undefined) {
  if (!dt) return null;
  return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
}
function Dash() { return <span className="text-gray-300 text-xs">—</span>; }

const BLANK_CONTACT = { name: "", title: "", email: "", phone: "", linkedin_url: "", is_primary: false };

// ── Activity helpers ──────────────────────────────────────────────────────────
const ACT_STATUS: Record<string, { icon: any; color: string; label: string }> = {
  sent:             { icon: Send,       color: "text-blue-600 bg-blue-50 border-blue-200",       label: "Sent" },
  opened:           { icon: Eye,        color: "text-violet-600 bg-violet-50 border-violet-200", label: "Opened" },
  replied:          { icon: Reply,      color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Replied" },
  pending_approval: { icon: Clock,      color: "text-amber-600 bg-amber-50 border-amber-200",    label: "Pending" },
  scheduled:        { icon: AlarmClock, color: "text-cyan-600 bg-cyan-50 border-cyan-200",       label: "Scheduled" },
  pending:          { icon: AlarmClock, color: "text-cyan-600 bg-cyan-50 border-cyan-200",       label: "Scheduled" },
};

// Convert UTC datetime string to IST (UTC+5:30) for display
function toIST(dt: string | null | undefined): Date | null {
  if (!dt) return null;
  const d = new Date(dt.endsWith("Z") || dt.includes("+") ? dt : dt + "Z");
  return new Date(d.getTime() + 5.5 * 60 * 60 * 1000);
}
function fmtDT(dt: string | null | undefined, ist = false) {
  if (!dt) return "—";
  const d = ist ? toIST(dt) : new Date(dt);
  if (!d) return "—";
  return d.toLocaleString("en-IN", {
    month: "short", day: "numeric", year: "2-digit",
    hour: "numeric", minute: "2-digit", hour12: true,
  }) + " IST";
}
function fmtScheduleIST(dt: string | null | undefined) {
  if (!dt) return null;
  const d = toIST(dt);
  if (!d) return null;
  return d.toLocaleString("en-IN", {
    month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
  }) + " IST";
}
function formatLocation(country: string | null, location: string | null): string {
  const raw = (country || location || "").trim();
  if (!raw) return "";
  // Priority keywords — return immediately if found
  const lower = raw.toLowerCase();
  if (lower.includes("remote")) return "Remote";
  if (lower.includes("anywhere")) return "Anywhere";
  if (lower.includes("worldwide")) return "Worldwide";
  if (lower.includes("hybrid")) return "Hybrid";
  // If it's a comma-separated list of cities, just return the country field if it's short
  // otherwise take the first token before the comma
  if (raw.includes(",")) return raw.split(",")[0].trim();
  // If longer than 20 chars, truncate
  return raw.length > 20 ? raw.slice(0, 20) + "…" : raw;
}

// Convert local datetime-local input value to UTC ISO string
function localToUTC(localStr: string): string {
  // datetime-local gives "YYYY-MM-DDTHH:MM" in IST — convert to UTC
  const d = new Date(localStr); // browser treats as local tz
  return d.toISOString();
}
// Convert UTC string to datetime-local input value (IST)
function utcToISTInput(dt: string | null | undefined): string {
  if (!dt) return "";
  const d = toIST(dt);
  if (!d) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function JobActivityTab({ jobId }: { jobId: string }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["activities", jobId],
    queryFn: () => getActivities({ job_id: jobId }),
  });
  const events = data as any[];

  if (isLoading) return (
    <div className="space-y-3 py-4">
      {[1,2,3].map(i => <div key={i} className="h-16 bg-gray-100 rounded-xl animate-pulse" />)}
    </div>
  );

  if (events.length === 0) return (
    <div className="py-12 text-center">
      <Activity size={32} className="text-gray-200 mx-auto mb-3" />
      <p className="text-gray-500 font-medium text-sm">No activity yet</p>
      <p className="text-gray-400 text-xs mt-1">Use "Apply Now" to send the first email for this job</p>
    </div>
  );

  return (
    <div className="space-y-3 py-1">
      {events.map((ev: any) => {
        const isFollowup = ev.type === "followup";
        const meta = ACT_STATUS[ev.status] || { icon: Activity, color: "text-gray-500 bg-gray-50 border-gray-200", label: ev.status };
        const Icon = meta.icon;
        const time = ev.sent_at || ev.scheduled_at;
        const isPending = !ev.sent_at && ev.scheduled_at;
        return (
          <div key={ev.id} className={`rounded-xl border p-3.5 ${isFollowup ? "ml-6 border-orange-100 bg-orange-50/30" : "border-gray-100 bg-gray-50/40"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2.5 min-w-0">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${isFollowup ? "bg-orange-100" : "bg-blue-50"}`}>
                  {isFollowup ? <RefreshCw size={13} className="text-orange-500" /> : <Mail size={13} className="text-blue-600" />}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {isFollowup && (
                      <span className="text-[10px] font-bold text-orange-600 bg-orange-100 px-1.5 py-0.5 rounded-full">FU#{ev.followup_number}</span>
                    )}
                    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${meta.color}`}>
                      <Icon size={9} />{meta.label}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-gray-700 mt-1 truncate">✉ {ev.subject}</p>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    {isPending ? "Scheduled →" : "Sent →"} <span className="font-medium text-gray-600">{ev.to_email}</span>
                    {ev.to_name ? ` (${ev.to_name})` : ""}
                  </p>
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-[11px] font-semibold text-gray-600 whitespace-nowrap">{fmtDT(time, true)}</p>
                {isPending && <p className="text-[10px] text-cyan-600 font-medium mt-0.5">Scheduled</p>}
                {ev.email_opened && <p className="text-[10px] text-violet-600 font-medium mt-0.5">👁 Opened</p>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Create Job Modal ──────────────────────────────────────────────────────────
function CreateJobModal({ onClose, onCreate }: { onClose: () => void; onCreate: (data: any) => void }) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    title: "", company_name: "", company_website: "", location: "", country: "",
    job_url: "", apply_url: "", job_description: "", industry: "",
  });
  const [contact, setContact] = useState({ name: "", email: "", phone: "", title: "" });
  const setF = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));
  const setC = (k: string, v: string) => setContact(p => ({ ...p, [k]: v }));

  const field = (key: string, label: string, placeholder = "", textarea = false) => (
    <div key={key}>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {textarea
        ? <textarea value={(form as any)[key]} onChange={e => setF(key, e.target.value)}
            placeholder={placeholder} rows={4}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
        : <input value={(form as any)[key]} onChange={e => setF(key, e.target.value)}
            placeholder={placeholder}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />}
    </div>
  );

  const handleSave = async () => {
    if (!form.title) return;
    setSaving(true);
    try {
      const payload = {
        ...form,
        uploaded_manually: true,
        contacts: contact.email ? [{ ...contact, is_primary: true }] : [],
      };
      onCreate(payload);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-8" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100">
          <div>
            <h2 className="font-bold text-gray-900 text-base">Add Manual Job</h2>
            <p className="text-xs text-gray-400 mt-0.5">Profile will be auto-matched and email scheduled</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100"><X size={16} /></button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Job details */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Job Details</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">{field("title", "Job Title *", "e.g. Senior WordPress Developer")}</div>
              {field("company_name", "Company Name", "e.g. Acme Corp")}
              {field("company_website", "Company Website", "https://acme.com")}
              {field("industry", "Industry", "e.g. SaaS / E-Commerce")}
              {field("location", "Location", "e.g. London, UK")}
              {field("country", "Country", "e.g. United Kingdom")}
              {field("job_url", "Job URL (listing page)", "https://jobs.wordpress.net/job/...")}
              {field("apply_url", "Apply URL (direct link or mailto:)", "https://company.com/apply or mailto:hr@company.com")}
              <div className="col-span-2">{field("job_description", "Job Description", "Paste the full job description here — used for skill matching and email generation", true)}</div>
            </div>
          </div>

          {/* Hiring contact */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Hiring Contact <span className="text-gray-300 font-normal">(optional but needed to send email)</span></p>
            <div className="grid grid-cols-2 gap-3">
              {(["name","title","email","phone"] as const).map(k => (
                <div key={k}>
                  <label className="block text-xs font-medium text-gray-500 mb-1 capitalize">{k === "name" ? "Full Name" : k === "title" ? "Job Title" : k === "email" ? "Email Address" : "Phone"}</label>
                  <input value={contact[k]} onChange={e => setC(k, e.target.value)}
                    placeholder={k === "email" ? "hiring@company.com" : ""}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </div>
              ))}
            </div>
          </div>

          {!contact.email && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-amber-700">
              ⚠ No hiring contact email — profile will be matched but email won't be scheduled until you add a contact email.
            </div>
          )}
        </div>

        <div className="flex gap-2 px-6 pb-6">
          <button onClick={onClose}
            className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
            Cancel
          </button>
          <button onClick={handleSave} disabled={!form.title || saving}
            className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Add Job & Start Pipeline
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Modal (tabbed) ───────────────────────────────────────────────────────
function EditModal({ job, onClose, onSave }: { job: any; onClose: () => void; onSave: (data: any) => void }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"details" | "activity">("details");
  const [form, setForm] = useState({
    title: job.title || "",
    company_name: job.company_name || "",
    company_linkedin_url: job.company_linkedin_url || "",
    company_website: job.company_website || "",
    industry: job.industry || "",
    location: job.location || "",
    country: job.country || "",
    timezone: job.timezone || "",
    job_url: job.job_url || "",
    apply_url: job.apply_url || "",
    job_description: job.job_description || "",
    company_size: job.company_size || "",
    status: job.status || "new",
  });
  const [contacts, setContacts] = useState<any[]>(
    job.contacts?.length ? job.contacts.map((c: any) => ({ ...c })) : [{ ...BLANK_CONTACT, is_primary: true }]
  );

  // Profile + schedule state
  const { data: profilesData = [] } = useQuery({ queryKey: ["profiles"], queryFn: getProfiles });
  const activeProfiles = (profilesData as any[]).filter((p: any) => p.is_active !== false);
  const [selectedProfileId, setSelectedProfileId] = useState<string>(job.matched_profile_id || "");
  const [scheduleIST, setScheduleIST] = useState<string>(job.scheduled_at ? utcToISTInput(job.scheduled_at) : "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [scheduleSaved, setScheduleSaved] = useState(false);

  const handleSaveProfile = async () => {
    if (!selectedProfileId) return;
    setSavingProfile(true);
    try {
      await assignProfileToJob(job.id, selectedProfileId);
      // Refresh after a short delay so the auto-computed schedule from apply_job_task appears
      setTimeout(() => qc.invalidateQueries({ queryKey: ["jobs"] }), 3000);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 3000);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to assign profile");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleSaveSchedule = async () => {
    if (!scheduleIST) return;
    setSavingSchedule(true);
    try {
      const istDate = new Date(scheduleIST);
      const utcDate = new Date(istDate.getTime() - 5.5 * 60 * 60 * 1000);
      await apiRescheduleJob(job.id, utcDate.toISOString());
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setScheduleSaved(true);
      setTimeout(() => setScheduleSaved(false), 2000);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to set schedule");
    } finally {
      setSavingSchedule(false);
    }
  };

  const setF = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));
  const setC = (i: number, k: string, v: any) => setContacts(prev => prev.map((c, idx) => idx === i ? { ...c, [k]: v } : c));
  const addContact = () => setContacts(prev => [...prev, { ...BLANK_CONTACT }]);
  const removeContact = (i: number) => setContacts(prev => prev.filter((_, idx) => idx !== i));
  const setPrimary = (i: number) => setContacts(prev => prev.map((c, idx) => ({ ...c, is_primary: idx === i })));

  const field = (key: string, label: string, span = 1, textarea = false) => (
    <div className={span === 2 ? "col-span-2" : ""} key={key}>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {textarea
        ? <textarea value={(form as any)[key]} onChange={e => setF(key, e.target.value)} rows={3}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
        : <input value={(form as any)[key]} onChange={e => setF(key, e.target.value)}
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-8" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-0">
          <div>
            <h2 className="font-semibold text-gray-900 text-base">{job.title}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{job.company_name || "—"} · {job.location || "—"}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100 mt-0.5"><X size={16} /></button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-6 mt-4 border-b border-gray-100">
          {(["details", "activity"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors capitalize ${
                tab === t
                  ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                  : "text-gray-500 hover:text-gray-700"
              }`}>
              {t === "details" ? <><Settings size={12} className="inline mr-1.5 mb-0.5" />Details</> : <><Activity size={12} className="inline mr-1.5 mb-0.5" />Activity</>}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="px-6 py-5 max-h-[65vh] overflow-y-auto">
          {tab === "activity" ? (
            <JobActivityTab jobId={job.id} />
          ) : (
            <div className="space-y-6">
              {/* Job Details */}
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Job Details</p>
                <div className="grid grid-cols-2 gap-3">
                  {field("title", "Role / Title", 2)}
                  {field("company_name", "Company Name")}
                  {field("company_website", "Company Website")}
                  {field("industry", "Industry")}
                  {field("company_linkedin_url", "Company LinkedIn URL")}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Team Size</label>
                    <select value={form.company_size} onChange={e => setF("company_size", e.target.value)}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                      <option value="">— Unknown —</option>
                      {["1-10","11-50","51-200","201-500","501-1,000","1,001-5,000","5,001-10,000","10,000+"].map(r => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>
                  {field("location", "Location")}
                  {field("country", "Country")}
                  {field("timezone", "Timezone")}
                  {field("job_url", "Job URL (listing page)", 2)}
                  {field("apply_url", "Apply URL", 2)}
                  {field("job_description", "Job Description", 2, true)}
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Status</label>
                    <select value={form.status} onChange={e => setF("status", e.target.value)}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                      {STATUSES.map(s => <option key={s} value={s}>{STATUS_CONFIG[s]?.label || s}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              {/* Profile & Schedule */}
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Profile &amp; Schedule</p>
                <div className="grid grid-cols-2 gap-4">
                  {/* Assign Profile */}
                  <div className="border border-gray-100 rounded-xl p-3 bg-gray-50/50">
                    <label className="block text-xs font-medium text-gray-500 mb-2">Assigned Profile</label>
                    <select
                      value={selectedProfileId}
                      onChange={e => setSelectedProfileId(e.target.value)}
                      className="w-full border border-gray-200 rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white mb-2">
                      <option value="">— Select profile —</option>
                      {activeProfiles.map((p: any) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={handleSaveProfile}
                      disabled={!selectedProfileId || savingProfile}
                      className="flex items-center gap-1.5 text-xs font-semibold bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors">
                      {savingProfile ? <Loader2 size={11} className="animate-spin" /> : profileSaved ? <Check size={11} /> : null}
                      {profileSaved ? "Saved!" : "Save Profile"}
                    </button>
                  </div>

                  {/* Set Schedule */}
                  <div className="border border-gray-100 rounded-xl p-3 bg-gray-50/50">
                    <label className="block text-xs font-medium text-gray-500 mb-2">Send Schedule (IST)</label>
                    <input
                      type="datetime-local"
                      value={scheduleIST}
                      onChange={e => setScheduleIST(e.target.value)}
                      className="w-full border border-gray-200 rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 bg-white mb-2"
                    />
                    <button
                      onClick={handleSaveSchedule}
                      disabled={!scheduleIST || savingSchedule}
                      className="flex items-center gap-1.5 text-xs font-semibold bg-cyan-600 text-white px-3 py-1.5 rounded-lg hover:bg-cyan-700 disabled:opacity-40 transition-colors">
                      {savingSchedule ? <Loader2 size={11} className="animate-spin" /> : scheduleSaved ? <Check size={11} /> : <AlarmClock size={11} />}
                      {scheduleSaved ? "Saved!" : "Save Schedule"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Contacts */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Contacts / Hiring People</p>
                  <button onClick={addContact}
                    className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors">
                    <Plus size={12} /> Add Contact
                  </button>
                </div>
                <div className="space-y-4">
                  {contacts.map((c, i) => (
                    <div key={i} className="border border-gray-100 rounded-xl p-4 bg-gray-50/50 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-gray-500">Contact {i + 1}</span>
                          {c.is_primary
                            ? <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Primary</span>
                            : <button onClick={() => setPrimary(i)} className="text-[10px] text-gray-400 hover:text-blue-600 underline">Set primary</button>}
                        </div>
                        {contacts.length > 1 && (
                          <button onClick={() => removeContact(i)} className="text-gray-300 hover:text-red-500 transition-colors">
                            <X size={14} />
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {[["name","Full Name"],["title","Job Title"]].map(([k,l]) => (
                          <div key={k}>
                            <label className="block text-[10px] font-medium text-gray-400 mb-1">{l}</label>
                            <input value={c[k] ?? ''} onChange={e => setC(i, k, e.target.value)}
                              className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white" />
                          </div>
                        ))}
                        {[["email","Email"],["phone","Phone"]].map(([k,l]) => (
                          <div key={k}>
                            <label className="block text-[10px] font-medium text-gray-400 mb-1">{l}</label>
                            <input value={c[k] ?? ''} onChange={e => setC(i, k, e.target.value)}
                              className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white" />
                          </div>
                        ))}
                        <div className="col-span-2">
                          <label className="block text-[10px] font-medium text-gray-400 mb-1">LinkedIn URL</label>
                          <input value={c.linkedin_url} onChange={e => setC(i, "linkedin_url", e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white" />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer — only show Save on details tab */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose} className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">
            {tab === "activity" ? "Close" : "Cancel"}
          </button>
          {tab === "details" && (
            <button onClick={() => onSave({ ...form, contacts })}
              className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700 flex items-center gap-2 shadow-sm font-medium">
              <Check size={13} /> Save Changes
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const COLS = [
  "", // checkbox
  "Company", "Role / Title", "Location", "Industry", "Team Size", "Website", "Platform", "Posted At", "Scraped At",
  "Hiring Person", "Email", "Phone", "LinkedIn",
  "Status", "Auto Apply", "Scheduled Send", "Date Applied", "Follow-up Dates", "Applied From", "CV", "Skills",
  "Job URL", "Apply URL", "Summary", "Actions"
];

// ── Apply Now Modal ───────────────────────────────────────────────────────────
type ApplyState = "idle" | "running" | "done" | "error";

function ApplyNowModal({ job, onClose }: { job: any; onClose: () => void }) {
  const [state, setState] = useState<ApplyState>("idle");
  const [result, setResult] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const { data: profiles = [] } = useQuery({ queryKey: ["profiles"], queryFn: getProfiles });

  const handleApply = async () => {
    setState("running");
    setErrorMsg("");
    try {
      const res = await applyNow(job.id);
      setResult(res);
      setState("done");
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err.message || "Unknown error");
      setState("error");
    }
  };

  const activeProfiles = (profiles as any[]).filter((p: any) => p.is_active !== false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <h2 className="font-bold text-gray-900 text-lg flex items-center gap-2">
              <Zap size={18} className="text-blue-600" /> Auto Apply
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">{job.title} · {job.company_name || "—"}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg">
            <X size={16} />
          </button>
        </div>

        {/* Steps preview */}
        {state === "idle" && (
          <div className="space-y-3 mb-5">
            <p className="text-sm text-gray-600 font-medium">The system will automatically:</p>
            <div className="space-y-2">
              {[
                { icon: "🎯", text: `Pick the best matching profile (${activeProfiles.length} active)` },
                { icon: "✍️", text: "Generate a personalised email using Claude AI" },
                { icon: "📄", text: "Tailor your CV to match this job's skills" },
                { icon: "📨", text: `Send email to ${job.hiring_email || job.contacts?.[0]?.email || "contact on job"}` },
              ].map((s, i) => (
                <div key={i} className="flex items-center gap-3 bg-gray-50 rounded-xl px-3 py-2.5 text-sm text-gray-700">
                  <span className="text-base">{s.icon}</span>{s.text}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Running */}
        {state === "running" && (
          <div className="py-8 flex flex-col items-center gap-3">
            <Loader2 size={36} className="text-blue-600 animate-spin" />
            <p className="text-sm text-gray-600 font-medium">Generating email & tailoring CV…</p>
            <p className="text-xs text-gray-400">This takes 10–20 seconds</p>
          </div>
        )}

        {/* Success */}
        {state === "done" && result && (
          <div className="space-y-3 mb-5">
            <div className="flex items-center gap-2 text-emerald-700 font-semibold">
              <CheckCircle2 size={20} className="text-emerald-500" /> Email sent successfully!
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-2 text-sm">
              <div className="flex gap-2"><span className="text-gray-500 w-20 flex-shrink-0">Profile:</span><span className="font-medium text-gray-800">{result.profile}</span></div>
              <div className="flex gap-2"><span className="text-gray-500 w-20 flex-shrink-0">Sent to:</span><span className="font-medium text-gray-800">{result.to}</span></div>
              <div className="flex gap-2"><span className="text-gray-500 w-20 flex-shrink-0">Subject:</span><span className="font-medium text-gray-800">{result.subject}</span></div>
              <div className="flex gap-2"><span className="text-gray-500 w-20 flex-shrink-0">CV:</span><span className="font-medium text-gray-800">{result.cv_attached ? "Attached (tailored)" : "Not attached"}</span></div>
            </div>
          </div>
        )}

        {/* Error */}
        {state === "error" && (
          <div className="mb-5 bg-red-50 border border-red-200 rounded-xl p-4 flex gap-3">
            <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-red-700 mb-1">Apply failed</p>
              <p className="text-xs text-red-600">{errorMsg}</p>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          {state === "idle" && (
            <button onClick={handleApply}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white py-2.5 rounded-xl font-semibold text-sm hover:bg-blue-700 shadow-sm">
              <Zap size={14} /> Apply Now
            </button>
          )}
          {state === "error" && (
            <button onClick={handleApply}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white py-2.5 rounded-xl font-semibold text-sm hover:bg-blue-700">
              <RefreshCw size={14} /> Retry
            </button>
          )}
          <button onClick={onClose}
            className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
            {state === "done" ? "Close" : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [scrapedTodayFilter, setScrapedTodayFilter] = useState(false);
  const [manualFilter, setManualFilter] = useState(false);
  const [editJob, setEditJob] = useState<any>(null);
  const [applyJob, setApplyJob] = useState<any>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [rescheduleJob, setRescheduleJob] = useState<any>(null);
  const [rescheduleVal, setRescheduleVal] = useState("");
  const [rescheduling, setRescheduling] = useState(false);

  // Assign profile modal
  const [assignProfileJob, setAssignProfileJob] = useState<any>(null);
  const [assigningProfile, setAssigningProfile] = useState(false);

  // Manual schedule modal (for jobs without an existing application)
  const [scheduleJob, setScheduleJob] = useState<any>(null);
  const [scheduleVal, setScheduleVal] = useState("");
  const [scheduling, setScheduling] = useState(false);

  // Follow-up reschedule
  const [rescheduleFollowup, setRescheduleFollowup] = useState<{ jobId: string; fu: any } | null>(null);
  const [rescheduleFollowupVal, setRescheduleFollowupVal] = useState("");
  const [reschedulingFollowup, setReschedulingFollowup] = useState(false);

  // Per-job CV upload state
  const cvFileRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [cvUploading, setCvUploading] = useState<Record<string, boolean>>({});
  const [cvUploadError, setCvUploadError] = useState<Record<string, string>>({});

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [customSize, setCustomSize] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  // Multi-select
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data: jobsResponse, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => getJobs({ page: 1, page_size: 2000 }),
  });

  const { data: profilesData = [] } = useQuery({ queryKey: ["profiles"], queryFn: getProfiles });
  const activeProfiles = (profilesData as any[]).filter((p: any) => p.is_active !== false);

  const allJobs = (jobsResponse?.jobs ?? (Array.isArray(jobsResponse) ? jobsResponse : [])) as any[];

  // Client-side filtering + pagination
  const [filterCountry, setFilterCountry] = useState("");
  const [filterPlatform, setFilterPlatform] = useState("");
  const [filterScheduleDate, setFilterScheduleDate] = useState("");
  const [filterAppliedDate, setFilterAppliedDate] = useState("");
  const [filterScrapedDate, setFilterScrapedDate] = useState("");
  const [filterActivityDate, setFilterActivityDate] = useState("");
  const [filterTeamSize, setFilterTeamSize] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const todayStr = new Date().toISOString().slice(0, 10);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const result = allJobs.filter((j: any) => {
      if (statusFilter && j.status !== statusFilter) return false;
      if (scrapedTodayFilter) {
        const raw = j.scraped_at || j.created_at;
        if (!raw || new Date(raw).toISOString().slice(0, 10) !== todayStr) return false;
      }
      if (filterCountry && j.country !== filterCountry) return false;
      if (filterPlatform && j.platform_name !== filterPlatform) return false;
      if (filterScheduleDate && j.scheduled_at) {
        const d = toIST(j.scheduled_at);
        if (!d) return false;
        const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
        if (dateStr !== filterScheduleDate) return false;
      } else if (filterScheduleDate && !j.scheduled_at) return false;
      if (filterAppliedDate && j.date_applied) {
        const d = new Date(j.date_applied);
        const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
        if (dateStr !== filterAppliedDate) return false;
      } else if (filterAppliedDate && !j.date_applied) return false;
      if (filterScrapedDate) {
        const raw = j.scraped_at || j.created_at;
        if (!raw) return false;
        const d = new Date(raw);
        const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
        if (dateStr !== filterScrapedDate) return false;
      }
      if (filterActivityDate) {
        const toDateStr = (raw: string | null | undefined) => {
          if (!raw) return null;
          const d = new Date(raw);
          return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
        };
        const activityDates = [
          toDateStr(j.scraped_at || j.created_at),
          toDateStr(j.date_applied),
          toDateStr(j.contact_found_at),
          ...((j.followup_dates || []).map((fu: any) => toDateStr(fu.sent_at))),
        ].filter(Boolean);
        if (!activityDates.includes(filterActivityDate)) return false;
      }
      if (filterTeamSize) {
        const sizeRangeMax: Record<string, number> = {
          "1-10": 10, "11-50": 50, "51-200": 200, "201-500": 500,
          "501-1,000": 1000, "1,001-5,000": 5000, "5,001-10,000": 10000, "10,000+": 999999,
        };
        const maxAllowed = parseInt(filterTeamSize);
        const cs = (j.company_size || "").trim();
        if (!cs) return false; // no size data — hide if filtering
        const upper = sizeRangeMax[cs];
        if (upper === undefined) return false;
        if (upper > maxAllowed) return false;
      }
      if (q) {
        const haystack = [
          j.title,
          j.company_name,
          j.hiring_person_name,
          j.hiring_person_email,
          j.contact_email,
          j.applied_from_email,
          j.sender_email,
          j.country,
          j.platform_name,
          j.job_url,
          j.notes,
          j.matched_profile?.name,
          ...(j.contacts || []).map((c: any) => `${c.name || ""} ${c.email || ""} ${c.title || ""}`),
          ...(j.hiring_contacts || []).map((c: any) => `${c.name || ""} ${c.email || ""}`),
        ].filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
    result.sort((a: any, b: any) => {
      const aTime = new Date(a.scraped_at || a.created_at || 0).getTime();
      const bTime = new Date(b.scraped_at || b.created_at || 0).getTime();
      return bTime - aTime;
    });
    return result;
  }, [allJobs, statusFilter, filterCountry, filterPlatform, filterScheduleDate, filterAppliedDate, filterScrapedDate, filterActivityDate, filterTeamSize, searchQuery, scrapedTodayFilter, todayStr]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

  // Reset page when filter or pageSize changes
  const handleStatusFilter = (s: string) => { setStatusFilter(s); setPage(1); setSelected(new Set()); };
  const handlePageSize = (n: number) => { setPageSize(n); setPage(1); setSelected(new Set()); setShowCustomInput(false); };

  // Select logic
  const pageIds = paginated.map((j: any) => j.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selected.has(id));
  const someSelected = selected.size > 0;

  const toggleAll = () => {
    if (allPageSelected) {
      const next = new Set(selected);
      pageIds.forEach(id => next.delete(id));
      setSelected(next);
    } else {
      const next = new Set(selected);
      pageIds.forEach(id => next.add(id));
      setSelected(next);
    }
  };
  const toggleOne = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadJobs(file),
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ["jobs"] }); alert(`Uploaded: ${res.created} new, ${res.updated} existing updated`); },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateJob(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["jobs"] }); setEditJob(null); },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => bulkDeleteJobs(ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["jobs"] }); setSelected(new Set()); },
  });
  const applyMutation = useMutation({
    mutationFn: (id: string) => triggerApply(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const createMutation = useMutation({
    mutationFn: (data: any) => createJob(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setShowCreateModal(false);
      // Backend already triggers match_job_task → apply_job_task automatically
    },
  });
  const toggleAutoApply = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateJob(id, { auto_apply_enabled: enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const handleReschedule = async () => {
    if (!rescheduleJob || !rescheduleVal) return;
    setRescheduling(true);
    try {
      // rescheduleVal is datetime-local in IST; convert to UTC ISO
      const istDate = new Date(rescheduleVal);
      // subtract 5:30 to get UTC
      const utcDate = new Date(istDate.getTime() - 5.5 * 60 * 60 * 1000);
      await apiRescheduleJob(rescheduleJob.id, utcDate.toISOString());
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setRescheduleJob(null);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to reschedule");
    } finally {
      setRescheduling(false);
    }
  };

  const handleRescheduleFollowup = async () => {
    if (!rescheduleFollowup || !rescheduleFollowupVal) return;
    setReschedulingFollowup(true);
    try {
      const istDate = new Date(rescheduleFollowupVal);
      const utcDate = new Date(istDate.getTime() - 5.5 * 60 * 60 * 1000);
      await apiRescheduleFollowup(rescheduleFollowup.jobId, rescheduleFollowup.fu.id, utcDate.toISOString());
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setRescheduleFollowup(null);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to reschedule follow-up");
    } finally {
      setReschedulingFollowup(false);
    }
  };

  const handleAssignProfile = async (profileId: string) => {
    if (!assignProfileJob) return;
    setAssigningProfile(true);
    try {
      await assignProfileToJob(assignProfileJob.id, profileId);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setAssignProfileJob(null);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to assign profile");
    } finally {
      setAssigningProfile(false);
    }
  };

  const handleManualSchedule = async () => {
    if (!scheduleJob || !scheduleVal) return;
    setScheduling(true);
    try {
      const istDate = new Date(scheduleVal);
      const utcDate = new Date(istDate.getTime() - 5.5 * 60 * 60 * 1000);
      await apiRescheduleJob(scheduleJob.id, utcDate.toISOString());
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setScheduleJob(null);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to set schedule");
    } finally {
      setScheduling(false);
    }
  };

  const handleExport = async () => {
    const ids = filtered.map((j: any) => j.id);
    const blob = await exportJobs(ids);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "jobs_export.xlsx"; a.click();
  };

  const counts = STATUSES.reduce((acc, s) => {
    acc[s] = allJobs.filter((j: any) => j.status === s).length;
    return acc;
  }, {} as Record<string, number>);

  // Stats derived from all jobs
  const stats = {
    total: allJobs.length,
    sent: allJobs.filter((j: any) => j.date_applied).length,
    scheduled: allJobs.filter((j: any) => j.scheduled_at && !j.date_applied).length,
    opened: allJobs.filter((j: any) => j.application_status === "opened").length,
    replied: allJobs.filter((j: any) => j.status === "replied").length,
    scrapedToday: allJobs.filter((j: any) => {
      const raw = j.scraped_at || j.created_at;
      return raw && new Date(raw).toISOString().slice(0, 10) === todayStr;
    }).length,
  };

  // Unique options for dropdowns
  const countryOptions = Array.from(new Set(allJobs.map((j: any) => j.country).filter(Boolean))).sort() as string[];
  const platformOptions = Array.from(new Set(allJobs.map((j: any) => j.platform_name).filter(Boolean))).sort() as string[];
  const hasActiveFilters = !!(filterCountry || filterPlatform || filterScheduleDate || filterAppliedDate || filterScrapedDate || filterActivityDate || filterTeamSize || statusFilter || searchQuery || scrapedTodayFilter || manualFilter);

  if (isLoading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-40" />
      <div className="h-96 bg-gray-100 rounded-2xl" />
    </div>
  );

  return (
    <div className="space-y-5">
      {editJob && (
        <EditModal job={editJob} onClose={() => setEditJob(null)}
          onSave={(form) => updateMutation.mutate({ id: editJob.id, data: form })} />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
          <p className="text-gray-500 text-sm mt-1">{filtered.length} shown · {allJobs.length.toLocaleString()} total jobs</p>
        </div>
        <div className="flex gap-2 items-center">
          <button onClick={() => setShowFilters(v => !v)}
            className={`flex items-center gap-2 border px-3 py-2 rounded-xl text-sm shadow-sm transition-colors ${hasActiveFilters ? "border-blue-400 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-700 bg-white hover:bg-gray-50"}`}>
            <Settings size={14} /> Filters {hasActiveFilters && <span className="bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">ON</span>}
          </button>
          <button onClick={handleExport} className="flex items-center gap-2 border border-gray-200 text-gray-700 px-3 py-2 rounded-xl text-sm bg-white shadow-sm hover:bg-gray-50">
            <Download size={14} /> Export
          </button>
          <button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm">
            <Plus size={14} /> Add Job
          </button>
          <button onClick={() => fileRef.current?.click()} className="flex items-center gap-2 border border-gray-200 text-gray-700 px-4 py-2 rounded-xl text-sm bg-white hover:bg-gray-50 shadow-sm">
            <Upload size={14} /> Upload CSV
          </button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden"
            onChange={(e) => { if (e.target.files?.[0]) uploadMutation.mutate(e.target.files[0]); }} />
        </div>
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          type="text"
          placeholder="Search by company, email, hiring person, job title..."
          value={searchQuery}
          onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
          className="w-full pl-9 pr-9 py-2.5 border border-gray-200 rounded-xl text-sm bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {searchQuery && (
          <button onClick={() => { setSearchQuery(""); setPage(1); }} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
            <X size={14} />
          </button>
        )}
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { label: "Total Jobs",      value: stats.total,        icon: Briefcase,  color: "text-gray-700",    bg: "bg-gray-50",    border: "border-gray-200",   onClick: () => { setStatusFilter(""); setManualFilter(false); setFilterCountry(""); setFilterPlatform(""); setFilterScheduleDate(""); setFilterAppliedDate(""); setFilterScrapedDate(""); setFilterActivityDate(""); setFilterTeamSize(""); setSearchQuery(""); setScrapedTodayFilter(false); setPage(1); } },
          { label: "Scraped Today",   value: stats.scrapedToday, icon: RefreshCw,  color: "text-orange-700",  bg: "bg-orange-50",  border: "border-orange-200", onClick: () => { setFilterScrapedDate(todayStr); setPage(1); } },
          { label: "Emails Sent",     value: stats.sent,         icon: Send,       color: "text-blue-700",    bg: "bg-blue-50",    border: "border-blue-200",   onClick: undefined },
          { label: "Scheduled",       value: stats.scheduled,    icon: AlarmClock, color: "text-cyan-700",    bg: "bg-cyan-50",    border: "border-cyan-200",   onClick: undefined },
          { label: "Opened",          value: stats.opened,       icon: Eye,        color: "text-violet-700",  bg: "bg-violet-50",  border: "border-violet-200", onClick: undefined },
          { label: "Replied",         value: stats.replied,      icon: Reply,      color: "text-emerald-700", bg: "bg-emerald-50", border: "border-emerald-200",onClick: undefined },
        ].map(({ label, value, icon: Icon, color, bg, border, onClick }) => (
          <div key={label} onClick={onClick}
            className={`${bg} border ${border} rounded-2xl px-4 py-3.5 flex items-center gap-3 ${onClick ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}>
            <div className={`w-9 h-9 rounded-xl ${bg} border ${border} flex items-center justify-center flex-shrink-0`}>
              <Icon size={16} className={color} />
            </div>
            <div>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Advanced filters panel */}
      {showFilters && (
        <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Filter Jobs</p>
            {hasActiveFilters && (
              <button onClick={() => { setStatusFilter(""); setFilterCountry(""); setFilterPlatform(""); setFilterScheduleDate(""); setFilterAppliedDate(""); setFilterScrapedDate(""); setFilterActivityDate(""); setFilterTeamSize(""); setSearchQuery(""); setScrapedTodayFilter(false); setPage(1); }}
                className="text-xs text-red-500 hover:text-red-700 font-medium flex items-center gap-1">
                <X size={11} /> Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            {/* Status */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Status</label>
              <select value={statusFilter} onChange={e => { handleStatusFilter(e.target.value); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">All</option>
                {STATUSES.map(s => <option key={s} value={s}>{STATUS_CONFIG[s]?.label || s}</option>)}
              </select>
            </div>
            {/* Country */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Country</label>
              <select value={filterCountry} onChange={e => { setFilterCountry(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">All Countries</option>
                {countryOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            {/* Platform */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Platform</label>
              <select value={filterPlatform} onChange={e => { setFilterPlatform(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">All Platforms</option>
                {platformOptions.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            {/* Schedule Date */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Schedule Date (IST)</label>
              <input type="date" value={filterScheduleDate} onChange={e => { setFilterScheduleDate(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            {/* Date Applied */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Date Applied</label>
              <input type="date" value={filterAppliedDate} onChange={e => { setFilterAppliedDate(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            {/* Scraped Date */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Scraped Date</label>
              <input type="date" value={filterScrapedDate} onChange={e => { setFilterScrapedDate(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            {/* Activity Date */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Activity Date</label>
              <input type="date" value={filterActivityDate} onChange={e => { setFilterActivityDate(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            {/* Team Size */}
            <div>
              <label className="block text-[11px] font-medium text-gray-400 mb-1">Max Team Size</label>
              <select value={filterTeamSize} onChange={e => { setFilterTeamSize(e.target.value); setPage(1); }}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">All Sizes</option>
                <option value="10">1–10 employees</option>
                <option value="50">Up to 50 employees</option>
                <option value="200">Up to 200 employees</option>
                <option value="500">Up to 500 employees</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Status filter pills */}
      <div className="flex flex-wrap gap-2">
        {STATUSES.filter(s => counts[s] > 0).map(s => {
          const cfg = STATUS_CONFIG[s];
          return (
            <button key={s} onClick={() => handleStatusFilter(statusFilter === s ? "" : s)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
                statusFilter === s ? "border-blue-500 bg-blue-50 text-blue-700" : `${cfg.cls} hover:opacity-80`
              }`}>
              {cfg.label} <span className="ml-1 font-bold">{counts[s]}</span>
            </button>
          );
        })}
        {stats.scrapedToday > 0 && (
          <button onClick={() => { setScrapedTodayFilter(p => !p); setPage(1); }}
            className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
              scrapedTodayFilter
                ? "border-blue-500 bg-blue-50 text-blue-700"
                : "bg-violet-100 text-violet-700 border-violet-200 hover:opacity-80"
            }`}>
            Scraped Today <span className="ml-1 font-bold">{stats.scrapedToday}</span>
          </button>
        )}
        <button onClick={() => { setManualFilter(p => !p); setPage(1); }}
          className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
            manualFilter
              ? "border-blue-500 bg-blue-50 text-blue-700"
              : "bg-teal-50 text-teal-700 border-teal-200 hover:opacity-80"
          }`}>
          Manual {!manualFilter && <span className="ml-1 font-bold">{allJobs.filter((j: any) => j.uploaded_manually).length}</span>}
        </button>
      </div>

      {/* Activity date summary banner */}
      {filterActivityDate && (() => {
        const toDs = (raw: string | null | undefined) => {
          if (!raw) return null;
          const d = new Date(raw);
          return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
        };
        let scraped = 0, applied = 0, followups = 0, contacts = 0;
        allJobs.forEach((j: any) => {
          if (toDs(j.scraped_at || j.created_at) === filterActivityDate) scraped++;
          if (toDs(j.date_applied) === filterActivityDate) applied++;
          if (toDs(j.contact_found_at) === filterActivityDate) contacts++;
          (j.followup_dates || []).forEach((fu: any) => { if (toDs(fu.sent_at) === filterActivityDate) followups++; });
        });
        return (
          <div className="flex flex-wrap items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-2.5 text-sm">
            <span className="font-semibold text-indigo-700">Activity on {filterActivityDate}:</span>
            <span className="flex items-center gap-1 text-orange-700 bg-orange-100 px-2 py-0.5 rounded-full text-xs font-medium">Scraped: {scraped}</span>
            <span className="flex items-center gap-1 text-green-700 bg-green-100 px-2 py-0.5 rounded-full text-xs font-medium">Applied: {applied}</span>
            <span className="flex items-center gap-1 text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full text-xs font-medium">Follow-ups: {followups}</span>
            <span className="flex items-center gap-1 text-purple-700 bg-purple-100 px-2 py-0.5 rounded-full text-xs font-medium">Contacts Found: {contacts}</span>
            <button onClick={() => { setFilterActivityDate(""); setPage(1); }} className="ml-auto text-xs text-indigo-500 hover:text-indigo-700 font-medium flex items-center gap-1"><X size={11} /> Clear</button>
          </div>
        );
      })()}

      {/* Bulk action bar */}
      {someSelected && (
        <div className="flex items-center gap-3 bg-blue-50 border border-blue-200 rounded-xl px-4 py-2.5">
          <span className="text-sm font-semibold text-blue-700">{selected.size} selected</span>
          <button
            onClick={() => { if (confirm(`Delete ${selected.size} jobs? This cannot be undone.`)) bulkDeleteMutation.mutate([...selected]); }}
            disabled={bulkDeleteMutation.isPending}
            className="flex items-center gap-1.5 bg-red-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg hover:bg-red-600 disabled:opacity-50">
            <Trash2 size={12} /> Delete Selected
          </button>
          <button onClick={() => setSelected(new Set())}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium">Clear selection</button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-x-auto">
        <table style={{ minWidth: "1950px", width: "100%", borderCollapse: "collapse" }} className="text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/70">
              {/* Checkbox col — sticky */}
              <th className="px-4 py-3 w-10 sticky left-0 z-20 bg-gray-50">
                <input type="checkbox" checked={allPageSelected} onChange={toggleAll}
                  className="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer accent-blue-600" />
              </th>
              {/* Company — sticky */}
              <th className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap sticky left-10 z-20 bg-gray-50 shadow-[2px_0_4px_-1px_rgba(0,0,0,0.06)]">
                Company
              </th>
              {/* Role / Title — sticky */}
              <th className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap sticky left-[210px] z-20 bg-gray-50 shadow-[2px_0_4px_-1px_rgba(0,0,0,0.06)]">
                Role / Title
              </th>
              {COLS.slice(3).map(h => (
                <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginated.map((job: any, idx: number) => {
              const cfg = STATUS_CONFIG[job.status] || { label: job.status, cls: "bg-gray-100 text-gray-600 border-gray-200" };
              const followups: any[] = job.followup_dates || [];
              const isChecked = selected.has(job.id);

              return (
                <tr key={job.id}
                  className={`border-b border-gray-50 transition-colors hover:bg-blue-50/30 ${
                    isChecked ? "bg-blue-50/50" : job.is_pinned ? "bg-amber-50/30" : idx % 2 === 0 ? "bg-white" : "bg-gray-50/20"
                  }`}>

                  {/* Checkbox — sticky */}
                  <td className={`px-4 py-3 sticky left-0 z-10 ${isChecked ? "bg-blue-100" : job.is_pinned ? "bg-amber-50" : idx % 2 === 0 ? "bg-white" : "bg-gray-50"}`}>
                    <input type="checkbox" checked={isChecked} onChange={() => toggleOne(job.id)}
                      className="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer accent-blue-600" />
                  </td>

                  {/* 1. Company — sticky */}
                  <td className={`px-4 py-3 sticky left-10 z-10 ${isChecked ? "bg-blue-100" : job.is_pinned ? "bg-amber-50" : idx % 2 === 0 ? "bg-white" : "bg-gray-50"}`}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-slate-100 to-slate-200 border border-slate-200 flex items-center justify-center text-[11px] font-bold text-slate-500 flex-shrink-0">
                        {(job.company_name || "?")[0].toUpperCase()}
                      </div>
                      <span className="font-semibold text-gray-900 whitespace-nowrap text-[13px]">{job.company_name || <Dash />}</span>
                    </div>
                  </td>

                  {/* 2. Role / Title — sticky */}
                  <td className={`px-4 py-3 max-w-[180px] sticky left-[210px] z-10 shadow-[2px_0_4px_-1px_rgba(0,0,0,0.08)] ${isChecked ? "bg-blue-100" : job.is_pinned ? "bg-amber-50" : idx % 2 === 0 ? "bg-white" : "bg-gray-50"}`}>
                    <span className="text-gray-800 font-medium text-[13px] block truncate" title={job.title}>{job.title}</span>
                  </td>

                  {/* 3. Location */}
                  <td className="px-4 py-3">
                    {formatLocation(job.country, job.location)
                      ? <div className="flex items-center gap-1 text-gray-500 text-xs whitespace-nowrap">
                          <MapPin size={11} className="flex-shrink-0 text-gray-400" />
                          {formatLocation(job.country, job.location)}
                        </div>
                      : <Dash />}
                  </td>

                  {/* 4. Industry */}
                  <td className="px-4 py-3">
                    {job.industry
                      ? <span className="text-xs text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full whitespace-nowrap">{job.industry}</span>
                      : <span className="text-gray-300 text-xs italic">—</span>}
                  </td>

                  {/* 5. Team Size */}
                  <td className="px-4 py-3">
                    {job.company_size
                      ? <span className="text-xs text-gray-600 whitespace-nowrap">{job.company_size.toLocaleString()} emp.</span>
                      : <span className="text-gray-300 text-xs italic">—</span>}
                  </td>

                  {/* 6. Website */}
                  <td className="px-4 py-3">
                    {job.company_website
                      ? <a href={job.company_website.startsWith("http") ? job.company_website : `https://${job.company_website}`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline whitespace-nowrap">
                          {job.company_website.replace(/^https?:\/\//, "").split("/")[0]}
                        </a>
                      : <span className="text-gray-300 text-xs italic">—</span>}
                  </td>

                  {/* Platform */}
                  <td className="px-4 py-3">
                    <span className="text-[11px] bg-slate-100 text-slate-600 border border-slate-200 px-2 py-1 rounded-full font-medium whitespace-nowrap">
                      {job.platform_name || "Manual"}
                    </span>
                  </td>

                  {/* 5. Posted At */}
                  <td className="px-4 py-3">
                    {job.posted_at
                      ? <span className="text-gray-700 text-xs whitespace-nowrap">{new Date(job.posted_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span>
                      : <span className="text-gray-300 italic text-xs">—</span>}
                  </td>

                  {/* 5b. Scraped At */}
                  <td className="px-4 py-3">
                    {(job.scraped_at || job.created_at)
                      ? <span className="text-gray-700 text-xs whitespace-nowrap">{new Date(job.scraped_at || job.created_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span>
                      : <span className="text-gray-300 italic text-xs">—</span>}
                  </td>

                  {/* 6. Hiring Person */}
                  <td className="px-4 py-3">
                    {job.hiring_person
                      ? <span className="text-gray-800 text-[13px] font-medium whitespace-nowrap">{job.hiring_person}</span>
                      : <span className="text-gray-300 text-xs italic">Not found</span>}
                  </td>

                  {/* 6. Email */}
                  <td className="px-4 py-3">
                    {job.hiring_email
                      ? <a href={`mailto:${job.hiring_email}`} className="text-blue-600 hover:underline text-xs flex items-center gap-1 whitespace-nowrap">
                          <Mail size={10} />{job.hiring_email}
                        </a>
                      : <Dash />}
                  </td>

                  {/* 7. Phone */}
                  <td className="px-4 py-3">
                    {job.hiring_phone
                      ? <a href={`tel:${job.hiring_phone}`} className="text-gray-600 hover:text-blue-600 text-xs flex items-center gap-1 whitespace-nowrap">
                          <Phone size={10} />{job.hiring_phone}
                        </a>
                      : <Dash />}
                  </td>

                  {/* 8. LinkedIn */}
                  <td className="px-4 py-3">
                    {job.hiring_linkedin
                      ? <a href={job.hiring_linkedin} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 text-[11px] font-medium text-blue-600 bg-blue-50 border border-blue-100 px-2 py-1 rounded-lg whitespace-nowrap">
                          <ExternalLink size={10} /> LinkedIn
                        </a>
                      : <Dash />}
                  </td>

                  {/* 9. Status */}
                  <td className="px-4 py-3">
                    <span className={`inline-flex text-[11px] font-semibold px-2.5 py-1 rounded-full border whitespace-nowrap ${cfg.cls}`}>
                      {cfg.label}
                    </span>
                  </td>

                  {/* 10. Auto Apply Toggle */}
                  <td className="px-4 py-3">
                    {(() => {
                      const enabled = job.auto_apply_enabled !== false;
                      return (
                        <button
                          onClick={() => toggleAutoApply.mutate({ id: job.id, enabled: !enabled })}
                          title={enabled ? "Auto Apply ON — click to disable" : "Auto Apply OFF — click to enable"}
                          className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 transition-colors duration-200 focus:outline-none ${
                            enabled ? "bg-blue-600 border-blue-600" : "bg-gray-200 border-gray-200"
                          }`}>
                          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                            enabled ? "translate-x-4" : "translate-x-0"
                          }`} />
                        </button>
                      );
                    })()}
                  </td>

                  {/* Scheduled Send */}
                  <td className="px-4 py-3 min-w-[150px]">
                    {job.scheduled_at ? (
                      <div className="flex flex-col gap-0.5">
                        {(() => {
                          const isPast = new Date(job.scheduled_at) < new Date();
                          return (
                            <div className="flex items-center gap-1.5">
                              <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${isPast ? "text-orange-700 bg-orange-50 border border-orange-200" : "text-cyan-700 bg-cyan-50 border border-cyan-200"}`}>
                                <AlarmClock size={9} /> {isPast ? "Sending soon" : "Scheduled"}
                              </span>
                              <button
                                onClick={() => { setRescheduleJob(job); setRescheduleVal(utcToISTInput(job.scheduled_at)); }}
                                title="Edit schedule"
                                className="text-gray-400 hover:text-blue-600 transition-colors"
                              >
                                <Pencil size={11} />
                              </button>
                            </div>
                          );
                        })()}
                        <span className="text-[11px] text-gray-600 font-medium whitespace-nowrap">
                          {fmtScheduleIST(job.scheduled_at)}
                        </span>
                      </div>
                    ) : job.date_applied ? (
                      <span className="text-[11px] text-gray-400 italic">Already sent</span>
                    ) : (
                      /* No schedule yet — show Set Schedule button for all roles */
                      <button
                        onClick={() => { setScheduleJob(job); setScheduleVal(""); }}
                        title="Set send schedule manually"
                        className="flex items-center gap-1 text-[10px] text-cyan-700 hover:text-cyan-900 hover:bg-cyan-50 px-1.5 py-0.5 rounded transition-colors w-fit border border-cyan-200">
                        <AlarmClock size={9} /> Set Schedule
                      </button>
                    )}
                  </td>

                  {/* Date Applied */}
                  <td className="px-4 py-3">
                    {fmt(job.date_applied)
                      ? <span className="text-xs text-gray-600 font-medium whitespace-nowrap">{fmt(job.date_applied)}</span>
                      : <Dash />}
                  </td>

                  {/* 11. Follow-up Dates */}
                  <td className="px-4 py-3">
                    {followups.length > 0
                      ? <div className="flex flex-col gap-1 min-w-[130px]">
                          {followups.map((fu: any) => (
                            <div key={fu.number} className="flex items-center gap-1.5 group/fu">
                              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 ${fu.status === "sent" ? "bg-emerald-100 text-emerald-700" : "bg-orange-100 text-orange-700"}`}>
                                F{fu.number}
                              </span>
                              <span className="text-[11px] text-gray-500 whitespace-nowrap flex-1">
                                {fu.status === "sent"
                                  ? (fmt(fu.sent_at) || "Sent")
                                  : (fmtScheduleIST(fu.scheduled_at) || "Pending")}
                              </span>
                              {fu.status === "pending" && fu.id && (
                                <button
                                  onClick={() => { setRescheduleFollowup({ jobId: job.id, fu }); setRescheduleFollowupVal(utcToISTInput(fu.scheduled_at)); }}
                                  title="Edit follow-up schedule"
                                  className="opacity-0 group-hover/fu:opacity-100 transition-opacity text-gray-400 hover:text-blue-600 flex-shrink-0">
                                  <Pencil size={10} />
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      : <Dash />}
                  </td>

                  {/* 12. Applied From / Matched Profile */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1">
                      {job.applied_from_email
                        ? <span className="text-[11px] text-gray-600 whitespace-nowrap">{job.applied_from_email}</span>
                        : job.matched_profile?.name
                          ? <span className="text-[11px] text-gray-600 font-medium whitespace-nowrap">{job.matched_profile.name}</span>
                          : null}
                      {/* Profile assign button — always visible to all roles */}
                      {!job.date_applied && (
                        <button
                          onClick={() => setAssignProfileJob(job)}
                          title={job.matched_profile_id ? "Change profile" : "Assign profile"}
                          className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-1.5 py-0.5 rounded transition-colors w-fit border border-blue-200">
                          <Pencil size={9} /> {job.matched_profile_id ? "Change" : "Set Profile"}
                        </button>
                      )}
                    </div>
                  </td>

                  {/* 13. CV */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {job.cv_url
                        ? <a href={job.cv_url} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-lg hover:bg-emerald-100 whitespace-nowrap">
                            <FileText size={10} /> View CV
                          </a>
                        : ["researching","ready","matched","scheduled","pending_approval"].includes(job.status) && job.matched_profile_id
                          ? <span className="text-[11px] text-amber-600 bg-amber-50 border border-amber-200 px-2 py-1 rounded-lg whitespace-nowrap">Will attach</span>
                          : ["applied","sent","followed_up","replied"].includes(job.status)
                            ? <span className="text-[11px] text-gray-400 italic">Not attached</span>
                            : <Dash />}

                      {/* Upload / replace CV button — available for any job with an application */}
                      {["scheduled","pending_approval","ready","applied","sent","followed_up"].includes(job.status) && job.matched_profile_id && (
                        <>
                          <button
                            onClick={() => cvFileRefs.current[job.id]?.click()}
                            disabled={cvUploading[job.id]}
                            className="p-1 rounded text-gray-300 hover:text-blue-500 hover:bg-blue-50 transition-colors disabled:opacity-40"
                            title={job.cv_url ? "Replace CV" : "Upload CV"}>
                            <Upload size={11} />
                          </button>
                          <input type="file" accept=".pdf,.docx,.doc" className="hidden"
                            ref={el => { cvFileRefs.current[job.id] = el; }}
                            onChange={async e => {
                              const file = e.target.files?.[0];
                              if (!file) return;
                              e.target.value = "";
                              setCvUploading(s => ({ ...s, [job.id]: true }));
                              setCvUploadError(s => ({ ...s, [job.id]: "" }));
                              try {
                                await uploadJobCV(job.id, file);
                                qc.invalidateQueries({ queryKey: ["jobs"] });
                              } catch (err: any) {
                                setCvUploadError(s => ({ ...s, [job.id]: err.message || "Upload failed" }));
                              } finally {
                                setCvUploading(s => ({ ...s, [job.id]: false }));
                              }
                            }} />
                          {job.cv_url && (
                            <button
                              onClick={async () => {
                                if (!confirm("Remove CV from this job?")) return;
                                try {
                                  await deleteJobCV(job.id);
                                  qc.invalidateQueries({ queryKey: ["jobs"] });
                                } catch {}
                              }}
                              className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                              title="Remove CV">
                              <Trash2 size={11} />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                    {cvUploading[job.id] && <div className="text-[10px] text-blue-500 mt-0.5">Uploading…</div>}
                    {cvUploadError[job.id] && <div className="text-[10px] text-red-500 mt-0.5">{cvUploadError[job.id]}</div>}
                  </td>

                  {/* 14. Skills */}
                  <td className="px-4 py-3">
                    {job.matched_skills?.length
                      ? <div className="flex flex-wrap gap-1">
                          {job.matched_skills.map((s: string) => (
                            <span key={s} className="text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200 px-1.5 py-0.5 rounded-md whitespace-nowrap">{s}</span>
                          ))}
                        </div>
                      : <Dash />}
                  </td>

                  {/* 15. Job URL */}
                  <td className="px-4 py-3">
                    {job.job_url
                      ? <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-800 whitespace-nowrap">
                          <ExternalLink size={10} /> View Job
                        </a>
                      : <Dash />}
                  </td>

                  {/* 15. Apply URL */}
                  <td className="px-4 py-3">
                    {job.apply_url
                      ? job.apply_url.startsWith("mailto:")
                        ? <a href={job.apply_url}
                              className="flex items-center gap-1 text-[11px] font-medium text-violet-600 hover:text-violet-800 whitespace-nowrap">
                            <Mail size={10} /> Email
                          </a>
                        : <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
                              className="flex items-center gap-1 text-[11px] font-medium text-violet-600 hover:text-violet-800 whitespace-nowrap">
                            <ExternalLink size={10} /> Apply
                          </a>
                      : <Dash />}
                  </td>

                  {/* 16. Summary */}
                  <td className="px-4 py-3 max-w-[200px]">
                    {job.job_description
                      ? <span className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed" title={job.job_description}>
                          {job.job_description.slice(0, 120)}{job.job_description.length > 120 ? "…" : ""}
                        </span>
                      : <Dash />}
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 whitespace-nowrap">
                      <button onClick={() => setApplyJob(job)}
                        title="Apply manually now"
                        className="flex items-center gap-1 text-[11px] bg-blue-600 text-white px-2.5 py-1.5 rounded-lg hover:bg-blue-700 font-medium shadow-sm">
                        <Zap size={10} /> Apply Now
                      </button>
                      <button onClick={() => setEditJob(job)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Edit">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => updateMutation.mutate({ id: job.id, data: { status: job.status } })}
                        className="p-1.5 text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Refresh">
                        <RefreshCw size={13} />
                      </button>
                      <button onClick={() => { if (confirm(`Delete "${job.title}"?`)) deleteMutation.mutate(job.id); }}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors" title="Delete">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="text-center py-20">
            <Briefcase size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No jobs found</p>
            <p className="text-gray-400 text-sm mt-1">Upload a CSV or sync a platform to get started</p>
          </div>
        )}
      </div>

      {/* Pagination footer */}
      {filtered.length > 0 && (
        <div className="flex items-center justify-between bg-white border border-gray-100 rounded-2xl px-5 py-3 shadow-sm">
          {/* Left: page size selector */}
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>Rows per page:</span>
            <div className="flex items-center gap-1">
              {PAGE_SIZE_OPTIONS.map(n => (
                <button key={n} onClick={() => handlePageSize(n)}
                  className={`w-9 h-8 rounded-lg text-xs font-semibold transition-colors ${
                    pageSize === n && !showCustomInput
                      ? "bg-blue-600 text-white shadow-sm"
                      : "text-gray-600 hover:bg-gray-100 border border-gray-200"
                  }`}>
                  {n}
                </button>
              ))}
              {/* Custom input */}
              {showCustomInput ? (
                <input
                  autoFocus
                  type="number"
                  min={1}
                  max={500}
                  value={customSize}
                  onChange={e => setCustomSize(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") {
                      const n = parseInt(customSize);
                      if (n > 0) handlePageSize(n);
                    }
                    if (e.key === "Escape") setShowCustomInput(false);
                  }}
                  onBlur={() => {
                    const n = parseInt(customSize);
                    if (n > 0) handlePageSize(n);
                    else setShowCustomInput(false);
                  }}
                  className="w-16 h-8 border border-blue-400 rounded-lg px-2 text-xs text-center focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g. 100"
                />
              ) : (
                <button
                  onClick={() => { setShowCustomInput(true); setCustomSize(""); }}
                  className={`px-2.5 h-8 rounded-lg text-xs font-semibold transition-colors border ${
                    !PAGE_SIZE_OPTIONS.includes(pageSize)
                      ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                      : "text-gray-600 hover:bg-gray-100 border-gray-200"
                  }`}>
                  {!PAGE_SIZE_OPTIONS.includes(pageSize) ? pageSize : "Custom"}
                </button>
              )}
            </div>
          </div>

          {/* Centre: info */}
          <div className="text-sm text-gray-500">
            Showing <span className="font-semibold text-gray-700">{Math.min((page - 1) * pageSize + 1, filtered.length)}</span>
            {" – "}
            <span className="font-semibold text-gray-700">{Math.min(page * pageSize, filtered.length)}</span>
            {" of "}
            <span className="font-semibold text-gray-700">{filtered.length}</span>
            {someSelected && <span className="ml-2 text-blue-600 font-semibold">({selected.size} selected)</span>}
          </div>


          {/* Right: page nav */}
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(1)} disabled={page === 1}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronsLeft size={15} />
            </button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronLeft size={15} />
            </button>
            {/* Page number buttons */}
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter(n => n === 1 || n === totalPages || Math.abs(n - page) <= 1)
              .reduce<(number | "…")[]>((acc, n, i, arr) => {
                if (i > 0 && n - (arr[i - 1] as number) > 1) acc.push("…");
                acc.push(n);
                return acc;
              }, [])
              .map((n, i) =>
                n === "…"
                  ? <span key={`e${i}`} className="px-1 text-gray-400 text-sm">…</span>
                  : <button key={n} onClick={() => setPage(n as number)}
                      className={`w-8 h-8 rounded-lg text-xs font-semibold transition-colors ${
                        page === n ? "bg-blue-600 text-white shadow-sm" : "text-gray-600 hover:bg-gray-100"
                      }`}>
                      {n}
                    </button>
              )}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronRight size={15} />
            </button>
            <button onClick={() => setPage(totalPages)} disabled={page === totalPages}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed">
              <ChevronsRight size={15} />
            </button>
          </div>
        </div>
      )}

      {/* Create Job Modal */}
      {showCreateModal && (
        <CreateJobModal
          onClose={() => setShowCreateModal(false)}
          onCreate={(data) => createMutation.mutate(data)}
        />
      )}

      {/* Apply Now Modal */}
      {applyJob && (
        <ApplyNowModal
          job={applyJob}
          onClose={() => { setApplyJob(null); qc.invalidateQueries({ queryKey: ["jobs"] }); }}
        />
      )}

      {/* Reschedule Modal */}
      {rescheduleJob && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-gray-900">Edit Schedule</h3>
                <p className="text-xs text-gray-500 mt-0.5 truncate max-w-[220px]">{rescheduleJob.title}</p>
              </div>
              <button onClick={() => setRescheduleJob(null)} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5">New send time (IST)</label>
            <input
              type="datetime-local"
              value={rescheduleVal}
              onChange={e => setRescheduleVal(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-[11px] text-gray-400 mt-1.5">Enter time in IST (India Standard Time, UTC+5:30)</p>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setRescheduleJob(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleReschedule} disabled={!rescheduleVal || rescheduling}
                className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2">
                {rescheduling ? <Loader2 size={14} className="animate-spin" /> : <AlarmClock size={14} />}
                Save Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assign Profile Modal */}
      {assignProfileJob && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-gray-900">Assign Profile</h3>
                <p className="text-xs text-gray-500 mt-0.5 truncate max-w-[220px]">{assignProfileJob.title}</p>
              </div>
              <button onClick={() => setAssignProfileJob(null)} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-3">Select the profile that will send the application email for this job.</p>
            <div className="flex flex-col gap-2 max-h-64 overflow-y-auto">
              {(activeProfiles as any[]).map((p: any) => (
                <button
                  key={p.id}
                  onClick={() => handleAssignProfile(p.id)}
                  disabled={assigningProfile}
                  className={`flex items-center gap-3 w-full text-left px-3 py-2.5 rounded-xl border transition-colors disabled:opacity-50 ${
                    assignProfileJob.matched_profile_id === p.id
                      ? "border-blue-400 bg-blue-50 text-blue-800"
                      : "border-gray-200 hover:border-blue-300 hover:bg-blue-50/50 text-gray-700"
                  }`}>
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-100 to-indigo-200 border border-blue-200 flex items-center justify-center text-[11px] font-bold text-blue-700 flex-shrink-0">
                    {(p.name || "?")[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold truncate">{p.name}</div>
                    {p.email && <div className="text-[11px] text-gray-400 truncate">{p.email}</div>}
                  </div>
                  {assignProfileJob.matched_profile_id === p.id && (
                    <Check size={14} className="text-blue-600 flex-shrink-0" />
                  )}
                  {assigningProfile && <Loader2 size={12} className="animate-spin flex-shrink-0" />}
                </button>
              ))}
              {(activeProfiles as any[]).length === 0 && (
                <p className="text-sm text-gray-400 text-center py-4">No active profiles found</p>
              )}
            </div>
            <button onClick={() => setAssignProfileJob(null)}
              className="w-full mt-4 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Manual Schedule Modal */}
      {scheduleJob && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-gray-900">Set Send Schedule</h3>
                <p className="text-xs text-gray-500 mt-0.5 truncate max-w-[220px]">{scheduleJob.title}</p>
              </div>
              <button onClick={() => setScheduleJob(null)} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5">Send time (IST)</label>
            <input
              type="datetime-local"
              value={scheduleVal}
              onChange={e => setScheduleVal(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
            <p className="text-[11px] text-gray-400 mt-1.5">Enter time in IST (India Standard Time, UTC+5:30)</p>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setScheduleJob(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleManualSchedule} disabled={!scheduleVal || scheduling}
                className="flex-1 bg-cyan-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-cyan-700 disabled:opacity-50 flex items-center justify-center gap-2">
                {scheduling ? <Loader2 size={14} className="animate-spin" /> : <AlarmClock size={14} />}
                Set Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Followup Reschedule Modal */}
      {rescheduleFollowup && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-gray-900">Edit Follow-up Schedule</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Follow-up #{rescheduleFollowup.fu.number} · {rescheduleFollowup.fu.status}
                </p>
              </div>
              <button onClick={() => setRescheduleFollowup(null)} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5">New send time (IST)</label>
            <input
              type="datetime-local"
              value={rescheduleFollowupVal}
              onChange={e => setRescheduleFollowupVal(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-[11px] text-gray-400 mt-1.5">Enter time in IST (India Standard Time, UTC+5:30)</p>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setRescheduleFollowup(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-xl text-sm font-medium hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleRescheduleFollowup} disabled={!rescheduleFollowupVal || reschedulingFollowup}
                className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2">
                {reschedulingFollowup ? <Loader2 size={14} className="animate-spin" /> : <AlarmClock size={14} />}
                Save Schedule
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
