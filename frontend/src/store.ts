import { create } from "zustand";
import { User } from "./api";

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (token: string, user: User) => void;
  clear: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: (() => {
    try {
      return JSON.parse(localStorage.getItem("user") || "null");
    } catch {
      return null;
    }
  })(),
  token: localStorage.getItem("token"),
  setAuth: (token, user) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
    set({ token, user });
  },
  clear: () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    set({ token: null, user: null });
  },
}));
