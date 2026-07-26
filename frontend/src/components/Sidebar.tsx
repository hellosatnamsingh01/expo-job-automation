"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getMe, getUnreadAlertCount } from "@/lib/api";
import {
  LayoutDashboard, Users, Briefcase, Globe, Mail, FileText,
  Settings, BarChart2, CheckSquare, LogOut, Target, ChevronRight, Zap, Activity, Bell
} from "lucide-react";

const ALL_NAV = [
  { href: "/dashboard",                label: "Overview",       icon: LayoutDashboard, exact: true, roles: ["super_admin", "manager", "outreach_specialist", "researcher"] },
  { href: "/dashboard/jobs",           label: "Jobs",           icon: Briefcase,                    roles: ["super_admin", "manager", "outreach_specialist", "researcher"] },
  { href: "/dashboard/activities",     label: "Activities",     icon: Activity,                     roles: ["super_admin", "manager", "outreach_specialist", "researcher"] },
  { href: "/dashboard/applications",   label: "Applications",   icon: CheckSquare,                  roles: ["super_admin", "manager", "outreach_specialist"] },
  { href: "/dashboard/leads",          label: "B2B Leads",      icon: Target,                       roles: ["super_admin", "manager", "outreach_specialist"] },
  { href: "/dashboard/approvals",      label: "Approval Queue", icon: Mail,                         roles: ["super_admin", "manager"] },
  { href: "/dashboard/alerts",         label: "Alerts",         icon: Bell,                         roles: ["super_admin", "manager"] },
  { href: "/dashboard/profiles",       label: "Profiles",       icon: Users,                        roles: ["super_admin", "manager"] },
  { href: "/dashboard/platforms",      label: "Platforms",      icon: Globe,                        roles: ["super_admin", "manager"] },
  { href: "/dashboard/email-accounts", label: "Email Accounts", icon: Mail,                         roles: ["super_admin"] },
  { href: "/dashboard/templates",      label: "Templates",      icon: FileText,                     roles: ["super_admin", "manager"] },
  { href: "/dashboard/analytics",      label: "Analytics",      icon: BarChart2,                    roles: ["super_admin", "manager"] },
  { href: "/dashboard/users",          label: "Team",           icon: Users,                        roles: ["super_admin"] },
  { href: "/dashboard/settings",       label: "Settings",       icon: Settings,                     roles: ["super_admin"] },
];

const ROLE_LABELS: Record<string, string> = {
  super_admin:         "Super Admin",
  manager:             "Manager",
  outreach_specialist: "Outreach Specialist",
  researcher:          "Researcher",
};

export default function Sidebar() {
  const pathname = usePathname();
  const [user, setUser] = useState<{ email: string; full_name: string; role: string } | null>(null);
  const [unreadAlerts, setUnreadAlerts] = useState(0);

  useEffect(() => {
    getMe().then(setUser).catch(() => {});
  }, []);

  useEffect(() => {
    const fetchCount = () => getUnreadAlertCount().then((d: any) => setUnreadAlerts(d.count || 0)).catch(() => {});
    fetchCount();
    const interval = setInterval(fetchCount, 60_000);
    return () => clearInterval(interval);
  }, []);

  const role = user?.role || "researcher";
  const nav = ALL_NAV.filter(item => item.roles.includes(role));

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/login";
  };

  const initials = user?.full_name
    ? user.full_name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2)
    : "?";

  return (
    <aside className="w-64 h-screen bg-gray-950 flex flex-col fixed left-0 top-0 z-40">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center flex-shrink-0">
            <Zap size={14} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">EXPANDIMO</h1>
            <p className="text-[10px] text-gray-500 font-medium tracking-widest uppercase">Outreach Engine</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest px-3 mb-2">Navigation</p>
        {nav.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          const isAlerts = href === "/dashboard/alerts";
          return (
            <Link
              key={href}
              href={href}
              className={`group flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 ${
                active
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                  : "text-gray-400 hover:bg-gray-800 hover:text-white"
              }`}
            >
              <Icon size={15} className={active ? "text-white" : "text-gray-500 group-hover:text-gray-300"} />
              <span className="flex-1">{label}</span>
              {isAlerts && unreadAlerts > 0 && (
                <span className="text-[10px] font-bold bg-red-500 text-white rounded-full px-1.5 py-0.5 min-w-[18px] text-center leading-none">
                  {unreadAlerts > 99 ? "99+" : unreadAlerts}
                </span>
              )}
              {active && !isAlerts && <ChevronRight size={12} className="text-blue-300" />}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="px-3 py-4 border-t border-gray-800 space-y-2">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-white truncate">{ROLE_LABELS[role] || role}</p>
            <p className="text-[10px] text-gray-500 truncate">{user?.email || "..."}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 hover:bg-gray-800 hover:text-red-400 w-full transition-colors"
        >
          <LogOut size={14} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
