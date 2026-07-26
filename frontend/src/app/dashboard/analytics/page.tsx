"use client";
import { useQuery } from "@tanstack/react-query";
import { getOverview, getByProfile, getByCountry } from "@/lib/api";

export default function AnalyticsPage() {
  const { data: overview } = useQuery({ queryKey: ["overview"], queryFn: getOverview });
  const { data: byProfile = [] } = useQuery({ queryKey: ["by-profile"], queryFn: getByProfile });
  const { data: byCountry = [] } = useQuery({ queryKey: ["by-country"], queryFn: getByCountry });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        <p className="text-gray-500 text-sm mt-1">Performance breakdown across profiles and countries</p>
      </div>

      {/* By Profile */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-semibold text-gray-900 mb-4">Performance by Profile</h2>
        {byProfile.length === 0 ? (
          <p className="text-gray-400 text-sm">No data yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-2 text-xs text-gray-500 font-semibold uppercase">Profile</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Applied</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Opened</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Replied</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Open Rate</th>
                <th className="text-right py-2 text-xs text-gray-500 font-semibold uppercase">Reply Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {byProfile.map((row: any) => (
                <tr key={row.profile_id}>
                  <td className="py-3 text-gray-600 font-mono text-xs">{row.profile_id.slice(0, 8)}…</td>
                  <td className="py-3 text-right text-gray-900 font-medium">{row.total}</td>
                  <td className="py-3 text-right text-gray-600">{row.opened}</td>
                  <td className="py-3 text-right text-gray-600">{row.replied}</td>
                  <td className="py-3 text-right">
                    <span className={`text-xs font-semibold ${row.open_rate >= 30 ? "text-green-600" : "text-gray-500"}`}>{row.open_rate}%</span>
                  </td>
                  <td className="py-3 text-right">
                    <span className={`text-xs font-semibold ${row.reply_rate >= 5 ? "text-green-600" : "text-gray-500"}`}>{row.reply_rate}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* By Country */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-semibold text-gray-900 mb-4">Performance by Country</h2>
        {byCountry.length === 0 ? (
          <p className="text-gray-400 text-sm">No data yet.</p>
        ) : (
          <div className="space-y-2">
            {byCountry.map((row: any) => {
              const replyRate = row.applications > 0 ? Math.round(row.replies / row.applications * 100) : 0;
              const barWidth = Math.min(100, (row.applications / (byCountry[0]?.applications || 1)) * 100);
              return (
                <div key={row.country} className="flex items-center gap-4">
                  <span className="text-sm text-gray-700 w-32 shrink-0">{row.country || "Unknown"}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${barWidth}%` }} />
                  </div>
                  <span className="text-xs text-gray-500 w-20 text-right shrink-0">
                    {row.applications} apps · {replyRate}% reply
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
