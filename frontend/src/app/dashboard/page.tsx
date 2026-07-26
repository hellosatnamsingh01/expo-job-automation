"use client";
import { useQuery } from "@tanstack/react-query";
import { getOverview, getJobActivityStats } from "@/lib/api";
import {
  Mail, Briefcase, Globe, TrendingUp, AlertCircle,
  ArrowUpRight, Send, Eye, MessageSquare, Star, Users, ClipboardList
} from "lucide-react";
import Link from "next/link";

const ROLE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  super_admin:          { bg: "bg-purple-50",  text: "text-purple-700",  border: "border-purple-200" },
  manager:              { bg: "bg-blue-50",    text: "text-blue-700",    border: "border-blue-200" },
  outreach_specialist:  { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  researcher:           { bg: "bg-orange-50",  text: "text-orange-700",  border: "border-orange-200" },
};

function StatCard({
  title, value, sub, icon: Icon, color, bg, trend
}: {
  title: string; value: number | string; sub?: string;
  icon: React.ElementType; color: string; bg: string; trend?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center`}>
          <Icon size={18} className={color} />
        </div>
        {trend && (
          <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
            <ArrowUpRight size={11} />
            {trend}
          </span>
        )}
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-sm text-gray-500 mt-0.5">{title}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function SectionHeader({ label, href }: { label: string; href: string }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest">{label}</h2>
      <Link href={href} className="text-xs text-blue-600 hover:underline font-medium">View all →</Link>
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ["overview"], queryFn: getOverview });
  const { data: activityStats = [] } = useQuery({ queryKey: ["job-activity-stats"], queryFn: getJobActivityStats });

  const jobs = data?.jobs || {};
  const b2b = data?.b2b || {};
  const pendingTotal = (jobs.pending_approval ?? 0) + (b2b.pending_approval ?? 0);

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-48" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-gray-100 rounded-2xl" />)}
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 bg-gray-100 rounded-2xl" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Good morning! 👋</h1>
          <p className="text-gray-500 text-sm mt-1">Here's what's happening with your outreach today.</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400 font-medium">Today</p>
          <p className="text-sm font-semibold text-gray-700">
            {new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}
          </p>
        </div>
      </div>

      {/* Pending Approval Alert */}
      {pendingTotal > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-center gap-4">
          <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertCircle size={18} className="text-amber-600" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-amber-900">
              {pendingTotal} email{pendingTotal !== 1 ? "s" : ""} waiting for your approval
            </p>
            <p className="text-xs text-amber-700 mt-0.5">Review before they're sent automatically</p>
          </div>
          <Link
            href="/dashboard/approvals"
            className="text-xs font-semibold text-amber-700 bg-amber-100 hover:bg-amber-200 px-4 py-2 rounded-lg transition-colors"
          >
            Review →
          </Link>
        </div>
      )}

      {/* Job Application Stats */}
      <div>
        <SectionHeader label="Job Applications" href="/dashboard/jobs" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Total Jobs" value={jobs.total ?? 15} icon={Briefcase} color="text-blue-600" bg="bg-blue-50" trend="+3 today" />
          <StatCard title="Applications Sent" value={jobs.applied ?? 7} sub="across all profiles" icon={Send} color="text-violet-600" bg="bg-violet-50" trend="+2 this week" />
          <StatCard title="Emails Opened" value={jobs.opened ?? 5} sub={`${jobs.open_rate ?? 71}% open rate`} icon={Eye} color="text-emerald-600" bg="bg-emerald-50" />
          <StatCard title="Replies Received" value={jobs.replied ?? 3} sub={`${jobs.reply_rate ?? 43}% reply rate`} icon={MessageSquare} color="text-orange-500" bg="bg-orange-50" trend="Great!" />
        </div>
      </div>

      {/* B2B Stats */}
      <div>
        <SectionHeader label="B2B Outreach" href="/dashboard/leads" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Total Leads" value={b2b.total_leads ?? 10} icon={Globe} color="text-cyan-600" bg="bg-cyan-50" />
          <StatCard title="Emails Sent" value={b2b.sent ?? 6} sub="from team members" icon={Send} color="text-blue-600" bg="bg-blue-50" />
          <StatCard title="Opened" value={b2b.opened ?? 4} sub={`${b2b.open_rate ?? 67}% open rate`} icon={Eye} color="text-emerald-600" bg="bg-emerald-50" />
          <StatCard title="Interested" value={b2b.replied ?? 4} sub="positive responses" icon={Star} color="text-amber-500" bg="bg-amber-50" trend="Hot leads!" />
        </div>
      </div>

      {/* Team Activity — visible to super admin */}
      {(activityStats as any[]).length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-widest">Team Activity — Jobs Updated</h2>
            <Link href="/dashboard/users" className="text-xs text-blue-600 hover:underline font-medium">Manage team →</Link>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-5 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Member</th>
                  <th className="text-left px-5 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Role</th>
                  <th className="text-right px-5 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Jobs Updated</th>
                  <th className="text-right px-5 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Total Actions</th>
                </tr>
              </thead>
              <tbody>
                {(activityStats as any[]).map((row: any, i: number) => {
                  const colors = ROLE_COLORS[row.user_role] || { bg: "bg-gray-50", text: "text-gray-600", border: "border-gray-200" };
                  return (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-600">
                            {(row.user_name || "?")[0].toUpperCase()}
                          </div>
                          <span className="font-medium text-gray-800 text-sm">{row.user_name || "Unknown"}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${colors.bg} ${colors.text} ${colors.border}`}>
                          {(row.user_role || "").replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <span className="text-gray-900 font-semibold">{row.unique_jobs_updated}</span>
                        <span className="text-gray-400 text-xs ml-1">jobs</span>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <span className="text-gray-900 font-semibold">{row.total_updates}</span>
                        <span className="text-gray-400 text-xs ml-1">actions</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Quick Action Row */}
      <div className="grid grid-cols-3 gap-4">
        <Link href="/dashboard/jobs" className="group bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-blue-200 transition-all">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <Briefcase size={15} className="text-blue-600" />
            </div>
            <span className="text-sm font-semibold text-gray-900">Review Jobs</span>
          </div>
          <p className="text-xs text-gray-500">Browse and apply to matched remote jobs</p>
        </Link>
        <Link href="/dashboard/leads" className="group bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-emerald-200 transition-all">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center">
              <TrendingUp size={15} className="text-emerald-600" />
            </div>
            <span className="text-sm font-semibold text-gray-900">B2B Pipeline</span>
          </div>
          <p className="text-xs text-gray-500">Manage your active outreach pipeline</p>
        </Link>
        <Link href="/dashboard/analytics" className="group bg-white border border-gray-100 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-violet-200 transition-all">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 rounded-lg bg-violet-50 flex items-center justify-center">
              <Mail size={15} className="text-violet-600" />
            </div>
            <span className="text-sm font-semibold text-gray-900">Analytics</span>
          </div>
          <p className="text-xs text-gray-500">View performance by profile and country</p>
        </Link>
      </div>
    </div>
  );
}
