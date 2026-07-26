"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

function extractError(e: any): string {
  const detail = e?.response?.data?.detail;
  if (!detail) return e?.message || "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || String(d)).join("; ");
  return String(detail);
}
import {
  getEmailAccounts, getProfileEmails, connectGmail,
  deleteEmailAccount, toggleEmailAccount, createEmailAccount, updateEmailAccount, sendTestEmail,
  addProfileEmail, deleteProfileEmail,
} from "@/lib/api";
import {
  Mail, Plus, Trash2, ToggleLeft, ToggleRight, CheckCircle, XCircle,
  AlertTriangle, RefreshCw, Link, Pencil, Eye, EyeOff, X, Check, Key, Send,
} from "lucide-react";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

const EMPTY_FORM = { display_name: "", email: "", client_id: "", client_secret: "", purpose: "job_applications" };

const PURPOSE_LABELS: Record<string, { label: string; color: string }> = {
  job_applications: { label: "Job Applications", color: "bg-blue-100 text-blue-700" },
  b2b: { label: "B2B Outreach", color: "bg-violet-100 text-violet-700" },
  both: { label: "Both", color: "bg-amber-100 text-amber-700" },
};

function AddEmailModal({ initial, onClose, onSave, saving }: {
  initial?: typeof EMPTY_FORM & { id?: string };
  onClose: () => void;
  onSave: (data: typeof EMPTY_FORM) => void;
  saving: boolean;
}) {
  const [form, setForm] = useState(initial || EMPTY_FORM);
  const [showSecret, setShowSecret] = useState(false);
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));
  const isEdit = !!initial?.id;

  const handleSave = () => {
    if (!form.display_name.trim()) { alert("Name is required"); return; }
    if (!form.email.trim()) { alert("Email is required"); return; }
    if (!isEdit && !form.client_id.trim()) { alert("Gmail Client ID is required"); return; }
    if (!isEdit && !form.client_secret.trim()) { alert("Gmail Client Secret is required"); return; }
    onSave(form);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">
              <Mail size={15} className="text-red-500" />
            </div>
            <h2 className="font-semibold text-gray-900">{isEdit ? "Edit Email Account" : "Add Email Account"}</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {/* Setup hint */}
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-3.5 text-xs text-blue-800 space-y-1.5">
            <p className="font-semibold flex items-center gap-1.5"><Key size={11} /> Where to get these credentials</p>
            <ol className="list-decimal list-inside space-y-1 text-blue-700">
              <li>Go to <span className="font-mono bg-blue-100 px-1 rounded">console.cloud.google.com</span></li>
              <li>APIs &amp; Services → Credentials → Create OAuth 2.0 Client ID</li>
              <li>Application type: <strong>Web application</strong></li>
              <li>Redirect URI: <span className="font-mono bg-blue-100 px-1 rounded">http://localhost:8000/api/v1/email-accounts/callback</span></li>
              <li>Copy Client ID and Client Secret below</li>
            </ol>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Display Name *</label>
              <input value={form.display_name} onChange={e => set("display_name", e.target.value)}
                placeholder="e.g. Satnam Singh"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Gmail Address *</label>
              <input value={form.email} onChange={e => set("email", e.target.value)}
                placeholder="satnam@gmail.com"
                type="email"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Gmail Client ID *</label>
              <input value={form.client_id} onChange={e => set("client_id", e.target.value)}
                placeholder="123456789-abc...apps.googleusercontent.com"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Gmail Client Secret *</label>
              <div className="relative">
                <input value={form.client_secret} onChange={e => set("client_secret", e.target.value)}
                  type={showSecret ? "text" : "password"}
                  placeholder="GOCSPX-..."
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 pr-10 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" />
                <button type="button" onClick={() => setShowSecret(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Account Purpose *</label>
              <select value={form.purpose} onChange={e => set("purpose", e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white">
                <option value="job_applications">Job Applications</option>
                <option value="b2b">B2B Outreach</option>
                <option value="both">Both</option>
              </select>
              <p className="text-xs text-gray-400 mt-1">Controls which emails are sent from this account</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose}
            className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving}
            className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700 flex items-center gap-2 shadow-sm font-medium disabled:opacity-60">
            {saving ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}
            {isEdit ? "Save Changes" : "Add Account"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EmailAccountsInner() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editAccount, setEditAccount] = useState<any>(null);
  const [testModal, setTestModal] = useState<{ id: string; email: string } | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testSending, setTestSending] = useState(false);
  const [addEmailModal, setAddEmailModal] = useState<{ profileId: string; profileName: string; existing: string[] } | null>(null);
  const [selectedEmails, setSelectedEmails] = useState<string[]>([]);

  const { data: accounts = [], isLoading: loadingAccounts } = useQuery({ queryKey: ["email-accounts"], queryFn: getEmailAccounts });
  const { data: profileEmails = [], isLoading: loadingProfiles } = useQuery({ queryKey: ["profile-emails"], queryFn: getProfileEmails });

  useEffect(() => {
    const connected = searchParams.get("connected");
    const error = searchParams.get("error");
    const isProfile = searchParams.get("profile");
    if (connected) {
      setToast({ msg: `${isProfile ? "Profile email" : "Account"} ${connected} connected successfully!`, type: "success" });
      qc.invalidateQueries({ queryKey: ["email-accounts"] });
      qc.invalidateQueries({ queryKey: ["profile-emails"] });
      window.history.replaceState({}, "", "/dashboard/email-accounts");
    } else if (error) {
      setToast({ msg: `Connection failed: ${error}`, type: "error" });
      window.history.replaceState({}, "", "/dashboard/email-accounts");
    }
  }, [searchParams]);

  useEffect(() => {
    if (toast) { const t = setTimeout(() => setToast(null), 5000); return () => clearTimeout(t); }
  }, [toast]);

  const createMutation = useMutation({
    mutationFn: createEmailAccount,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["email-accounts"] });
      setShowAddModal(false);
      setToast({ msg: "Account added! Now click Connect Gmail to authorise it.", type: "success" });
    },
    onError: (e: any) => setToast({ msg: extractError(e), type: "error" }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateEmailAccount(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-accounts"] });
      setEditAccount(null);
      setToast({ msg: "Account updated", type: "success" });
    },
    onError: (e: any) => setToast({ msg: extractError(e), type: "error" }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteEmailAccount,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email-accounts"] }),
  });

  const toggleMutation = useMutation({
    mutationFn: toggleEmailAccount,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email-accounts"] }),
  });

  const addProfileEmailMutation = useMutation({
    mutationFn: ({ profileId, email }: { profileId: string; email: string }) =>
      addProfileEmail(profileId, email, false),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile-emails"] });
      setAddEmailModal(null);
      setSelectedEmails([]);
      setToast({ msg: "Email linked. Now click Connect Gmail to authorise it.", type: "success" });
    },
    onError: (e: any) => setToast({ msg: extractError(e), type: "error" }),
  });

  const deleteProfileEmailMutation = useMutation({
    mutationFn: ({ profileId, emailId }: { profileId: string; emailId: string }) =>
      deleteProfileEmail(profileId, emailId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile-emails"] });
      setToast({ msg: "Email removed", type: "success" });
    },
    onError: (e: any) => setToast({ msg: extractError(e), type: "error" }),
  });

  const handleSendTest = async () => {
    if (!testModal) return;
    if (!testTo.trim()) { setToast({ msg: "Enter a recipient email", type: "error" }); return; }
    setTestSending(true);
    try {
      const res = await sendTestEmail(testModal.id, testTo.trim());
      setToast({ msg: res.message || "Test email sent!", type: "success" });
      setTestModal(null);
      setTestTo("");
    } catch (e: any) {
      setToast({ msg: extractError(e), type: "error" });
    } finally {
      setTestSending(false);
    }
  };

  const handleConnect = async (params?: { account_id?: string; profile_email_id?: string }) => {
    const key = params?.account_id || params?.profile_email_id || "new";
    setConnecting(key);
    try {
      const { auth_url } = await connectGmail(params);
      window.location.href = auth_url;
    } catch (e: any) {
      setToast({ msg: extractError(e), type: "error" });
      setConnecting(null);
    }
  };

  const accs = accounts as any[];
  const pemails = profileEmails as any[];

  return (
    <div className="space-y-8 max-w-3xl">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium ${toast.type === "success" ? "bg-emerald-600 text-white" : "bg-red-500 text-white"}`}>
          {toast.type === "success" ? <CheckCircle size={16} /> : <XCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {/* Modals */}
      {showAddModal && (
        <AddEmailModal
          onClose={() => setShowAddModal(false)}
          onSave={(data) => createMutation.mutate(data)}
          saving={createMutation.isPending}
        />
      )}
      {editAccount && (
        <AddEmailModal
          initial={editAccount}
          onClose={() => setEditAccount(null)}
          onSave={(data) => updateMutation.mutate({ id: editAccount.id, data })}
          saving={updateMutation.isPending}
        />
      )}

      {/* Send Test Email Modal */}
      {testModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => { setTestModal(null); setTestTo(""); }}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
                  <Send size={14} className="text-blue-600" />
                </div>
                <div>
                  <h2 className="font-semibold text-gray-900 text-sm">Send Test Email</h2>
                  <p className="text-[11px] text-gray-400">From: {testModal.email}</p>
                </div>
              </div>
              <button onClick={() => { setTestModal(null); setTestTo(""); }} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100">
                <X size={16} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="text-xs font-medium text-gray-500 block mb-1.5">Send test to *</label>
                <input
                  value={testTo}
                  onChange={e => setTestTo(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleSendTest()}
                  type="email"
                  placeholder="recipient@example.com"
                  autoFocus
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <p className="text-xs text-gray-400">A test email will be sent to confirm this Gmail account is working correctly.</p>
            </div>
            <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
              <button onClick={() => { setTestModal(null); setTestTo(""); }} className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">Cancel</button>
              <button onClick={handleSendTest} disabled={testSending}
                className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700 flex items-center gap-2 shadow-sm font-medium disabled:opacity-60">
                {testSending ? <RefreshCw size={13} className="animate-spin" /> : <Send size={13} />}
                {testSending ? "Sending..." : "Send Test"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email Accounts</h1>
          <p className="text-gray-500 text-sm mt-1">Connect Gmail accounts for sending job applications and outreach</p>
        </div>
        <button onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
          <Plus size={14} /> Add Email Account
        </button>
      </div>

      {/* Connected accounts */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Connected Accounts</h2>
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded-full font-medium">
            {accs.length} account{accs.length !== 1 ? "s" : ""}
          </span>
        </div>

        {loadingAccounts ? (
          <div className="space-y-3">{[...Array(2)].map((_, i) => <div key={i} className="h-20 bg-gray-100 rounded-2xl animate-pulse" />)}</div>
        ) : accs.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-12 text-center">
            <Mail size={32} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No accounts added yet</p>
            <p className="text-gray-400 text-sm mt-1">Click "Add Email Account" to get started</p>
            <button onClick={() => setShowAddModal(true)}
              className="mt-4 inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 font-medium">
              <Plus size={13} /> Add Email Account
            </button>
          </div>
        ) : (
          accs.map((account: any) => (
            <div key={account.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center flex-shrink-0">
                <Mail size={18} className="text-red-500" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="font-semibold text-gray-900 text-[15px]">{account.email}</span>
                  {account.is_authorized
                    ? <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"><CheckCircle size={9} /> Connected</span>
                    : <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700"><AlertTriangle size={9} /> Not authorised</span>}
                  {account.has_credentials && (
                    <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-600"><Key size={9} /> Credentials saved</span>
                  )}
                  {account.purpose && PURPOSE_LABELS[account.purpose] && (
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${PURPOSE_LABELS[account.purpose].color}`}>
                      {PURPOSE_LABELS[account.purpose].label}
                    </span>
                  )}
                </div>
                {account.display_name && account.display_name !== account.email && (
                  <p className="text-xs text-gray-400">{account.display_name}</p>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {/* Send Test Email — only if authorised */}
                {account.is_authorized && (
                  <button onClick={() => { setTestModal({ id: account.id, email: account.email }); setTestTo(""); }}
                    className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors">
                    <Send size={11} /> Send Test
                  </button>
                )}
                {/* Connect / Re-authorise */}
                <button onClick={() => handleConnect({ account_id: account.id })} disabled={!!connecting}
                  className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 transition-colors">
                  {connecting === account.id ? <RefreshCw size={11} className="animate-spin" /> : <Link size={11} />}
                  {account.is_authorized ? "Re-connect" : "Connect Gmail"}
                </button>
                {/* Edit */}
                <button onClick={() => setEditAccount({ ...account, client_id: "", client_secret: "", purpose: account.purpose || "job_applications" })}
                  className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-blue-600 hover:bg-blue-50 hover:border-blue-200 transition-colors" title="Edit">
                  <Pencil size={14} />
                </button>
                {/* Toggle */}
                <button onClick={() => toggleMutation.mutate(account.id)}
                  className={`p-2 rounded-xl border transition-colors ${account.is_active ? "text-emerald-600 bg-emerald-50 border-emerald-200 hover:bg-emerald-100" : "text-gray-400 bg-gray-50 border-gray-200 hover:bg-gray-100"}`}
                  title={account.is_active ? "Disable" : "Enable"}>
                  {account.is_active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                </button>
                {/* Delete */}
                <button onClick={() => { if (confirm(`Disconnect ${account.email}?`)) deleteMutation.mutate(account.id); }}
                  className="p-2 rounded-xl border border-gray-200 text-gray-400 hover:text-red-500 hover:bg-red-50 hover:border-red-200 transition-colors" title="Remove">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))
        )}
      </section>

      {/* Profile emails */}
      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Profile Sending Emails</h2>
          <p className="text-xs text-gray-400 mt-0.5">Add multiple Gmail accounts per profile — system rotates them, max 15 emails/day each with 5 min gap</p>
        </div>

        {loadingProfiles ? (
          <div className="space-y-3">{[...Array(3)].map((_, i) => <div key={i} className="h-16 bg-gray-100 rounded-2xl animate-pulse" />)}</div>
        ) : pemails.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-100 p-8 text-center text-sm text-gray-400">
            No profiles created yet. <a href="/dashboard/profiles" className="text-blue-600 hover:underline">Add a profile</a> first.
          </div>
        ) : (() => {
          // Group by profile
          const groups: Record<string, { profile_id: string; profile_name: string; emails: any[] }> = {};
          pemails.forEach((pe: any) => {
            if (!groups[pe.profile_id]) groups[pe.profile_id] = { profile_id: pe.profile_id, profile_name: pe.profile_name, emails: [] };
            groups[pe.profile_id].emails.push(pe);
          });
          return (
            <div className="space-y-4">
              {Object.values(groups).map((group) => (
                <div key={group.profile_id} className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50/60">
                    <span className="font-semibold text-gray-800 text-sm">{group.profile_name}</span>
                    <button
                      onClick={() => {
                        setAddEmailModal({ profileId: group.profile_id, profileName: group.profile_name, existing: group.emails.map((e: any) => e.email) });
                        setSelectedEmails([]);
                      }}
                      className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-gray-900 text-white hover:bg-gray-700"
                    >
                      <Plus size={11} /> Link Emails
                    </button>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left px-5 py-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Email</th>
                        <th className="text-left px-5 py-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Gmail Status</th>
                        <th className="px-5 py-2.5" />
                      </tr>
                    </thead>
                    <tbody>
                      {group.emails.map((pe: any) => (
                        <tr key={pe.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/40">
                          <td className="px-5 py-3 text-gray-700">
                            {pe.email}
                            {pe.is_primary && <span className="ml-2 text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-semibold">Primary</span>}
                          </td>
                          <td className="px-5 py-3">
                            {pe.connected
                              ? <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full w-fit">
                                  <CheckCircle size={11} /> Connected
                                </span>
                              : <span className="flex items-center gap-1.5 text-xs font-semibold text-red-600 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full w-fit">
                                  <XCircle size={11} /> Not connected
                                </span>}
                          </td>
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2 justify-end">
                              <button onClick={() => handleConnect({ profile_email_id: pe.id })} disabled={!!connecting}
                                className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
                                {connecting === pe.id ? <RefreshCw size={11} className="animate-spin" /> : <Link size={11} />}
                                {pe.connected ? "Re-authorise" : "Connect Gmail"}
                              </button>
                              {!pe.is_primary && (
                                <button
                                  onClick={() => { if (confirm(`Remove ${pe.email} from ${group.profile_name}?`)) deleteProfileEmailMutation.mutate({ profileId: group.profile_id, emailId: pe.id }); }}
                                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50"
                                  title="Remove email"
                                >
                                  <Trash2 size={13} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          );
        })()}
      </section>

      {/* Link emails to profile modal — multi-select from connected accounts */}
      {addEmailModal && (() => {
        const connectedAccounts = (accounts as any[]).filter((a: any) => a.is_authorized);
        const available = connectedAccounts.filter((a: any) => !addEmailModal.existing.includes(a.email));
        const toggleEmail = (email: string) =>
          setSelectedEmails(prev => prev.includes(email) ? prev.filter(e => e !== email) : [...prev, email]);
        const handleLink = async () => {
          for (const email of selectedEmails) {
            await addProfileEmailMutation.mutateAsync({ profileId: addEmailModal.profileId, email });
          }
          setAddEmailModal(null);
        };
        return (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setAddEmailModal(null)}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                <div>
                  <h3 className="font-semibold text-gray-900">Link emails to {addEmailModal.profileName}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">Select one or more connected Gmail accounts. System rotates between them (max 15/day each).</p>
                </div>
                <button onClick={() => setAddEmailModal(null)} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100"><X size={16} /></button>
              </div>
              <div className="p-4 space-y-2 max-h-72 overflow-y-auto">
                {available.length === 0 ? (
                  <div className="text-center py-8 text-sm text-gray-400">
                    {connectedAccounts.length === 0
                      ? "No connected Gmail accounts yet. Add and connect an account above first."
                      : "All connected accounts are already linked to this profile."}
                  </div>
                ) : available.map((a: any) => {
                  const checked = selectedEmails.includes(a.email);
                  return (
                    <label key={a.id} className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer border transition-colors ${checked ? "border-blue-300 bg-blue-50" : "border-gray-100 hover:bg-gray-50"}`}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleEmail(a.email)}
                        className="w-4 h-4 accent-blue-600 rounded"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{a.display_name || a.email}</p>
                        <p className="text-xs text-gray-400 truncate">{a.email}</p>
                      </div>
                      <span className="flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full shrink-0">
                        <CheckCircle size={10} /> Connected
                      </span>
                    </label>
                  );
                })}
              </div>
              <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
                <button onClick={() => setAddEmailModal(null)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl">Cancel</button>
                <button
                  onClick={handleLink}
                  disabled={selectedEmails.length === 0 || addProfileEmailMutation.isPending}
                  className="px-5 py-2 text-sm font-semibold bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-60 flex items-center gap-2"
                >
                  {addProfileEmailMutation.isPending ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}
                  Link {selectedEmails.length > 0 ? `${selectedEmails.length} account${selectedEmails.length > 1 ? "s" : ""}` : "accounts"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* How it works */}
      <section className="bg-blue-50 border border-blue-100 rounded-2xl p-5 space-y-2">
        <h3 className="text-sm font-semibold text-blue-900">How it works</h3>
        <ul className="text-xs text-blue-800 space-y-1.5">
          <li className="flex items-start gap-2"><span className="text-blue-400 font-bold mt-0.5">1.</span> Click <strong>"Add Email Account"</strong> — enter the display name, email, and your Google OAuth credentials.</li>
          <li className="flex items-start gap-2"><span className="text-blue-400 font-bold mt-0.5">2.</span> Click <strong>"Connect Gmail"</strong> on the account to complete OAuth authorisation.</li>
          <li className="flex items-start gap-2"><span className="text-blue-400 font-bold mt-0.5">3.</span> When creating a profile, select the connected email as the sending address.</li>
          <li className="flex items-start gap-2"><span className="text-blue-400 font-bold mt-0.5">4.</span> All outreach emails are sent on a smart schedule to avoid spam filters.</li>
        </ul>
      </section>
    </div>
  );
}

export default function EmailAccountsPage() {
  return (
    <Suspense fallback={<div className="animate-pulse space-y-4"><div className="h-8 bg-gray-200 rounded w-48" /><div className="h-64 bg-gray-100 rounded-2xl" /></div>}>
      <EmailAccountsInner />
    </Suspense>
  );
}
