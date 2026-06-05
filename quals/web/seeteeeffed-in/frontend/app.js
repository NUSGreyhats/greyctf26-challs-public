const SESSION_STORAGE_KEY = "profile-sync-session-token";
const TEAM_TOKEN_STORAGE_KEY = "profile-sync-team-token";

export function getSessionToken() {
  return window.localStorage.getItem(SESSION_STORAGE_KEY);
}

export function setSessionToken(token) {
  if (token) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

export function getTeamToken() {
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get("team_token") || params.get("token");
  if (queryToken) {
    setTeamToken(queryToken);
    return queryToken;
  }
  return window.localStorage.getItem(TEAM_TOKEN_STORAGE_KEY);
}

export function setTeamToken(token) {
  if (token) {
    window.localStorage.setItem(TEAM_TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TEAM_TOKEN_STORAGE_KEY);
  }
}

export function setStatus(target, message, tone = "") {
  if (!target) return;
  target.textContent = message || "";
  if (tone) {
    target.dataset.tone = tone;
  } else {
    delete target.dataset.tone;
  }
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function initialsFor(value) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (!parts.length) return "PS";
  return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

export function formatTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

export async function api(path, options = {}) {
  const headers = {
    ...(options.headers || {})
  };

  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers["X-Session-Token"] = sessionToken;
  }
  const teamToken = getTeamToken();
  if (teamToken) {
    headers["X-Team-Token"] = teamToken;
  }
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, {
    ...options,
    headers
  });

  const payload = await response.json();
  if (!response.ok || payload.status !== "success") {
    throw new Error(payload.message || "Request failed");
  }

  return payload.data;
}

export async function loadProfile() {
  const token = getSessionToken();
  if (!token) {
    return null;
  }

  try {
    return await api("/api/me");
  } catch (error) {
    setSessionToken("");
    throw error;
  }
}

export async function loadPosts() {
  return api("/api/posts");
}

export function wireChrome() {
  const logoutButtons = document.querySelectorAll("[data-logout]");
  for (const button of logoutButtons) {
    button.addEventListener("click", () => {
      setSessionToken("");
      window.location.href = "/auth.html";
    });
  }
}

export function renderViewer(profile) {
  const authOnly = document.querySelectorAll("[data-auth-only]");
  const guestOnly = document.querySelectorAll("[data-guest-only]");

  for (const node of authOnly) {
    node.classList.toggle("hidden", !profile);
  }

  for (const node of guestOnly) {
    node.classList.toggle("hidden", Boolean(profile));
  }
}

export function renderPostsList(posts, container) {
  if (!container) return;

  if (!posts.length) {
    container.innerHTML = '<div class="empty-state">No posts yet. Join the network and publish the first update.</div>';
    return;
  }

  container.innerHTML = posts
    .map(
      (post) => `
        <article class="post-card">
          <div class="post-head">
            <div class="post-author">
              <div class="post-avatar">${escapeHtml(initialsFor(post.display_name || post.username))}</div>
              <div class="post-meta">
                <strong>${escapeHtml(post.display_name)}</strong>
                <span>@${escapeHtml(post.username)}</span>
              </div>
            </div>
            <div class="muted-meta">${escapeHtml(formatTimestamp(post.created_at))}</div>
          </div>
          <div class="post-body">${escapeHtml(post.body)}</div>
        </article>
      `
    )
    .join("");
}

export function summarizePosts(posts) {
  return {
    totalPosts: posts.length,
    uniqueAuthors: new Set(posts.map((post) => post.username)).size
  };
}
