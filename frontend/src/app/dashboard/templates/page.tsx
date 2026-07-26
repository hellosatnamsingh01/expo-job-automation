"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTemplates, createTemplate, updateTemplate, deleteTemplate } from "@/lib/api";
import { Plus, Edit2, Trash2, X, CheckCircle, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

// ── constants ────────────────────────────────────────────────────────────────

const B2B_INDUSTRIES = [
  "SaaS / Tech",
  "E-Commerce",
  "Healthcare / MedTech",
  "Real Estate / PropTech",
  "Generic (fallback for all industries)",
];

const B2B_TYPES = [
  { value: "b2b_initial",    label: "Initial Email" },
  { value: "b2b_followup_1", label: "Follow-up #1  (Day 3)" },
  { value: "b2b_followup_2", label: "Follow-up #2  (Day 7)" },
  { value: "b2b_followup_3", label: "Follow-up #3  (Day 14)" },
];

const JOB_TYPES = [
  { value: "job_initial",    label: "Initial Email" },
  { value: "job_followup_1", label: "Follow-up #1" },
  { value: "job_followup_2", label: "Follow-up #2" },
  { value: "job_followup_3", label: "Follow-up #3" },
];

const B2B_VARS  = "{name}  {company}  {industry}  {sender_name}";
const JOB_VARS  = "{name}  {company}  {role}  {skills}  {sender_name}";

const EMPTY_FORM = {
  name: "", template_type: "b2b_initial", subject: "", body: "",
  industry: "Generic (fallback for all industries)", is_default: true,
};

// ── helpers ──────────────────────────────────────────────────────────────────

function typeLabel(t: string) {
  return B2B_TYPES.find(x => x.value === t)?.label
    ?? JOB_TYPES.find(x => x.value === t)?.label
    ?? t.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function industryForApi(raw: string) {
  return raw === "Generic (fallback for all industries)" ? null : raw;
}

// ── sub-components ───────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button onClick={onChange}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${checked ? "bg-emerald-500" : "bg-gray-300"}`}>
      <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : "translate-x-0"}`} />
    </button>
  );
}

function TemplateModal({ initial, onClose, onSave, saving, isB2B }: {
  initial?: any;
  onClose: () => void;
  onSave: (data: any) => void;
  saving: boolean;
  isB2B: boolean;
}) {
  const isEdit = !!initial?.id;
  const [form, setForm] = useState(initial ?? { ...EMPTY_FORM, template_type: isB2B ? "b2b_initial" : "job_initial" });
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const types = isB2B ? B2B_TYPES : JOB_TYPES;
  const vars  = isB2B ? B2B_VARS : JOB_VARS;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 sticky top-0 bg-white z-10">
          <h2 className="font-semibold text-gray-900">{isEdit ? "Edit Template" : "New Template"}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 p-1 rounded-lg hover:bg-gray-100"><X size={16} /></button>
        </div>

        <div className="p-6 space-y-4">
          {/* variables hint */}
          <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-2.5 text-xs text-blue-700">
            <span className="font-semibold">Available variables: </span>{vars}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Template Name *</label>
              <input value={form.name} onChange={e => set("name", e.target.value)}
                placeholder="e.g. SaaS Initial Outreach"
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Email Type *</label>
              <select value={form.template_type} onChange={e => set("template_type", e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                {types.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {isB2B && (
              <div className="col-span-2">
                <label className="text-xs font-medium text-gray-500 block mb-1">Industry</label>
                <select value={form.industry ?? "Generic (fallback for all industries)"} onChange={e => set("industry", e.target.value)}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                  {B2B_INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
                </select>
                <p className="text-[11px] text-gray-400 mt-1">
                  Industry-specific templates are used first. If none exists for a lead's industry, the Generic template is used as fallback.
                </p>
              </div>
            )}

            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-500 block mb-1">Subject Line *</label>
              <input value={form.subject} onChange={e => set("subject", e.target.value)}
                placeholder="e.g. Quick question about {company}'s tech roadmap"
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-500 block mb-1">Email Body *</label>
              <textarea value={form.body} onChange={e => set("body", e.target.value)}
                rows={10} placeholder="Write your email body here. Use variables like {name}, {company}…"
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            <div className="col-span-2 flex items-center gap-2">
              <input type="checkbox" id="is_default" checked={form.is_default}
                onChange={e => set("is_default", e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600" />
              <label htmlFor="is_default" className="text-sm text-gray-700">
                Set as default for this type{isB2B ? " + industry" : ""}
              </label>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100 sticky bottom-0 bg-white">
          <button onClick={onClose} className="border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50">Cancel</button>
          <button onClick={() => {
            if (!form.name.trim()) { alert("Name is required"); return; }
            if (!form.subject.trim()) { alert("Subject is required"); return; }
            if (!form.body.trim()) { alert("Body is required"); return; }
            onSave({
              ...form,
              industry: isB2B ? industryForApi(form.industry ?? "") : null,
            });
          }} disabled={saving}
            className="bg-blue-600 text-white px-5 py-2 rounded-xl text-sm hover:bg-blue-700 font-medium shadow-sm disabled:opacity-60">
            {saving ? "Saving…" : "Save Template"}
          </button>
        </div>
      </div>
    </div>
  );
}

function TemplateCard({ t, onEdit, onDelete, onToggle, onToggleDefault }: {
  t: any; onEdit: () => void; onDelete: () => void;
  onToggle: () => void; onToggleDefault: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`bg-white rounded-2xl border shadow-sm transition-opacity ${t.is_active ? "border-gray-100" : "border-gray-100 opacity-60"}`}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <p className="font-semibold text-sm text-gray-900">{t.name}</p>
              {t.is_default && (
                <span className="text-[10px] font-semibold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Default</span>
              )}
              {!t.is_active && (
                <span className="text-[10px] font-semibold bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Disabled</span>
              )}
              <span className="text-[10px] text-gray-400 ml-auto">
                Used {t.times_used}× · {t.open_count} opens · {t.reply_count} replies
              </span>
            </div>
            <p className="text-xs text-gray-500 truncate">
              <span className="font-medium text-gray-600">Subject: </span>{t.subject}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Toggle checked={t.is_active} onChange={onToggle} />
            <button onClick={() => setExpanded(v => !v)}
              className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100">
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            <button onClick={onEdit} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50" title="Edit">
              <Edit2 size={14} />
            </button>
            <button onClick={onDelete} className="p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50" title="Delete">
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {expanded && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <pre className="text-xs text-gray-600 whitespace-pre-wrap font-sans leading-relaxed bg-gray-50 rounded-xl p-3">
              {t.body}
            </pre>
            {!t.is_default && (
              <button onClick={onToggleDefault}
                className="mt-2 text-xs text-blue-600 hover:underline">
                Set as default
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── main page ────────────────────────────────────────────────────────────────

type Tab = "b2b" | "job";

export default function TemplatesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("b2b");
  const [modal, setModal] = useState<{ open: boolean; initial?: any }>({ open: false });
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const { data = [], isLoading } = useQuery({ queryKey: ["templates"], queryFn: () => getTemplates() });
  const templates = data as any[];

  const createMut = useMutation({
    mutationFn: createTemplate,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["templates"] }); setModal({ open: false }); showToast("Template saved"); },
    onError: () => showToast("Save failed", "error"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateTemplate(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["templates"] }); setModal({ open: false }); showToast("Template updated"); },
    onError: () => showToast("Update failed", "error"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["templates"] }); showToast("Template deleted"); },
    onError: () => showToast("Delete failed", "error"),
  });

  const handleSave = (formData: any) => {
    if (modal.initial?.id) {
      updateMut.mutate({ id: modal.initial.id, data: formData });
    } else {
      createMut.mutate(formData);
    }
  };

  const saving = createMut.isPending || updateMut.isPending;

  // ── group B2B templates by industry → type ──
  const b2bTemplates = templates.filter(t => t.template_type.startsWith("b2b_"));
  const jobTemplates = templates.filter(t => t.template_type.startsWith("job_"));

  // Industries present in the data + the standard list
  const industriesInData = Array.from(new Set(
    b2bTemplates.map(t => t.industry ?? "Generic (fallback for all industries)")
  ));
  const allIndustries = Array.from(new Set([...B2B_INDUSTRIES, ...industriesInData]));

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium ${toast.type === "success" ? "bg-emerald-600 text-white" : "bg-red-500 text-white"}`}>
          {toast.type === "success" ? <CheckCircle size={16} /> : <XCircle size={16} />}
          {toast.msg}
        </div>
      )}

      {modal.open && (
        <TemplateModal
          initial={modal.initial}
          isB2B={tab === "b2b"}
          onClose={() => setModal({ open: false })}
          onSave={handleSave}
          saving={saving}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Email Templates</h1>
          <p className="text-gray-500 text-sm mt-1">AI uses these as a base and rewrites to sound human and personalised</p>
        </div>
        <button onClick={() => setModal({ open: true })}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm font-medium">
          <Plus size={14} /> New Template
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {(["b2b", "job"] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${tab === t ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"}`}>
            {t === "b2b" ? "B2B Outreach" : "Job Applications"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3 animate-pulse">{[...Array(4)].map((_, i) => <div key={i} className="h-16 bg-gray-100 rounded-2xl" />)}</div>
      ) : tab === "b2b" ? (
        /* ── B2B — grouped by industry → then by type ── */
        <div className="space-y-8">
          {allIndustries.map(industry => {
            const industryKey = industry === "Generic (fallback for all industries)" ? null : industry;
            const industryTemplates = b2bTemplates.filter(t =>
              (t.industry ?? null) === industryKey
            );
            const isGeneric = industry === "Generic (fallback for all industries)";

            return (
              <div key={industry}>
                {/* Industry heading */}
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isGeneric ? "bg-gray-400" : "bg-blue-500"}`} />
                  <h2 className="font-semibold text-gray-800">{industry}</h2>
                  {isGeneric && (
                    <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                      Used when no industry-specific template exists
                    </span>
                  )}
                  <button
                    onClick={() => setModal({ open: true, initial: { ...EMPTY_FORM, industry } })}
                    className="ml-auto flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 border border-blue-200 bg-blue-50 hover:bg-blue-100 px-2.5 py-1 rounded-lg transition-colors">
                    <Plus size={11} /> Add for {isGeneric ? "Generic" : industry.split(" /")[0]}
                  </button>
                </div>

                {/* Types within this industry */}
                <div className="space-y-4 pl-5">
                  {B2B_TYPES.map(({ value: tType, label: tLabel }) => {
                    const typeTemplates = industryTemplates.filter(t => t.template_type === tType);
                    return (
                      <div key={tType}>
                        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">{tLabel}</p>
                        <div className="space-y-2">
                          {typeTemplates.map(t => (
                            <TemplateCard
                              key={t.id} t={t}
                              onEdit={() => setModal({ open: true, initial: { ...t, industry: t.industry ?? "Generic (fallback for all industries)" } })}
                              onDelete={() => { if (confirm(`Delete "${t.name}"?`)) deleteMut.mutate(t.id); }}
                              onToggle={() => updateMut.mutate({ id: t.id, data: { is_active: !t.is_active } })}
                              onToggleDefault={() => updateMut.mutate({ id: t.id, data: { is_default: true } })}
                            />
                          ))}
                          {typeTemplates.length === 0 && (
                            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 rounded-xl border border-dashed border-gray-200">
                              <span className="text-xs text-gray-400">No template — {isGeneric ? "AI uses built-in default" : "will fall back to Generic template"}</span>
                              <button
                                onClick={() => setModal({ open: true, initial: { ...EMPTY_FORM, industry, template_type: tType } })}
                                className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                                <Plus size={10} /> Add
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── Job Applications — grouped by type only ── */
        <div className="space-y-6">
          {JOB_TYPES.map(({ value: tType, label: tLabel }) => {
            const typeTemplates = jobTemplates.filter(t => t.template_type === tType);
            return (
              <div key={tType}>
                <p className="text-sm font-semibold text-gray-700 mb-2">{tLabel}</p>
                <div className="space-y-2">
                  {typeTemplates.map(t => (
                    <TemplateCard
                      key={t.id} t={t}
                      onEdit={() => setModal({ open: true, initial: t })}
                      onDelete={() => { if (confirm(`Delete "${t.name}"?`)) deleteMut.mutate(t.id); }}
                      onToggle={() => updateMut.mutate({ id: t.id, data: { is_active: !t.is_active } })}
                      onToggleDefault={() => updateMut.mutate({ id: t.id, data: { is_default: true } })}
                    />
                  ))}
                  {typeTemplates.length === 0 && (
                    <div className="px-4 py-3 bg-gray-50 rounded-xl border border-dashed border-gray-200 text-xs text-gray-400">
                      No template — AI uses built-in default style
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
