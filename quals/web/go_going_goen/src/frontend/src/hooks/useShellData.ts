import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import {
  persistTeamToken,
  readQueryTeamToken,
  readStoredTeamToken,
  stripTokenFromUrl,
} from "../lib/teamToken";
import type { ProgressResponse, SessionInfo } from "../types";

type ShellState = {
  session: SessionInfo | null;
  progress: ProgressResponse | null;
  loading: boolean;
  error: string | null;
  needsAuth: boolean;
  refresh: () => Promise<void>;
  resetAll: () => Promise<void>;
};

async function bootstrapIfNeeded(): Promise<boolean> {
  const queryToken = readQueryTeamToken();
  const storedToken = readStoredTeamToken();
  const token = queryToken ?? storedToken;
  if (!token) {
    return false;
  }

  await api.bootstrapSession(token);
  persistTeamToken(token);
  if (queryToken) {
    stripTokenFromUrl();
  }
  return true;
}

export function useShellData(): ShellState {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [nextSession, nextProgress] = await Promise.all([api.getMe(), api.getProgress()]);
      setSession(nextSession.user_id === null ? null : nextSession);
      setProgress(nextProgress);
      setNeedsAuth(nextSession.user_id === null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load shell state.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        await bootstrapIfNeeded();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Authentication failed.");
        setLoading(false);
        setNeedsAuth(true);
        return;
      }
      await refresh();
    };

    void load();
  }, [refresh]);

  return {
    session,
    progress,
    loading,
    error,
    needsAuth,
    refresh,
    resetAll: async () => {
      await api.resetAll();
      await refresh();
    },
  };
}
