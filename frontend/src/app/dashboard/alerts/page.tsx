"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getAlerts, dismissAlert, dismissAllAlerts, markAllAlertsRead } from "@/lib/api";
import {
  Bell, AlertTriangle, AlertCircle, Info, CheckCircle2,
  Key, Globe, Mail, MessageSquare, Users, RefreshCw, Trash2, X
} from "lucide-react";
import { useState } from "react";

const TYPE_META: Record<string, { label: string; icon: any; color: string }> = {
  key_exhausted:      { label: "Key Exhausted",       icon: Key,            color: "text-orange-500" },
  key_rotated:        { label: "Key Rotated",          icon: RefreshCw,      color: "text-blue-500" },
  key_renewed:        { label: "Key Renewed",          icon: RefreshCw,      color: "text-emerald-500" },
  key_error:          { label: "Key Error",            icon: Key,            color: "text-red-500" },
  platform_error:     { label: "Platform Error",       icon: Globe,          color: "text-red-500" },
  platform_ok:        { label: "Platform Scraped",     icon: Globe,          color: "text-green-500" },
  email_disconnected: { label: "Email Disconnected",   icon: Mail,           color: "text-red-500" },
  email_error:        { label: "Email Error",          icon: Mail,           color: "text-orange-500" },
  reply_received:     { label: "Reply Received",       icon: MessageSquare,  color: "text-emerald-500" },
  b2b_reply:          { label: "B2B Reply",            icon: MessageSquare,  color: "text-emerald-500" },
  lead_imported:      { label: "Leads Imported",       icon: Users,          color: "text-blue-500" },
  enrich_done:        { label: "Enrichment Complete",  icon: CheckCircle2,   color: "text-green-500" },
  system:             { label: "System",               icon: Info,           color: "text-gray-400" },
};

const SEVERITY_META: Record<string, { bg: string; border: string; badge: string }> = {
  error:   { bg: "bg-red-50",    border: "border-red-100",    badge: "bg-red-100 text-red-700" },
  warning: { bg: "bg-orange-50", border: "border-orange-100", badge: "bg-orange-100 text-orange-700" },
  info:    { bg: "bg-white",     border: "border-gray-100",   badge: "bg-gray-100 text-gray-600" },
};

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === "error")   return <AlertCircle size={14} className="text-red-500 flex-shrink-0 mt-0.5" />;
  if (severity === "warning") return <AlertTriangle size={14} className="text-orange-500 flex-shrink-0 mt-0.5" />;
  return <Info size={14} className="text-blue-400 flex-shrink-0 mt-0.5" />;
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

type FilterType = "all" | "error" | "warning" | "info";

export default function AlertsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<FilterType>("all");

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: getAlerts,
    refetchInterval: 30_000,
  });

  // Mark all alerts as read when the page is opened
  useEffect(() => {
    markAllAlertsRead().then(() => {
      qc.invalidateQueries({ queryKey: ["alert-count"] });
    });
  }, []);

  const dismiss = useMutation({
    mutationFn: (id: string) => dismissAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const dismissAll = useMutation({
    mutationFn: dismissAllAlerts,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-count"] });
    },
  });

  const filtered = alerts.filter((a: any) => {
    if (filter === "error")   return a.severity === "error";
    if (filter === "warning") return a.severity === "warning";
    if (filter === "info")    return a.severity === "info";
    return true;
  });

  const totalCount = alerts.length;
  const errorCount = alerts.filter((a: any) => a.severity === "error").length;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow">
            <Bell size={16} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Alerts</h1>
            <p className="text-xs text-gray-400">
              {totalCount > 0
                ? `${totalCount} alert${totalCount > 1 ? "s" : ""}${errorCount > 0 ? ` · ${errorCount} error${errorCount > 1 ? "s" : ""} need attention` : ""}`
                : "No alerts — everything looks good"}
            </p>
          </div>
        </div>
        {totalCount > 0 && (
          <button
            onClick={() => dismissAll.mutate()}
            disabled={dismissAll.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
          >
            <Trash2 size={12} />
            Clear all
          </button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-4 bg-gray-100 p-1 rounded-xl w-fit">
        {(["all", "error", "warning", "info"] as FilterType[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors capitalize ${
              filter === f ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f === "error" && errorCount > 0 && (
              <span className="ml-1 bg-red-500 text-white text-[9px] font-bold rounded-full px-1">{errorCount}</span>
            )}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="text-center py-20 text-gray-400 text-sm">Loading alerts…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20">
          <Bell size={36} className="text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">No {filter !== "all" ? `"${filter}" ` : ""}alerts</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((alert: any) => {
            const meta    = TYPE_META[alert.type]   || TYPE_META.system;
            const sevMeta = SEVERITY_META[alert.severity] || SEVERITY_META.info;
            const Icon    = meta.icon;
            return (
              <div
                key={alert.id}
                className={`flex gap-3 p-4 rounded-xl border shadow-sm ${sevMeta.bg} ${sevMeta.border}`}
              >
                {/* Type icon */}
                <div className={`mt-0.5 flex-shrink-0 ${meta.color}`}>
                  <Icon size={16} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${sevMeta.badge}`}>
                        {alert.severity.toUpperCase()}
                      </span>
                      {alert.source && (
                        <span className="text-[10px] font-medium text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-md">
                          {alert.source}
                        </span>
                      )}
                      <span className="text-[10px] text-gray-400">{timeAgo(alert.created_at)}</span>
                    </div>
                    <button
                      onClick={() => dismiss.mutate(alert.id)}
                      title="Dismiss"
                      className="text-gray-300 hover:text-red-400 flex-shrink-0 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <p className="text-sm font-semibold text-gray-800 mt-1">{alert.title}</p>
                  {alert.message && (
                    <p className="text-xs text-gray-500 mt-0.5 whitespace-pre-line">{alert.message}</p>
                  )}
                </div>

                {/* Severity icon */}
                <SeverityIcon severity={alert.severity} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
