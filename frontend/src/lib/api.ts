import type {
  AuthGroupMapping,
  Meeting,
  MeetingListResponse,
  Transcript,
  Summary,
  SearchResponse,
  Team,
  User,
} from "@/types";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000/api/v1`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${getApiBase()}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      // Try refresh
      const refreshed = await refreshToken();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${localStorage.getItem("access_token")}`;
        const retryRes = await fetch(`${getApiBase()}${path}`, { ...options, headers });
        if (retryRes.ok) return retryRes.json();
      }
      // Redirect to login
      window.location.href = "/login";
      throw new ApiError("Unauthorized", 401);
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(err.detail || "Request failed", res.status);
  }

  if (res.status === 204) return {} as T;
  return res.json();
}

async function refreshToken(): Promise<boolean> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return false;

  try {
    const res = await fetch(`${getApiBase()}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// Auth
export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, display_name: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }),

  getMe: () => request<User>("/auth/me"),

  // Teams
  listTeams: () => request<Team[]>("/teams"),

  createTeam: (data: { name: string; description?: string }) =>
    request<Team>("/teams", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getTeam: (id: string) => request<Team>(`/teams/${id}`),

  deleteTeam: (id: string) =>
    request<void>(`/teams/${id}`, { method: "DELETE" }),

  addTeamMember: (teamId: string, userId: string, role: string = "viewer") =>
    request<unknown>(`/teams/${teamId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, role }),
    }),

  removeTeamMember: (teamId: string, userId: string) =>
    request<void>(`/teams/${teamId}/members/${userId}`, { method: "DELETE" }),

  // Meetings
  listMeetings: (params?: {
    page?: number;
    page_size?: number;
    status?: string;
    team_id?: string;
  }) => {
    const search = new URLSearchParams();
    if (params?.page) search.set("page", String(params.page));
    if (params?.page_size) search.set("page_size", String(params.page_size));
    if (params?.status) search.set("status", params.status);
    if (params?.team_id) search.set("team_id", params.team_id);
    return request<MeetingListResponse>(`/meetings?${search}`);
  },

  createMeeting: (file: File, title?: string, team_id?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    if (team_id) form.append("team_id", team_id);
    return request<Meeting>("/meetings", {
      method: "POST",
      body: form,
    });
  },

  getMeeting: (id: string) => request<Meeting>(`/meetings/${id}`),

  updateMeeting: (
    id: string,
    data: {
      title?: string;
      date?: string;
      meeting_location?: string | null;
      host?: string | null;
      recorder_unit?: string | null;
    }
  ) =>
    request<Meeting>(`/meetings/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteMeeting: (id: string) =>
    request<void>(`/meetings/${id}`, { method: "DELETE" }),

  processMeeting: (id: string) =>
    request<{ message: string }>(`/meetings/${id}/process`, { method: "POST" }),

  // Transcript
  getTranscript: (meetingId: string) =>
    request<Transcript>(`/meetings/${meetingId}/transcript`),

  renameSpeakers: (meetingId: string, mappings: Record<string, string>) =>
    request<void>(`/meetings/${meetingId}/transcript/speakers`, {
      method: "PUT",
      body: JSON.stringify({ mappings }),
    }),

  exportTranscriptDocx: async (meetingId: string, suggestedFilename?: string) => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${getApiBase()}/meetings/${meetingId}/transcript/export`, {
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(err.detail || "Export failed", res.status);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const asciiMatch = disposition.match(/filename="([^"]+)"/i);
    const filename = utf8Match
      ? decodeURIComponent(utf8Match[1])
      : asciiMatch?.[1] || suggestedFilename || "transcript.docx";

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // Summary
  getSummary: (meetingId: string) =>
    request<Summary>(`/meetings/${meetingId}/summary`),

  exportFormalMinutesDocx: async (meetingId: string, suggestedFilename?: string) => {
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(
      `${getApiBase()}/meetings/${meetingId}/summary/minutes/export`,
      { headers }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(err.detail || "Export failed", res.status);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const asciiMatch = disposition.match(/filename="([^"]+)"/i);
    const filename = utf8Match
      ? decodeURIComponent(utf8Match[1])
      : asciiMatch?.[1] || suggestedFilename || "minutes.docx";

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  regenerateSummary: (meetingId: string) =>
    request<{ message: string }>(`/meetings/${meetingId}/summary/regenerate`, {
      method: "POST",
    }),

  updateSummary: (meetingId: string, data: Partial<Summary>) =>
    request<Summary>(`/meetings/${meetingId}/summary`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Search
  search: (q: string, team_id?: string, page = 1) => {
    const search = new URLSearchParams({ q, page: String(page) });
    if (team_id) search.set("team_id", team_id);
    return request<SearchResponse>(`/search?${search}`);
  },

  // Admin
  adminListUsers: () => request<User[]>("/admin/users"),
  adminUpdateUserRole: (userId: string, role: string) =>
    request<void>(`/admin/users/${userId}/role?role=${role}`, { method: "PUT" }),
  adminGetStats: () =>
    request<{ total_users: number; total_meetings: number }>("/admin/stats"),
  adminListAuthMappings: () =>
    request<AuthGroupMapping[]>("/admin/auth/mappings"),
  adminCreateAuthMapping: (data: {
    auth_provider?: string;
    group_name: string;
    mapped_role: string;
  }) =>
    request<AuthGroupMapping>("/admin/auth/mappings", {
      method: "POST",
      body: JSON.stringify({
        auth_provider: data.auth_provider ?? "ldap",
        group_name: data.group_name,
        mapped_role: data.mapped_role,
      }),
    }),
  adminDeleteAuthMapping: (id: string) =>
    request<void>(`/admin/auth/mappings/${id}`, { method: "DELETE" }),
};
