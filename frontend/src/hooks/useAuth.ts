"use client";

import { useCallback, useEffect, useState } from "react";
import { login as apiLogin, ApiError } from "@/lib/api";

const TOKEN_KEY = "auth_token";

export function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Hydrate token from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      setToken(stored);
      setIsAuthenticated(true);
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (password: string) => {
    const { token: newToken } = await apiLogin(password);
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    setIsAuthenticated(true);
    return newToken;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setIsAuthenticated(false);
  }, []);

  return {
    token,
    isAuthenticated,
    isLoading,
    login,
    logout,
  };
}

export { ApiError };
