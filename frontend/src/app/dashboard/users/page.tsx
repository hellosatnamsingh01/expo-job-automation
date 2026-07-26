"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUsers, createUser, updateUser, deleteUser, getUserPermissions, setUserPermissions } from "@/lib/api";
import { useState } from "react";
import { ChevronDown, ChevronUp, Shield, Plus, Trash2, X, Eye, EyeOff } from "lucide-react";

const ROLES = ["super_admin", "manager", "outreach_specialist", "researcher"];
const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super Admin",
  manager: "Manager",
  outreach_specialist: "Outreach Specialist",
  researcher: "Researcher",
};

const EMPTY_FORM = { email: "", full_name: "", password: "", role: "researcher" };

export default function UsersPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({ queryKey: ["users"], queryFn: getUsers });
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [perms, setPerms] = useState<Record<string, Record<string, boolean>>>({});
  const [loadedPerms, setLoadedPerms] = useState<Record<string, boolean>>({});
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [showPassword, setShowPassword] = useState(false);
  const [createError, setCreateError] = useState("");

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowModal(false);
      setForm({ ...EMPTY_FORM });
      setCreateError("");
    },
    onError: (e: any) => {
      const detail = e?.response?.data?.detail;
      setCreateError(typeof detail === "string" ? detail : "Failed to create user");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateUser(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const permsMutation = useMutation({
    mutationFn: ({ id, permissions }: { id: string; permissions: Record<string, boolean> }) =>
      setUserPermissions(id, permissions),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const loadPerms = async (userId: string) => {
    if (loadedPerms[userId]) return;
    const data = await getUserPermissions(userId);
    const flat: Record<string, boolean> = {};
    for (const [key, val] of Object.entries(data.permissions as Record<string, { has: boolean }>)) {
      flat[key] = val.has;
    }
    setPerms(p => ({ ...p, [userId]: flat }));
    setLoadedPerms(l => ({ ...l, [userId]: true }));
  };

  const toggleExpand = async (userId: string) => {
    if (expandedUser === userId) {
      setExpandedUser(null);
    } else {
      setExpandedUser(userId);
      await loadPerms(userId);
    }
  };

  const handleCreate = () => {
    setCreateError("");
    if (!form.email || !form.full_name || !form.password) {
      setCreateError("Email, name and password are required");
      return;
    }
    createMutation.mutate(form);
  };

  if (isLoading) return <div className="text-gray-500">Loading...</div>;

  return (
    <div className="space-y-5">
      {/* Add Member Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-gray-900">Add Team Member</h2>
              <button onClick={() => { setShowModal(false); setCreateError(""); }} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Full Name</label>
                <input
                  type="text"
                  placeholder="e.g. John Smith"
                  value={form.full_name}
                  onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                <input
                  type="email"
                  placeholder="john@example.com"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Min. 6 characters"
                    value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button type="button" onClick={() => setShowPassword(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
                <select
                  value={form.role}
                  onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
              </div>

              {createError && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{createError}</p>
              )}
            </div>

            <div className="flex gap-2 mt-6">
              <button onClick={() => { setShowModal(false); setCreateError(""); }}
                className="flex-1 border border-gray-200 text-gray-700 py-2.5 rounded-xl text-sm hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleCreate} disabled={createMutation.isPending}
                className="flex-1 bg-blue-600 text-white py-2.5 rounded-xl text-sm hover:bg-blue-700 disabled:opacity-50 font-medium">
                {createMutation.isPending ? "Creating..." : "Add Member"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Team</h1>
          <p className="text-gray-500 text-sm mt-1">{(data as any[]).length} member{(data as any[]).length !== 1 ? "s" : ""}</p>
        </div>
        <button onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm hover:bg-blue-700 shadow-sm">
          <Plus size={14} /> Add Member
        </button>
      </div>

      {/* User list */}
      <div className="space-y-3">
        {(data as any[]).map((user: any) => (
          <div key={user.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-sm font-bold text-blue-600">
                  {user.full_name?.[0]?.toUpperCase() || "?"}
                </div>
                <div>
                  <p className="font-semibold text-gray-900 text-sm">{user.full_name}</p>
                  <p className="text-xs text-gray-500">{user.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={user.role}
                  onChange={e => updateMutation.mutate({ id: user.id, data: { role: e.target.value } })}
                  className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs bg-white"
                >
                  {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
                <label className="flex items-center gap-1.5 cursor-pointer select-none">
                  <input type="checkbox" checked={user.is_active}
                    onChange={e => updateMutation.mutate({ id: user.id, data: { is_active: e.target.checked } })} />
                  <span className="text-xs text-gray-600">Active</span>
                </label>
                <button onClick={() => toggleExpand(user.id)}
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700">
                  <Shield size={13} /> Permissions
                  {expandedUser === user.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                </button>
                <button
                  onClick={() => { if (confirm(`Delete ${user.full_name}?`)) deleteMutation.mutate(user.id); }}
                  className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {expandedUser === user.id && perms[user.id] && (
              <div className="border-t border-gray-100 p-4 bg-gray-50">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Permissions</p>
                <div className="grid grid-cols-3 gap-2 mb-4">
                  {Object.entries(perms[user.id]).map(([perm, has]) => (
                    <label key={perm} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={has}
                        onChange={e => setPerms(p => ({ ...p, [user.id]: { ...p[user.id], [perm]: e.target.checked } }))} />
                      <span className="text-xs text-gray-700">{perm.replace(/_/g, " ")}</span>
                    </label>
                  ))}
                </div>
                <button
                  onClick={() => permsMutation.mutate({ id: user.id, permissions: perms[user.id] })}
                  className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-xs hover:bg-blue-700">
                  Save Permissions
                </button>
              </div>
            )}
          </div>
        ))}
        {(data as any[]).length === 0 && (
          <div className="text-center py-16 text-gray-500 bg-white rounded-xl border border-gray-200">
            <p className="font-medium">No team members yet</p>
            <p className="text-xs mt-1">Click "Add Member" to invite someone</p>
          </div>
        )}
      </div>
    </div>
  );
}
