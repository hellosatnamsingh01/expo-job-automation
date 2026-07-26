"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getActivities, getSettings, updateSettings } from "@/lib/api";
import {
  Activity, Mail, RefreshCw, Clock, CheckCircle2, Eye, Reply,
  Send, AlarmClock, XCircle, ChevronDown, ChevronUp, Settings2
} from "lucide-react";
import { useState } from "react";

function fmt(dt: string | null | undefined) {
  if (!dt) return null;
  return new Date(dt).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "2-digit",
    hour: "numeric", minute: "2-digit", hour12: true,
  });
}

function relTime(dt: string | null | undefined) {
  if (!dt) return null;
  const diff = Date.now() - new Date(dt).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const STATUS_META: Record<string, { icon: any; color: string; label: string }> = {
  sent:             { icon: Send,        color: "text-blue-600 bg-blue-50 border-blue-200",    label: "Sent" },
  opened:           { icon: Eye,         color: "text-violet-600 bg-violet-50 border-violet-200", label: "Opened" },
  replied:          { icon: Reply,       color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "Replied" },
  pending_approval: { icon: Clock,       color: "text-amber-600 bg-amber-50 border-amber-200", label: "Pending" },
  scheduled:        { icon: AlarmClock,  color: "text-cyan-600 bg-cyan-50 border-cyan-200",    label: "Scheduled" },
  rejected:         { icon: XCircle,     color: "text-red-500 bg-red-50 border-red-200",       label: "Rejected" },
  pending:          { icon: AlarmClock,  color: "text-cyan-600 bg-cyan-50 border-cyan-200",    label: "Scheduled" },
};

function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] || { icon: Activity, color: "text-gray-500 bg-gray-50 border-gray-200", label: status };
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${m.color}`}>
      <Icon size={10} />{m.label}
    </span>
  );
}

function ScheduleSettings() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [saving, setSaving] = useState(false);

  const s = settings as any;
  const curStart = s?.send_time_start || "09:00";
  const curEnd   = s?.send_time_end   || "11:00";

  const openEdit = () => { setStart(curStart); setEnd(curEnd); setEditing(true); };
  const save = async () => {
    setSaving(true);
    try { await updateSettings({ send_time_start: start, send_time_end: end }); qc.invalidateQueries({ queryKey: ["settings"] }); setEditing(false); }
    finally { setSaving(false); }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center">
            <Clock size={15} className="text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">Email Send Window</h3>
            <p className="text-xs text-gray-400">Emails go out during this time window</p>
          </div>
        </div>
        <button onClick={editing ? () => setEditing(false) : openEdit}
          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
          <Settings2 size={15} />
        </button>
      </div>

      {!editing ? (
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-50 rounded-xl px-4 py-3 text-center">
            <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide mb-0.5">Start</p>
            <p className="text-xl font-bold text-gray-900">{curStart}</p>
          </div>
          <div className="text-gray-300 font-light text-lg">→</div>
          <div className="flex-1 bg-gray-50 rounded-xl px-4 py-3 text-center">
            <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide mb-0.5">End</p>
            <p className="text-xl font-bold text-gray-900">{curEnd}</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide block mb-1">Start Time</label>
              <input type="time" value={start} onChange={e => setStart(e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div className="flex-1">
              <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide block mb-1">End Time</label>
              <input type="time" value={end} onChange={e => setEnd(e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={save} disabled={saving}
              className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
            <button onClick={() => setEditing(false)}
              className="flex-1 border border-gray-200 text-gray-600 py-2 rounded-xl text-sm font-medium hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ActivityCard({ event }: { event: any }) {
  const [expanded, setExpanded] = useState(false);
  const isFollowup = event.type === "followup";

  const time = event.sent_at || event.created_at;
  const isScheduled = !event.sent_at && event.scheduled_at;

  return (
    <div className={`bg-white rounded-xl border shadow-sm overflow-hidden transition-all ${
      isFollowup ? "border-orange-100 ml-8" : "border-gray-100"
    }`}>
      <div className="p-4 flex items-start gap-3">
        {/* Timeline dot */}
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 ${
          isFollowup ? "bg-orange-50" : "bg-blue-50"
        }`}>
          {isFollowup
            ? <RefreshCw size={14} className="text-orange-500" />
            : <Mail size={14} className="text-blue-600" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {isFollowup && (
                  <span className="text-[10px] font-bold text-orange-600 bg-orange-50 border border-orange-200 px-1.5 py-0.5 rounded-full">
                    FOLLOW-UP #{event.followup_number}
                  </span>
                )}
                <StatusBadge status={event.status} />
                {event.email_opened && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border text-violet-600 bg-violet-50 border-violet-200">
                    <Eye size={9} /> Opened
                  </span>
                )}
              </div>
              <p className="font-semibold text-gray-900 text-sm mt-1 truncate">
                {event.job_title || "Unknown Job"}{event.company_name ? ` · ${event.company_name}` : ""}
              </p>
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                {isScheduled ? "📅 Scheduled" : "📤 Sent"} to <span className="font-medium text-gray-700">{event.to_email}</span>
                {event.to_name ? ` (${event.to_name})` : ""}
                {event.profile_name ? <> · <span className="text-blue-600 font-medium">{event.profile_name}</span></> : null}
              </p>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-[11px] text-gray-400 font-medium">
                {isScheduled ? fmt(event.scheduled_at) : fmt(time)}
              </p>
              {!isScheduled && time && (
                <p className="text-[10px] text-gray-300 mt-0.5">{relTime(time)}</p>
              )}
            </div>
          </div>

          {/* Subject */}
          <p className="text-xs text-gray-500 mt-1.5 italic truncate">
            ✉ {event.subject}
          </p>

          {/* Expand body */}
          {event.body && (
            <button onClick={() => setExpanded(e => !e)}
              className="flex items-center gap-1 text-[10px] text-blue-500 hover:text-blue-700 mt-1.5 font-medium">
              {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              {expanded ? "Hide email body" : "Preview email body"}
            </button>
          )}
          {expanded && event.body && (
            <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-100 text-xs text-gray-600 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
              {event.body.replace(/<[^>]+>/g, "")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ActivitiesPage() {
  const { data = [], isLoading, refetch } = useQuery({
    queryKey: ["activities"],
    queryFn: () => getActivities({ limit: 200 }),
    refetchInterval: 30000,
  });

  const events = data as any[];
  const sent      = events.filter(e => e.status === "sent" || e.status === "opened" || e.status === "replied").length;
  const scheduled = events.filter(e => e.status === "scheduled" || (e.status === "pending" && !e.sent_at)).length;
  const opened    = events.filter(e => e.email_opened).length;
  const replies   = events.filter(e => e.status === "replied" || e.replied_at).length;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Activities</h1>
          <p className="text-gray-500 text-sm mt-1">Timeline of all emails sent, scheduled, and follow-ups</p>
        </div>
        <button onClick={() => refetch()}
          className="flex items-center gap-2 border border-gray-200 text-gray-600 px-4 py-2 rounded-xl text-sm hover:bg-gray-50 font-medium">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Emails Sent",    value: sent,      color: "text-blue-600",    bg: "bg-blue-50"    },
            { label: "Scheduled",      value: scheduled, color: "text-cyan-600",    bg: "bg-cyan-50"    },
            { label: "Opened",         value: opened,    color: "text-violet-600",  bg: "bg-violet-50"  },
            { label: "Replied",        value: replies,   color: "text-emerald-600", bg: "bg-emerald-50" },
          ].map(s => (
            <div key={s.label} className={`rounded-2xl ${s.bg} border border-white shadow-sm p-4 text-center`}>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-500 font-medium mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Schedule Settings */}
        <ScheduleSettings />
      </div>

      {/* Timeline */}
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Email Timeline</h2>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-100 p-16 text-center">
            <Activity size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-600 font-semibold">No activity yet</p>
            <p className="text-gray-400 text-sm mt-1">
              Apply for a job to see email activity here
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {events.map(event => (
              <ActivityCard key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
