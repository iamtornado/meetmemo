"use client";

import { useState, useEffect, createContext, useContext } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, setTokens, clearTokens, getToken } from "@/lib/auth";
import type { User } from "@/types";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    // Use the same host as the current page
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000/api/v1`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function AuthProviderInner({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (token) {
      fetch(`${getApiBase()}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((u) => setUser(u))
        .catch(() => {
          clearTokens();
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${getApiBase()}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(err.detail);
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    setUser(data.user);
  };

  const register = async (email: string, password: string, display_name: string) => {
    const res = await fetch(`${getApiBase()}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Registration failed" }));
      throw new Error(err.detail);
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    setUser(data.user);
  };

  const logout = () => {
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
        isAdmin: user?.role === "admin",
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProviderInner>{children}</AuthProviderInner>
    </QueryClientProvider>
  );
}
