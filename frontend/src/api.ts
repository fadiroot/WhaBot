import axios from "axios";

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("token");
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(err);
  },
);

// --- types ---------------------------------------------------------------
export interface User {
  id: string;
  email: string;
  name: string;
  roles: string[];
  whatsapp_number?: string;
  is_active: boolean;
}

export interface Project {
  id: string;
  slug: string;
  name: string;
  description?: string;
  repository_url: string;
  provider: string;
  default_branch: string;
  allowed_whatsapp_chats: string[];
  member_ids: string[];
  indexed_files: number;
  last_indexed_at?: string;
}

export interface TaskStep {
  kind: string;
  name?: string;
  content?: string;
  arguments?: Record<string, unknown>;
  output?: string;
  created_at?: string;
}

export interface Task {
  id: string;
  request_text: string;
  status: string;
  kind: string;
  project_id?: string;
  whatsapp_chat_id?: string;
  whatsapp_number?: string;
  steps: TaskStep[];
  result?: string;
  error?: string;
  pr_url?: string;
  branch?: string;
  created_at: string;
}

export interface Approval {
  id: string;
  action: string;
  summary: string;
  status: string;
  project_id?: string;
  task_id?: string;
  payload: Record<string, unknown>;
  created_at: string;
  decided_by?: string;
  decided_at?: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  actor_id?: string;
  actor_kind: string;
  project_id?: string;
  task_id?: string;
  payload: Record<string, unknown>;
  success: boolean;
  message?: string;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}
