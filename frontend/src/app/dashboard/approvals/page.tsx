"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPendingApproval, approveApplication, approveLead } from "@/lib/api";
import { CheckCircle, XCircle, Mail, ChevronDown, ChevronUp, Clock, User, Building2 } from "lucide-react";
import { useState } from "react";

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ["pending-approvals"], queryFn: getPendingApproval });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: ({ id, action, reason, itemType }: { id: string; action: string; reason?: string; itemType: string }) =>
      itemType === "b2b" ? approveLead(id, action) : approveApplication(id, action, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pending-approvals"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["leads"] });
      setRejecting(null); setReason("");
    },
  });

  if (isLoading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-8 bg-gray-200 rounded w-56" />
      {[...Array(3)].map((_, i) => <div key={i} className="h-28 bg-gray-100 rounded-2xl" />)}
    </div>
  );

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center">
          <Mail size={18} className="text-amber-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Approval Queue</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {(data as any[]).length} email{(data as any[]).length !== 1 ? "s" : ""} waiting for review
          </p>
        </div>
      </div>

      {(data as any[]).length === 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
          <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto mb-4">
            <CheckCircle size={26} className="text-emerald-500" />
          </div>
          <p className="text-gray-700 font-semibold text-lg">All caught up!</p>
          <p className="text-gray-400 text-sm mt-1">No emails are waiting for approval right now.</p>
        </div>
      )}

      <div className="space-y-4">
        {(data as any[]).map((app: any) => {
          const isOpen = expanded === app.id;
          const isRejecting = rejecting === app.id;
          const isB2B = app.type === "b2b";
          const type = isB2B ? "B2B Outreach" : "Job Application";
          const typeColor = isB2B ? "bg-violet-100 text-violet-700" : "bg-blue-100 text-blue-700";

          return (
            <div key={app.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
              <div className="p-5">
                <div className="flex items-start gap-4">
                  {/* Icon */}
                  <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Mail size={15} className="text-amber-600" />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${typeColor}`}>{type}</span>
                      {isB2B && app.industry && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{app.industry}</span>
                      )}
                      {isB2B && app.score && (
                        <span className="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-medium">Score {app.score}</span>
                      )}
                      <span className="flex items-center gap-1 text-xs text-gray-400">
                        <Clock size={10} />
                        {app.scheduled_at ? new Date(app.scheduled_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "Send ASAP"}
                      </span>
                    </div>
                    <p className="font-semibold text-gray-900 text-sm">{app.subject}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      {isB2B ? <Building2 size={11} className="text-gray-400" /> : <User size={11} className="text-gray-400" />}
                      <p className="text-xs text-gray-500">
                        {isB2B ? (
                          <><span className="font-medium">{app.company_name}</span>{app.to_name ? ` · ${app.to_name}` : ""} <span className="text-gray-400">&lt;{app.to_email}&gt;</span></>
                        ) : (
                          <>{app.to_name ? `${app.to_name}` : ""} <span className="text-gray-400">&lt;{app.to_email}&gt;</span></>
                        )}
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => setExpanded(isOpen ? null : app.id)}
                      className="flex items-center gap-1.5 text-xs border border-gray-200 text-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {isOpen ? "Hide" : "Preview"}
                    </button>
                    <button
                      onClick={() => mutation.mutate({ id: app.id, action: "approve", itemType: app.type })}
                      disabled={mutation.isPending}
                      className="flex items-center gap-1.5 text-xs bg-emerald-600 text-white px-3 py-1.5 rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50 shadow-sm"
                    >
                      <CheckCircle size={12} /> Approve
                    </button>
                    <button
                      onClick={() => setRejecting(isRejecting ? null : app.id)}
                      className="flex items-center gap-1.5 text-xs bg-red-50 text-red-600 border border-red-200 px-3 py-1.5 rounded-lg hover:bg-red-100 transition-colors"
                    >
                      <XCircle size={12} /> Reject
                    </button>
                  </div>
                </div>

                {isRejecting && (
                  <div className="mt-4 space-y-2 pl-13">
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Optional: reason for rejection (e.g. wrong tone, wrong contact)"
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-300"
                      rows={2}
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => mutation.mutate({ id: app.id, action: "reject", reason, itemType: app.type })}
                        className="text-xs bg-red-600 text-white px-3 py-1.5 rounded-lg hover:bg-red-700 shadow-sm"
                      >Confirm Reject</button>
                      <button onClick={() => setRejecting(null)} className="text-xs border border-gray-200 px-3 py-1.5 rounded-lg hover:bg-gray-50">Cancel</button>
                    </div>
                  </div>
                )}
              </div>

              {isOpen && (
                <div className="border-t border-gray-100 bg-gray-50 p-5">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Email Preview</p>
                  <div className="bg-white rounded-xl border border-gray-200 p-4">
                    <p className="text-xs text-gray-500 mb-1"><span className="font-semibold">Subject:</span> {app.subject}</p>
                    <p className="text-xs text-gray-400 border-b border-gray-100 pb-2 mb-3"><span className="font-semibold">To:</span> {app.to_name} &lt;{app.to_email}&gt;</p>
                    <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{app.body || "No email body."}</pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
