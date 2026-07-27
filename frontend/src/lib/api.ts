import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://backend-production-22f6.up.railway.app/api/v1";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password }).then((r) => r.data);
export const getMe = () => api.get("/auth/me").then((r) => r.data);

// Profiles
export const getProfiles = () => api.get("/profiles/").then((r) => r.data);
export const createProfile = (data: any) => api.post("/profiles/", data).then((r) => r.data);
export const updateProfile = (id: string, data: any) => api.patch(`/profiles/${id}`, data).then((r) => r.data);
export const deleteProfile = (id: string) => api.delete(`/profiles/${id}`).then((r) => r.data);
export const uploadCV = (
  profileId: string,
  file: File,
  onProgress?: (pct: number) => void,
  region?: string | null
): Promise<any> => {
  const form = new FormData();
  form.append("file", file);
  if (region) form.append("region", region);
  const token = localStorage.getItem("token");
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/profiles/${profileId}/cv`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try { reject(new Error(JSON.parse(xhr.responseText).detail || "Upload failed")); }
        catch { reject(new Error("Upload failed")); }
      }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(form);
  });
};
export const deleteCv = (profileId: string, cvId: string) =>
  api.delete(`/profiles/${profileId}/cv/${cvId}`).then((r) => r.data);
export const downloadCv = (profileId: string, cvId: string, fileName: string) => {
  const token = localStorage.getItem("token");
  fetch(`${API_BASE}/profiles/${profileId}/cv/${cvId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
    .then((r) => r.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    });
};

