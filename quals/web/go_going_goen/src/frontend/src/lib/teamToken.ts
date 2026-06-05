const TEAM_TOKEN_STORAGE_KEY = "ggg_team_token";

export function readStoredTeamToken(): string | null {
  try {
    return localStorage.getItem(TEAM_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function persistTeamToken(token: string): void {
  try {
    localStorage.setItem(TEAM_TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore storage failures; cookie session may still work this visit.
  }
}

export function readQueryTeamToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token")?.trim();
  return token || null;
}

export function stripTokenFromUrl(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("token")) {
    return;
  }
  url.searchParams.delete("token");
  const next = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState({}, "", next);
}

export { TEAM_TOKEN_STORAGE_KEY };
