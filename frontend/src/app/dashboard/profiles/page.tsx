"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getProfiles, createProfile, updateProfile, deleteProfile, uploadCV, deleteCv, downloadCv, getEmailAccounts, addProfileEmail, deleteProfileEmail } from "@/lib/api";
import { Plus, Upload, User, Pencil, Trash2, Check, X, Mail, Star, FileText, ChevronDown, ChevronUp, Link, Download, CheckCircle } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const EMPTY_FORM = { name: "", bio: "", skills: "", years_experience: "", is_active: true };

function ProfileForm({
  title, initial, profileId, existingEmails, onSave, onCancel, saving, error,
}: {
  title: string;
  initial: typeof EMPTY_FORM;
  profileId?: string;
  existingEmails?: string[];
  onSave: (d: any, selectedEmails: string[]) => void;
  onCancel: () => void;
  saving: boolean;
  error?: string | null;
}) {
  const [form, setForm] = useState(initial);
  const [selectedEmails, setSelectedEmails] = useState<string[]>(existingEmails || []);
  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }));

  useEffect(() => { setForm(initial); }, [initial.name, initial.years_experience, initial.bio, initial.skills]);

  const { data: emailAccounts = [] } = useQuery({ queryKey: ["email-accounts"], queryFn: getEmailAccounts });
  const connectedEmails = (emailAccounts as any[]).filter((a: any) => a.is_authorized && a.is_active);

  const toggleEmail = (email: string) =>
    setSelectedEmails(prev => prev.includes(email) ? prev.filter(e => e !== email) : [...prev, email]);

  const handleSave = () => {
    if (!form.name.trim()) { alert("Name is required"); return; }
    if (selectedEmails.length === 0) { alert("Select at least one sending email"); return; }
    const skills = form.skills.split(",").map(s => ({ skill: s.trim(), skill_type: "primary" })).filter(s => s.skill);
    const yearsExpStr = String(form.years_experience ?? "").trim().replace(/[^0-9]/g, "");
    const yearsExp = yearsExpStr !== "" ? parseInt(yearsExpStr, 10) : undefined;
    onSave({ name: form.name, email: selectedEmails[0], bio: form.bio, years_experience: yearsExp, is_active: form.is_active, skills }, selectedEmails);
  };

  return (
    <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-6 space-y-4">
      <h2 className="font-semibold text-gray-900">{title}</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Full Name *</label>
          <input value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. Satinder Singh"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>

        {/* Multi-select sending emails */}
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">
            Sending Emails *
            <span className="ml-1.5 text-gray-400 font-normal">— select one or more</span>
          </label>
          {connectedEmails.length === 0 ? (
            <div className="border border-dashed border-gray-200 rounded-xl px-3 py-3 text-xs text-gray-400 text-center">
              No connected Gmail accounts.{" "}
              <a href="/dashboard/email-accounts" className="text-blue-500 hover:underline">Connect one first →</a>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-xl divide-y divide-gray-100 overflow-hidden">
              {connectedEmails.map((a: any) => {
                const checked = selectedEmails.includes(a.email);
                return (
                  <label key={a.id} className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors ${checked ? "bg-blue-50" : "hover:bg-gray-50"}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleEmail(a.email)}
                      className="w-4 h-4 accent-blue-600 rounded shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-800 truncate">{a.email}</p>
                      {a.display_name && a.display_name !== a.email && (
                        <p className="text-[10px] text-gray-400 truncate">{a.display_name}</p>
                      )}
                    </div>
                    {checked && selectedEmails[0] === a.email && (
                      <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-semibold shrink-0">Primary</span>
                    )}
                    <CheckCircle size={13} className={checked ? "text-blue-500 shrink-0" : "text-gray-200 shrink-0"} />
                  </label>
                );
              })}
            </div>
          )}
          <div className="mt-1.5 flex items-center gap-1.5">
            <Link size={9} className="text-gray-400" />
            <a href="/dashboard/email-accounts" className="text-[10px] text-blue-500 hover:underline font-medium">
              {`Manage email accounts (${connectedEmails.length} connected)`}
            </a>
          </div>
          {selectedEmails.length > 1 && (
            <p className="text-[10px] text-gray-400 mt-1">
              System rotates between {selectedEmails.length} accounts · max 15 emails/day each
            </p>
          )}
        </div>

        <div className="col-span-2">
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Primary Skills <span className="text-gray-400">(comma-separated)</span></label>
          <input value={form.skills} onChange={e => set("skills", e.target.value)} placeholder="React, Node.js, TypeScript, WordPress"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1.5">
            Years of Experience <span className="text-gray-400">(used in email: "X years of experience")</span>
          </label>
          <input
            type="text"
            value={form.years_experience}
            onChange={e => set("years_experience", e.target.value)}
            placeholder="e.g. 8 or 15+"
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-[10px] text-gray-400 mt-1">Leave blank to let AI estimate from your bio and skills.</p>
        </div>
        <div className="col-span-2">
          <label className="text-xs font-medium text-gray-500 block mb-1.5">Bio <span className="text-gray-400">(used by AI for email generation)</span></label>
          <textarea value={form.bio} onChange={e => set("bio", e.target.value)} rows={3}
            placeholder="Brief background — years of experience, key strengths, type of roles targeted..."
            className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
        </div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="is_active" checked={form.is_active} onChange={e => set("is_active", e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 accent-blue-600" />
          <label htmlFor="is_active" className="text-sm text-gray-600 cursor-pointer">Active (used for job matching)</label>
        </div>
      </div>
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl px-4 py-2.5">
          {error}
        </div>
      )}
      <div className="flex gap-2 pt-1">
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium disabled:opacity-50">
          <Check size={13} /> {saving ? "Saving..." : "Save Profile"}
        </button>
        <button onClick={onCancel}
          className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function ProfilesPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ["profiles"], queryFn: getProfiles });
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [uploadError, setUploadError] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [cvRegion, setCvRegion] = useState<Record<string, string>>({});

  const toggleExpand = (id: string) => setExpanded(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const handleCVUpload = (profileId: string, file: File, region?: string) => {
    setUploadError(e => ({ ...e, [profileId]: "" }));
    setUploadProgress(p => ({ ...p, [profileId]: 0 }));
    uploadCV(profileId, file, (pct) => setUploadProgress(p => ({ ...p, [profileId]: pct })), region || null)
      .then(() => {
        setUploadProgress(p => ({ ...p, [profileId]: 100 }));
        qc.invalidateQueries({ queryKey: ["profiles"] });
        setTimeout(() => setUploadProgress(p => { const n = { ...p }; delete n[profileId]; return n; }), 1500);
      })
      .catch((err: any) => {
        setUploadError(e => ({ ...e, [profileId]: err.message || "Upload failed" }));
        setUploadProgress(p => { const n = { ...p }; delete n[profileId]; return n; });
      });
  };

  const createMutation = useMutation({
    mutationFn: async ({ data, emails }: { data: any; emails: string[] }) => {
      const profile = await createProfile(data);
      for (let i = 0; i < emails.length; i++) {
        await addProfileEmail(profile.id, emails[i], i === 0);
      }
      return profile;
    },
    onSuccess: () => { setSaveError(null); qc.invalidateQueries({ queryKey: ["profiles"] }); setShowAdd(false); },
    onError: (e: any) => setSaveError(e?.response?.data?.detail || e?.message || "Failed to save profile"),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data, emails, existingEmailObjs }: {
      id: string; data: any; emails: string[];
      existingEmailObjs: { id: string; email: string; is_primary?: boolean }[];
    }) => {
      // 1. Save core profile fields
      await updateProfile(id, data);

      // 2. Add emails that are newly selected (idempotent on backend)
      for (let i = 0; i < emails.length; i++) {
        await addProfileEmail(id, emails[i], i === 0);
      }

      // 3. Remove emails that were deselected
      for (const existing of existingEmailObjs) {
        if (!emails.includes(existing.email)) {
          await deleteProfileEmail(id, existing.id);
        }
      }
    },
    onSuccess: async () => { setSaveError(null); await qc.refetchQueries({ queryKey: ["profiles"] }); setEditId(null); },
    onError: (e: any) => {
      const detail = e?.response?.data?.detail;
      const msg = Array.isArray(detail) ? detail.map((d: any) => d?.msg).join(", ") : (detail || e?.message || "Failed to save");
      setSaveError(msg);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const deleteCvMutation = useMutation({
    mutationFn: ({ profileId, cvId }: { profileId: string; cvId: string }) => deleteCv(profileId, cvId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });

  if (isLoading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-40" />
      {[...Array(3)].map((_, i) => <div key={i} className="h-32 bg-gray-100 rounded-2xl" />)}
    </div>
  );

  const profiles = data as any[];

  return (
    <div className="space-y-5 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Profiles</h1>
          <p className="text-gray-500 text-sm mt-1">Manage candidate profiles used for job applications</p>
        </div>
        <button onClick={() => { setShowAdd(true); setEditId(null); }}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
          <Plus size={14} /> Add Profile
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <ProfileForm
          title="Add New Profile"
          initial={EMPTY_FORM}
          saving={createMutation.isPending}
          error={saveError}
          onSave={(d, emails) => { setSaveError(null); createMutation.mutate({ data: d, emails }); }}
          onCancel={() => { setSaveError(null); setShowAdd(false); }}
        />
      )}

      {/* Profile cards */}
      <div className="space-y-4">
        {profiles.map((profile: any) => {
          const isEditing = editId === profile.id;
          const isExpanded = expanded.has(profile.id);
          const skills: any[] = profile.skills || [];
          const emails: any[] = profile.emails || [];
          const cvs: any[] = profile.cvs || [];
          const initials = profile.name?.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase() || "?";

          if (isEditing) {
            const skillStr = skills.filter((s: any) => s.type === "primary" || s.skill_type === "primary").map((s: any) => s.skill).join(", ");
            return (
              <ProfileForm
                key={profile.id}
                title={`Edit — ${profile.name}`}
                initial={{ name: profile.name, bio: profile.bio || "", skills: skillStr, years_experience: profile.years_experience != null ? String(profile.years_experience) : "", is_active: profile.is_active !== false }}
                profileId={profile.id}
                existingEmails={emails.map((e: any) => e.email)}
                saving={updateMutation.isPending}
                error={saveError}
                onSave={(d, selectedEmails) => { setSaveError(null); updateMutation.mutate({ id: profile.id, data: d, emails: selectedEmails, existingEmailObjs: emails }); }}
                onCancel={() => { setSaveError(null); setEditId(null); }}
              />
            );
          }

          return (
            <div key={profile.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              {/* Main row */}
              <div className="p-5 flex items-start gap-4">
                {/* Avatar */}
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0 ${profile.is_active !== false ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-400"}`}>
                  {initials}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-semibold text-gray-900 text-[15px]">{profile.name}</span>
                    {profile.is_active !== false
                      ? <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />Active</span>
                      : <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">Inactive</span>}
                  </div>

                  {/* Profile-level total */}
                  <div className="flex items-center gap-2 mt-1.5 mb-1">
                    <span className="text-[11px] text-gray-400">Total jobs matched:</span>
                    <span className="text-[11px] font-bold text-gray-700">{profile.total_jobs ?? 0}</span>
                    {profile.years_experience != null && (
                      <>
                        <span className="text-gray-300">·</span>
                        <span className="text-[11px] text-gray-400">Experience:</span>
                        <span className="text-[11px] font-bold text-gray-700">{profile.years_experience} yrs</span>
                      </>
                    )}
                  </div>

                  {/* Per-email breakdown */}
                  <div className="flex flex-col gap-1.5">
                    {emails.map((e: any) => (
                      <div key={e.id} className="flex items-center gap-2 text-xs bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-xl w-fit">
                        <Mail size={9} className="text-gray-400 shrink-0" />
                        <span className="text-gray-700 font-medium">{e.email}</span>
                        {e.is_primary && <Star size={9} className="text-amber-500 fill-amber-500 shrink-0" />}
                        <span className="text-gray-300">|</span>
                        <span className="text-gray-500">Assigned: <span className="font-semibold text-gray-700">{e.assigned_count ?? 0}</span></span>
                        <span className="text-gray-300">·</span>
                        <span className="text-emerald-600 font-semibold">{e.sent_count ?? 0} sent</span>
                        {(e.scheduled_count ?? 0) > 0 && (
                          <>
                            <span className="text-gray-300">·</span>
                            <span className="text-blue-500 font-semibold">{e.scheduled_count} queued</span>
                          </>
                        )}
                      </div>
                    ))}
                    {emails.length === 0 && profile.email && (
                      <span className="flex items-center gap-1 text-xs text-gray-500 bg-gray-50 border border-gray-200 px-2 py-0.5 rounded-full">
                        <Mail size={9} className="text-gray-400" />{profile.email}
                      </span>
                    )}
                  </div>

                  {/* Skills */}
                  {skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {skills.slice(0, 8).map((s: any, i: number) => (
                        <span key={i} className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${s.type === "primary" || s.skill_type === "primary" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"}`}>
                          {s.skill}
                        </span>
                      ))}
                      {skills.length > 8 && <span className="text-[11px] text-gray-400">+{skills.length - 8} more</span>}
                    </div>
                  )}

                  {/* CVs */}
                  {cvs.length > 0 && (
                    <div className="flex flex-col gap-1 mt-2">
                      {cvs.map((cv: any) => {
                        const regionLabel: Record<string, { label: string; color: string }> = {
                          US:    { label: "🇺🇸 US",          color: "bg-blue-100 text-blue-700" },
                          CA:    { label: "🇨🇦 Canada",       color: "bg-red-100 text-red-700" },
                          UK:    { label: "🇬🇧 UK",           color: "bg-purple-100 text-purple-700" },
                          AU:    { label: "🇦🇺 Australia",    color: "bg-yellow-100 text-yellow-700" },
                          AE:    { label: "🇦🇪 UAE",          color: "bg-green-100 text-green-700" },
                          IN:    { label: "🇮🇳 India",        color: "bg-orange-100 text-orange-700" },
                          DE:    { label: "🇩🇪 Germany",      color: "bg-slate-100 text-slate-700" },
                          NZ:    { label: "🇳🇿 NZ",           color: "bg-teal-100 text-teal-700" },
                          SG:    { label: "🇸🇬 Singapore",    color: "bg-rose-100 text-rose-700" },
                          PK:    { label: "🇵🇰 Pakistan",     color: "bg-emerald-100 text-emerald-700" },
                          IE:    { label: "🇮🇪 Ireland",      color: "bg-green-100 text-green-700" },
                          ZA:    { label: "🇿🇦 S. Africa",    color: "bg-yellow-100 text-yellow-700" },
                          NG:    { label: "🇳🇬 Nigeria",      color: "bg-green-100 text-green-700" },
                          KE:    { label: "🇰🇪 Kenya",        color: "bg-red-100 text-red-700" },
                          FR:    { label: "🇫🇷 France",       color: "bg-blue-100 text-blue-700" },
                          NL:    { label: "🇳🇱 Netherlands",  color: "bg-orange-100 text-orange-700" },
                          SE:    { label: "🇸🇪 Sweden",       color: "bg-blue-100 text-blue-700" },
                          DK:    { label: "🇩🇰 Denmark",      color: "bg-red-100 text-red-700" },
                          NO:    { label: "🇳🇴 Norway",       color: "bg-red-100 text-red-700" },
                          FI:    { label: "🇫🇮 Finland",      color: "bg-blue-100 text-blue-700" },
                          IT:    { label: "🇮🇹 Italy",        color: "bg-green-100 text-green-700" },
                          ES:    { label: "🇪🇸 Spain",        color: "bg-yellow-100 text-yellow-700" },
                          OTHER: { label: "🌍 Other",         color: "bg-amber-100 text-amber-700" },
                          // legacy tag support
                          US_CA: { label: "🇺🇸 US/CA",       color: "bg-blue-100 text-blue-700" },
                        };
                        const rd = cv.region ? regionLabel[cv.region] : null;
                        return (
                          <div key={cv.id} className="flex items-center gap-1.5 text-xs text-gray-500">
                            <FileText size={11} className="text-emerald-600 flex-shrink-0" />
                            {rd && <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${rd.color}`}>{rd.label}</span>}
                            <span className="text-emerald-700 font-medium truncate max-w-[140px]" title={cv.file_name}>{cv.file_name}</span>
                            <button
                              onClick={() => downloadCv(profile.id, cv.id, cv.file_name)}
                              className="p-0.5 text-gray-300 hover:text-blue-500 transition-colors flex-shrink-0"
                              title="Download CV">
                              <Download size={11} />
                            </button>
                            <button
                              onClick={() => { if (confirm("Delete this CV?")) deleteCvMutation.mutate({ profileId: profile.id, cvId: cv.id }); }}
                              className="p-0.5 text-gray-300 hover:text-red-500 transition-colors flex-shrink-0"
                              title="Delete CV">
                              <X size={11} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {/* Upload progress */}
                  {uploadProgress[profile.id] !== undefined && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                        <span>Uploading…</span><span>{uploadProgress[profile.id]}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full transition-all duration-200" style={{ width: `${uploadProgress[profile.id]}%` }} />
                      </div>
                    </div>
                  )}
                  {uploadError[profile.id] && (
                    <div className="mt-1 text-[10px] text-red-500 font-medium">{uploadError[profile.id]}</div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {/* Upload CV — region selector + file input */}
                  <div className="flex items-center gap-1">
                    <select
                      value={cvRegion[profile.id] ?? ""}
                      onChange={e => setCvRegion(r => ({ ...r, [profile.id]: e.target.value }))}
                      className="text-[11px] font-medium px-1.5 py-1.5 rounded-xl border border-gray-200 text-gray-600 bg-white focus:outline-none focus:border-blue-400"
                      title="CV region">
                      <option value="">— Select country —</option>
                      <option value="US">🇺🇸 United States</option>
                      <option value="CA">🇨🇦 Canada</option>
                      <option value="UK">🇬🇧 United Kingdom</option>
                      <option value="AU">🇦🇺 Australia</option>
                      <option value="AE">🇦🇪 UAE</option>
                      <option value="IN">🇮🇳 India</option>
                      <option value="DE">🇩🇪 Germany</option>
                      <option value="NZ">🇳🇿 New Zealand</option>
                      <option value="SG">🇸🇬 Singapore</option>
                      <option value="PK">🇵🇰 Pakistan</option>
                      <option value="IE">🇮🇪 Ireland</option>
                      <option value="ZA">🇿🇦 South Africa</option>
                      <option value="NG">🇳🇬 Nigeria</option>
                      <option value="KE">🇰🇪 Kenya</option>
                      <option value="FR">🇫🇷 France</option>
                      <option value="NL">🇳🇱 Netherlands</option>
                      <option value="SE">🇸🇪 Sweden</option>
                      <option value="DK">🇩🇰 Denmark</option>
                      <option value="NO">🇳🇴 Norway</option>
                      <option value="FI">🇫🇮 Finland</option>
                      <option value="IT">🇮🇹 Italy</option>
                      <option value="ES">🇪🇸 Spain</option>
                      <option value="OTHER">🌍 Other</option>
                    </select>
                    <button onClick={() => fileRefs.current[profile.id]?.click()}
                      disabled={uploadProgress[profile.id] !== undefined}
                      className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
                      title="Upload CV">
                      <Upload size={12} /> CV
                    </button>
                  </div>
                  <input type="file" accept=".docx,.doc,.pdf" className="hidden"
                    ref={el => { fileRefs.current[profile.id] = el; }}
                    onChange={e => { if (e.target.files?.[0]) { handleCVUpload(profile.id, e.target.files[0], cvRegion[profile.id] || undefined); e.target.value = ""; } }} />

                  {/* Edit */}
                  <button onClick={() => setEditId(profile.id)}
                    className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-blue-600 hover:bg-blue-50 hover:border-blue-200 transition-colors"
                    title="Edit">
                    <Pencil size={14} />
                  </button>

                  {/* Delete */}
                  <button
                    onClick={() => { if (confirm(`Delete profile "${profile.name}"? This cannot be undone.`)) deleteMutation.mutate(profile.id); }}
                    disabled={deleteMutation.isPending}
                    className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-red-500 hover:bg-red-50 hover:border-red-200 transition-colors disabled:opacity-50"
                    title="Delete">
                    <Trash2 size={14} />
                  </button>

                  {/* Expand bio */}
                  {profile.bio && (
                    <button onClick={() => toggleExpand(profile.id)}
                      className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:bg-gray-50 transition-colors">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  )}
                </div>
              </div>

              {/* Bio expand */}
              {isExpanded && profile.bio && (
                <div className="px-5 pb-4 border-t border-gray-50 pt-3">
                  <p className="text-xs text-gray-500 font-medium mb-1 uppercase tracking-wide">Bio</p>
                  <p className="text-sm text-gray-600 leading-relaxed">{profile.bio}</p>
                </div>
              )}
            </div>
          );
        })}

        {profiles.length === 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
            <User size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-600 font-semibold">No profiles yet</p>
            <p className="text-gray-400 text-sm mt-1">Add a profile for each candidate you want to apply jobs for</p>
            <button onClick={() => setShowAdd(true)} className="mt-4 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 font-medium">
              Add First Profile
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
