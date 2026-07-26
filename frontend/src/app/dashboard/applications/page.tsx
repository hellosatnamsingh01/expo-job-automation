"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getApplications, togglePin } from "@/lib/api";
import { Pin, PinOff, MessageSquare, ChevronDown, ChevronUp, Send, Eye, Clock } from "lucide-react";
import { useState } from "react";

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  draft:            { label: "Draft",        cls: "bg-gray-100 text-gray-600" },
  pending_approval: { label: "Pending",      cls: "bg-amber-100 text-amber-700" },
  approved:         { label: "Approved",     cls: "bg-cyan-100 text-cyan-700" },
  scheduled:        { label: "Scheduled",    cls: "bg-blue-100 text-blue-700" },
  sent:             { label: "Sent",         cls: "bg-violet-100 text-violet-700" },
  opened:           { label: "Opened",       cls: "bg-indigo-100 text-indigo-700" },
  replied:          { label: "Replied ✓",    cls: "bg-emerald-100 text-emerald-700" },
  follow_up_1:      { label: "Follow-up 1",  cls: "bg-orange-100 text-orange-700" },
  follow_up_2:      { label: "Follow-up 2",  cls: "bg-orange-100 text-orange-700" },
  follow_up_3:      { label: "Follow-up 3",  cls: "bg-red-100 text-red-700" },
  cold:             { label: "Cold",         cls: "bg-gray-100 text-gray-400" },
};

function fmt(dt: string) {
  return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ApplicationsPage() {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data = [], isLoading } = useQuery({ queryKey: ["applications"], queryFn: () => getApplications({ page_size: 500 }) });

  const pinMutation = useMutation({
    mutationFn: (id: string) => togglePin(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const replied = (data as any[]).filter((a: any) => a.replied_at).length;
  const opened = (data as any[]).filter((a: any) => a.email_opened).length;
  const sent = (data as any[]).filter((a: any) => a.status === "sent" || a.sent_at).length;

  if (isLoading) return (
    <div className="space-y-3 animate-pulse">
      {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-gray-100 rounded-2xl" />)}
    </div>
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Applications</h1>
        <p className="text-gray-500 text-sm mt-1">{(data as any[]).length} applications tracked</p>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center"><Send size={15} className="text-violet-600" /></div>
          <div><p className="text-xl font-bold text-gray-900">{sent}</p><p className="text-xs text-gray-500">Sent</p></div>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 flex items-center justify-center"><Eye size={15} className="text-indigo-600" /></div>
          <div><p className="text-xl font-bold text-gray-900">{opened}</p><p className="text-xs text-gray-500">Opened</p></div>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center"><MessageSquare size={15} className="text-emerald-600" /></div>
          <div><p className="text-xl font-bold text-gray-900">{replied}</p><p className="text-xs text-gray-500">Replied</p></div>
        </div>
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {(data as any[]).map((app: any) => {
          const cfg = STATUS_CONFIG[app.status] || { label: app.status, cls: "bg-gray-100 text-gray-600" };
          const isOpen = expanded === app.id;
          return (
            <div key={app.id} className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${
              app.is_pinned ? "border-amber-200" : "border-gray-100"
            }`}>
              <div className="p-5">
                <div className="flex items-start gap-4">
                  {/* Left icon */}
                  <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Send size={14} className="text-blue-600" />
                  </div>

                  {/* Main content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${cfg.cls}`}>{cfg.label}</span>
                      {app.email_opened && (
                        <span className="flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50 px-2 py-1 rounded-full font-medium">
                          <Eye size={10} /> Opened
                        </span>
                      )}
                      {app.replied_at && (
                        <span className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full font-medium">
                          <MessageSquare size={10} /> Replied
                        </span>
                      )}
                      {app.is_pinned && <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded-full font-medium">📌 Pinned</span>}
                    </div>

                    <p className="font-semibold text-gray-900 text-sm truncate">{app.subject}</p>
                    <div className="flex items-center gap-4 mt-1.5 flex-wrap">
                      <span className="text-xs text-gray-500">To: <span className="text-gray-700">{app.to_name || app.to_email}</span></span>
                      {app.sent_at && (
                        <span className="flex items-center gap-1 text-xs text-gray-400">
                          <Clock size={10} /> Sent {fmt(app.sent_at)}
                        </span>
                      )}
                      {app.follow_up_count > 0 && (
                        <span className="text-xs text-orange-600">↩ {app.follow_up_count} follow-up{app.follow_up_count !== 1 ? "s" : ""} sent</span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => pinMutation.mutate(app.id)}
                      className={`p-1.5 rounded-lg transition-colors ${app.is_pinned ? "text-amber-500 hover:bg-amber-50" : "text-gray-300 hover:text-amber-500 hover:bg-amber-50"}`}>
                      {app.is_pinned ? <PinOff size={14} /> : <Pin size={14} />}
                    </button>
                    <button onClick={() => setExpanded(isOpen ? null : app.id)}
                      className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
                      {isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                  </div>
                </div>
              </div>

              {isOpen && (
                <div className="border-t border-gray-100 bg-gray-50 p-5">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Email Preview</p>
                  <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{app.body || "No body saved."}</pre>
                  {app.followups?.length > 0 && (
                    <div className="mt-4 border-t border-gray-200 pt-4">
                      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Follow-ups</p>
                      <div className="space-y-1.5">
                        {app.followups.map((fu: any) => (
                          <div key={fu.id} className="flex items-center gap-3 text-xs">
                            <span className="font-semibold text-gray-600">Follow-up #{fu.number}</span>
                            <span className={`px-2 py-0.5 rounded-full font-medium ${fu.status === "sent" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
                              {fu.status}
                            </span>
                            {fu.scheduled_at && <span className="text-gray-400">{fmt(fu.scheduled_at)}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {(data as any[]).length === 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-16 text-center">
            <Send size={32} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No applications yet</p>
            <p className="text-gray-400 text-sm mt-1">Applications will appear here once jobs are applied to</p>
          </div>
        )}
      </div>
    </div>
  );
}