export const uploadJobCV = (jobId: string, file: File, onProgress?: (pct: number) => void): Promise<any> => {
  const form = new FormData();
  form.append("file", file);
  const token = localStorage.getItem("token");
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/jobs/${jobId}/cv`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else { try { reject(new Error(JSON.parse(xhr.responseText).detail || "Upload failed")); } catch { reject(new Error("Upload failed")); } }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(form);
  });
};
export const deleteJobCV = (jobId: string) => api.delete(`/jobs/${jobId}/cv`).then((r) => r.data);

// Platforms
export const getPlatforms = () => api.get("/platforms/").then((r) => r.data);
export const createPlatform = (data: any) => api.post("/platforms/", data).then((r) => r.data);
export const updatePlatform = (id: string, data: any) => api.patch(`/platforms/${id}`, data).then((r) => r.data);
export const deletePlatform = (id: string) => api.delete(`/platforms/${id}`).then((r) => r.data);
export const triggerScrape = (id: string) => api.post(`/platforms/${id}/scrape`).then((r) => r.data);
export const triggerScrapeAll = () => api.post("/platforms/scrape-all").then((r) => r.data);

// Jobs
export const getJobs = (params?: any) => api.get("/jobs/", { params }).then((r) => r.data);
export const createJob = (data: any) => api.post("/jobs/", data).then((r) => r.data);
export const updateJob = (id: string, data: any) => api.patch(`/jobs/${id}`, data).then((r) => r.data);
export const uploadJobs = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/jobs/upload", form, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
};
export const deleteJob = (id: string) => api.delete(`/jobs/${id}`).then((r) => r.data);
export const bulkDeleteJobs = (ids: string[]) => api.delete("/jobs/bulk", { data: ids }).then((r) => r.data);
export const exportJobs = (ids?: string[]) => api.post("/jobs/export", ids && ids.length ? { ids } : {}, { responseType: "blob" }).then((r) => r.data);
export const triggerApply = (jobId: string) => api.post(`/jobs/${jobId}/apply`).then((r) => r.data);
export const getJobActivityStats = () => api.get("/jobs/activity-stats").then((r) => r.data);
export const applyNow = (jobId: string) => api.post(`/jobs/${jobId}/apply-now`).then((r) => r.data);
export const rescheduleJob = (jobId: string, scheduledAt: string) =>
  api.patch(`/jobs/${jobId}/reschedule`, { scheduled_at: scheduledAt }).then((r) => r.data);
export const rescheduleFollowup = (jobId: string, followupId: string, scheduledAt: string) =>
  api.patch(`/jobs/${jobId}/followup/${followupId}/reschedule`, { scheduled_at: scheduledAt }).then((r) => r.data);
export const assignProfileToJob = (jobId: string, profileId: string) =>
  api.patch(`/jobs/${jobId}/assign-profile`, { profile_id: profileId }).then((r) => r.data);

// Applications
export const getApplications = (params?: any) => api.get("/applications/", { params }).then((r) => r.data);
export const getPendingApproval = () => api.get("/applications/pending-approval").then((r) => r.data);
export const approveApplication = (id: string, action: string, reason?: string) =>
  api.post(`/applications/${id}/approve`, { action, rejection_reason: reason }).then((r) => r.data);
export const togglePin = (id: string) => api.patch(`/applications/${id}/pin`).then((r) => r.data);

// Leads
export const getLeads = (params?: any) => api.get("/leads/", { params }).then((r) => r.data);
export const createLead = (data: any) => api.post("/leads/", data).then((r) => r.data);
export const updateLead = (id: string, data: any) => api.patch(`/leads/${id}`, data).then((r) => r.data);
export const deleteLead = (id: string) => api.delete(`/leads/${id}`).then((r) => r.data);
export const approveLead = (id: string, action: string) =>
  api.post(`/leads/${id}/approve`, { action }).then((r) => r.data);
export const uploadLeads = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/leads/upload", form, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
};
export const exportLeads = () => api.get("/leads/export", { responseType: "blob" }).then((r) => r.data);
export const scrapeLeads = () => api.post("/leads/scrape").then((r) => r.data);
export const getScrapeStatus = () => api.get("/leads/scrape-status").then((r) => r.data);

// Templates
export const getTemplates = (type?: string) => api.get("/templates/", { params: { template_type: type } }).then((r) => r.data);
export const createTemplate = (data: any) => api.post("/templates/", data).then((r) => r.data);
export const updateTemplate = (id: string, data: any) => api.patch(`/templates/${id}`, data).then((r) => r.data);
export const deleteTemplate = (id: string) => api.delete(`/templates/${id}`).then((r) => r.data);

// Settings
export const getSettings = () => api.get("/settings/").then((r) => r.data);
export const updateSettings = (data: any) => api.put("/settings/", data).then((r) => r.data);
export const getApiKeys = () => api.get("/settings/api-keys").then((r) => r.data);
export const getHunterUsage = () => api.get("/settings/hunter-usage").then((r) => r.data);
export const getHasDataUsage = () => api.get("/settings/hasdata-usage").then((r) => r.data);
export const getApifyUsage = () => api.get("/settings/apify-usage").then((r) => r.data);
export const updateApiKeys = (data: any) => api.put("/settings/api-keys", data).then((r) => r.data);
export const triggerResearchNow = () => api.post("/settings/research-now").then((r) => r.data);
export const triggerMatchNow = () => api.post("/settings/match-now").then((r) => r.data);
export const triggerCleanupSkipped = () => api.post("/settings/cleanup-skipped-now").then((r) => r.data);

// Users
export const getUsers = () => api.get("/users/").then((r) => r.data);
export const createUser = (data: { email: string; full_name: string; password: string; role: string }) =>
  api.post("/users/", data).then((r) => r.data);
export const updateUser = (id: string, data: any) => api.patch(`/users/${id}`, data).then((r) => r.data);
export const deleteUser = (id: string) => api.delete(`/users/${id}`).then((r) => r.data);
export const getUserPermissions = (id: string) => api.get(`/users/${id}/permissions`).then((r) => r.data);
export const setUserPermissions = (id: string, permissions: Record<string, boolean>) =>
  api.put(`/users/${id}/permissions`, { permissions }).then((r) => r.data);

// Email Accounts
export const getEmailAccounts = () => api.get("/email-accounts/").then((r) => r.data);
export const createEmailAccount = (data: { display_name: string; email: string; client_id: string; client_secret: string }) =>
  api.post("/email-accounts/", data).then((r) => r.data);
export const updateEmailAccount = (id: string, data: any) => api.patch(`/email-accounts/${id}`, data).then((r) => r.data);
export const getProfileEmails = () => api.get("/email-accounts/profile-emails").then((r) => r.data);
export const addProfileEmail = (profileId: string, email: string, isPrimary: boolean = false) =>
  api.post(`/profiles/${profileId}/emails`, { email, is_primary: isPrimary }).then((r) => r.data);
export const deleteProfileEmail = (profileId: string, emailId: string) =>
  api.delete(`/profiles/${profileId}/emails/${emailId}`).then((r) => r.data);
export const connectGmail = (params?: { account_id?: string; profile_email_id?: string }) =>
  api.get("/email-accounts/connect", { params }).then((r) => r.data);
export const deleteEmailAccount = (id: string) => api.delete(`/email-accounts/${id}`).then((r) => r.data);
export const toggleEmailAccount = (id: string) => api.patch(`/email-accounts/${id}/toggle`).then((r) => r.data);
export const sendTestEmail = (id: string, toEmail: string) =>
  api.post(`/email-accounts/${id}/send-test`, { to_email: toEmail }).then((r) => r.data);

// Activities
export const getActivities = (params?: { limit?: number; job_id?: string }) =>
  api.get("/activities/", { params: { limit: 100, ...params } }).then((r) => r.data);

// Alerts
export const getAlerts = () => api.get("/alerts/").then((r) => r.data);
export const getUnreadAlertCount = () => api.get("/alerts/unread-count").then((r) => r.data);
export const markAllAlertsRead = () => api.post("/alerts/mark-all-read").then((r) => r.data);
export const dismissAlert = (id: string) => api.delete(`/alerts/${id}`).then((r) => r.data);
export const dismissAllAlerts = () => api.delete("/alerts/").then((r) => r.data);

// Analytics
export const getOverview = () => api.get("/analytics/overview").then((r) => r.data);
export const getByProfile = () => api.get("/analytics/by-profile").then((r) => r.data);
export const getByCountry = () => api.get("/analytics/by-country").then((r) => r.data);
