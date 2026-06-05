import { mockApi } from "./mockApi";
import type {
  DownloadStageKey,
  PinpointGuessResponse,
  PinpointStatus,
  ProgressResponse,
  QueensBoardResponse,
  QueensSubmitResponse,
  SessionInfo,
  StageSlug,
  TangoBuyFlagResponse,
  TangoGrid,
  TangoLedger,
  TangoStatus,
  TangoSubmitResponse,
} from "../types";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly error?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    let error: string | undefined;

    try {
      const body = (await response.json()) as { message?: string; error?: string };
      message = body.message ?? message;
      error = body.error;
    } catch {}

    throw new ApiError(message, response.status, error);
  }
  return (await response.json()) as T;
}

async function requestTangoSubmit(grid: TangoGrid): Promise<TangoSubmitResponse> {
  const response = await fetch("/api/v3/tango/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grid }),
  });
  const body = (await response.json()) as TangoSubmitResponse | { message?: string; error?: string };
  if (
    response.ok ||
    (response.status === 400 && "attempt_id" in body) ||
    (response.status === 500 && "attempt_id" in body) ||
    response.status === 429
  ) {
    return body as TangoSubmitResponse;
  }
  throw new ApiError(body.message ?? `Request failed with status ${response.status}.`, response.status, body.error);
}

async function requestTangoBuyFlag(): Promise<TangoBuyFlagResponse> {
  const response = await fetch("/api/v3/tango/buy-flag", { method: "POST" });
  const body = (await response.json()) as TangoBuyFlagResponse | { message?: string; error?: string };
  if (response.ok || response.status === 402) {
    return body as TangoBuyFlagResponse;
  }
  throw new ApiError(body.message ?? `Request failed with status ${response.status}.`, response.status, body.error);
}

async function withFallback<T>(live: () => Promise<T>, fallback: () => Promise<T>) {
  try {
    return await live();
  } catch (error) {
    if (error instanceof ApiError && error.status !== 404) {
      throw error;
    }
    return fallback();
  }
}

export const api = {
  bootstrapSession: (token: string) =>
    requestJson<{ ok: true; authenticated: true }>(
      `/api/auth/session?token=${encodeURIComponent(token)}`,
      { method: "POST" },
    ),

  getMe: () =>
    withFallback<SessionInfo>(() => requestJson("/api/me"), () => mockApi.getMe()),

  getProgress: () =>
    withFallback<ProgressResponse>(() => requestJson("/api/progress"), () => mockApi.getProgress()),

  resetAll: () =>
    withFallback<{ ok: true }>(
      () => requestJson("/api/reset", { method: "POST" }),
      () => mockApi.resetAll(),
    ),

  resetStage: (stage: StageSlug) => {
    const stagePath = stage === "pinpoint" ? "v1/pinpoint" : stage === "queens" ? "v2/queens" : "v3/tango";
    return withFallback<{ ok: true }>(
      () => requestJson(`/api/${stagePath}/reset`, { method: "POST" }),
      () => mockApi.resetStage(stage),
    );
  },

  getPinpointStatus: () =>
    withFallback<PinpointStatus>(
      () => requestJson("/api/v1/pinpoint/status"),
      () => mockApi.getPinpointStatus(),
    ),

  submitGuess: (guess: string) =>
    withFallback<PinpointGuessResponse>(
      () =>
        requestJson("/api/v1/pinpoint/guess", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ guess }),
        }),
      () => mockApi.submitGuess(guess),
    ),

  getQueensBoard: () =>
    withFallback<QueensBoardResponse>(
      () => requestJson("/api/v2/queens/board"),
      () => mockApi.getQueensBoard(),
    ),

  addQueen: (row: number, col: number) =>
    withFallback<{ ok: true; total_queens: number }>(
      () =>
        requestJson("/api/v2/queens/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ row, col }),
        }),
      () => mockApi.addQueen(row, col),
    ),

  removeQueen: (row: number, col: number) =>
    withFallback<{ ok: true; total_queens: number }>(
      () =>
        requestJson("/api/v2/queens/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ row, col }),
        }),
      () => mockApi.removeQueen(row, col),
    ),

  submitQueens: () =>
    withFallback<QueensSubmitResponse>(
      () =>
        requestJson("/api/v2/queens/submit", {
          method: "POST",
        }),
      () => mockApi.submitQueens(),
    ),

  getTangoStatus: () =>
    withFallback<TangoStatus>(
      () => requestJson("/api/v3/tango/status"),
      () => mockApi.getTangoStatus(),
    ),

  getTangoLedger: () =>
    withFallback<TangoLedger>(
      () => requestJson("/api/v3/tango/ledger"),
      () => mockApi.getTangoLedger(),
    ),

  refreshTangoLedger: () =>
    withFallback<TangoLedger>(
      () => requestJson("/api/v3/tango/ledger/refresh", { method: "POST" }),
      () => mockApi.refreshTangoLedger(),
    ),

  submitTango: (grid: TangoGrid) =>
    withFallback<TangoSubmitResponse>(
      () => requestTangoSubmit(grid),
      () => mockApi.submitTango(grid),
    ),

  buyTangoFlag: () =>
    withFallback<TangoBuyFlagResponse>(
      () => requestTangoBuyFlag(),
      () => mockApi.buyTangoFlag(),
    ),

  getDownloadUrl: (stage: DownloadStageKey) => `/api/downloads/${stage}`,
};
