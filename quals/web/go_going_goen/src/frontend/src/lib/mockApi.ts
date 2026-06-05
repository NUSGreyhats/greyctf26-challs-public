import type {
  PinpointGuessResponse,
  PinpointStatus,
  ProgressResponse,
  QueenPosition,
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

type StoredState = {
  me: SessionInfo;
  progress: ProgressResponse;
  pinpoint: PinpointStatus & {
    answer: string;
  };
  queens: {
    size: number;
    queens: QueenPosition[];
    validation_started_at: string | null;
    last_result: QueensBoardResponse["submission"]["last_result"];
  };
  tango: {
    ledger: TangoLedger;
    latest_attempt_state: TangoStatus["latest_attempt_state"];
  };
};

const STORAGE_KEY = "ggg-shell-state";
const VALIDATION_WINDOW_MS = 3600;
const TANGO_SOLUTION: TangoGrid = [
  [1, 1, 2, 1, 2, 2],
  [1, 2, 2, 1, 1, 2],
  [2, 1, 1, 2, 2, 1],
  [1, 2, 1, 2, 1, 2],
  [2, 1, 2, 1, 2, 1],
  [2, 2, 1, 2, 1, 1],
];
const TANGO_FIXED_CELLS = [
  { row: 0, col: 0, value: 1 as const },
  { row: 0, col: 2, value: 2 as const },
  { row: 1, col: 5, value: 2 as const },
  { row: 2, col: 0, value: 2 as const },
  { row: 3, col: 3, value: 2 as const },
  { row: 4, col: 4, value: 2 as const },
  { row: 5, col: 1, value: 2 as const },
  { row: 5, col: 5, value: 1 as const },
];
const TANGO_INITIAL_GRID = TANGO_SOLUTION.map((row, rowIndex) =>
  row.map((cell, colIndex) =>
    TANGO_FIXED_CELLS.some((fixed) => fixed.row === rowIndex && fixed.col === colIndex) ? cell : 0,
  ),
) as TangoGrid;

function createDefaultLedger(): TangoLedger {
  return {
    currency_symbol: "$",
    spendable_dollars: 0,
    committed_dollars: 0,
    pending_dollars: 0,
    play_cost_dollars: 100,
    flag_cost_dollars: 1000,
    entries: [],
  };
}

function createDefaultState(): StoredState {
  return {
    me: {
      user_id: 1,
      username: "team",
    },
    progress: {
      stage1: { cleared: false },
      stage2: { cleared: false },
      stage3: { cleared: false },
      downloads: {
        stage1: false,
        stage2: false,
        stage3: false,
      },
    },
    pinpoint: {
      guesses_used: 0,
      remaining_guesses: 5,
      solved: false,
      last_result: null,
      recent_guesses: [],
      answer: "crane",
    },
    queens: {
      size: 50,
      queens: [],
      validation_started_at: null,
      last_result: null,
    },
    tango: {
      ledger: createDefaultLedger(),
      latest_attempt_state: "idle",
    },
  };
}

function readState(): StoredState {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    const fresh = createDefaultState();
    writeState(fresh);
    return fresh;
  }

  const parsed = JSON.parse(raw) as Partial<StoredState>;
  const fresh = createDefaultState();
  const merged: StoredState = {
    ...fresh,
    ...parsed,
    me: {
      ...fresh.me,
      ...parsed.me,
    },
    progress: {
      ...fresh.progress,
      ...parsed.progress,
      stage1: {
        ...fresh.progress.stage1,
        ...parsed.progress?.stage1,
      },
      stage2: {
        ...fresh.progress.stage2,
        ...parsed.progress?.stage2,
      },
      stage3: {
        ...fresh.progress.stage3,
        ...parsed.progress?.stage3,
      },
      downloads: {
        ...fresh.progress.downloads,
        ...parsed.progress?.downloads,
      },
    },
    pinpoint: {
      ...fresh.pinpoint,
      ...parsed.pinpoint,
      recent_guesses: parsed.pinpoint?.recent_guesses ?? fresh.pinpoint.recent_guesses,
    },
    queens: {
      ...fresh.queens,
      ...parsed.queens,
      queens: parsed.queens?.queens ?? fresh.queens.queens,
    },
    tango: {
      ...fresh.tango,
      ...parsed.tango,
      ledger: {
        ...fresh.tango.ledger,
        ...parsed.tango?.ledger,
        entries: parsed.tango?.ledger?.entries ?? fresh.tango.ledger.entries,
      },
    },
  };
  writeState(merged);
  return merged;
}

function writeState(state: StoredState) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function syncUnlocks(state: StoredState) {
  state.progress.downloads.stage1 = Boolean(state.me.user_id);
  state.progress.downloads.stage2 = state.progress.stage1.cleared;
  state.progress.downloads.stage3 = state.progress.stage2.cleared;
}

function deriveQueensSubmission(state: StoredState): QueensBoardResponse["submission"] {
  if (!state.queens.validation_started_at) {
    return {
      status: "idle",
      progress_pct: 0,
      last_result: state.queens.last_result,
    };
  }

  const elapsed = Date.now() - new Date(state.queens.validation_started_at).getTime();
  if (elapsed < VALIDATION_WINDOW_MS) {
    return {
      status: "validating",
      progress_pct: Math.min(99, Math.round((elapsed / VALIDATION_WINDOW_MS) * 100)),
      last_result: "pending",
    };
  }

  const totalQueens = state.queens.queens.length;
  if (totalQueens >= 1337) {
    state.progress.stage2.cleared = true;
    state.queens.last_result = "win";
    syncUnlocks(state);
    writeState(state);
    return { status: "won", progress_pct: 100, last_result: "win" };
  }

  state.queens.last_result = "valid";
  state.queens.validation_started_at = null;
  writeState(state);
  return { status: "valid", progress_pct: 100, last_result: "valid" };
}

export const mockApi = {
  async getMe(): Promise<SessionInfo> {
    const state = readState();
    if (!state.me.user_id) {
      state.me = createDefaultState().me;
      writeState(state);
    }
    return state.me;
  },

  async getProgress(): Promise<ProgressResponse> {
    const state = readState();
    syncUnlocks(state);
    writeState(state);
    return state.progress;
  },

  async resetAll(): Promise<{ ok: true }> {
    const state = readState();
    state.pinpoint = createDefaultState().pinpoint;
    state.queens = createDefaultState().queens;
    state.tango = createDefaultState().tango;
    syncUnlocks(state);
    writeState(state);
    return { ok: true };
  },

  async resetStage(stage: StageSlug): Promise<{ ok: true }> {
    const state = readState();
    const fresh = createDefaultState();
    if (stage === "pinpoint") {
      state.pinpoint = { ...fresh.pinpoint, answer: state.pinpoint.answer };
    }
    if (stage === "queens") {
      state.queens = fresh.queens;
    }
    if (stage === "tango") {
      state.tango = fresh.tango;
    }
    writeState(state);
    return { ok: true };
  },

  async getPinpointStatus(): Promise<PinpointStatus> {
    const { pinpoint } = readState();
    return pinpoint;
  },

  async submitGuess(guess: string): Promise<PinpointGuessResponse> {
    const state = readState();
    if (state.pinpoint.guesses_used >= 5) {
      throw new Error("Guess limit reached.");
    }

    const isCorrect = guess.trim().toLowerCase() === state.pinpoint.answer;
    state.pinpoint.guesses_used += 1;
    state.pinpoint.remaining_guesses = Math.max(0, 5 - state.pinpoint.guesses_used);
    state.pinpoint.last_result = isCorrect ? "correct" : "wrong";
    state.pinpoint.solved = state.pinpoint.solved || isCorrect;
    state.pinpoint.recent_guesses = [guess.trim().toLowerCase(), ...state.pinpoint.recent_guesses].slice(0, 5);

    if (isCorrect) {
      state.progress.stage1.cleared = true;
      syncUnlocks(state);
      writeState(state);
      return {
        result: "correct",
      };
    }

    writeState(state);
    return {
      result: "wrong",
      guesses_used: state.pinpoint.guesses_used,
      remaining_guesses: state.pinpoint.remaining_guesses,
    };
  },

  async getQueensBoard(): Promise<QueensBoardResponse> {
    const state = readState();
    return {
      size: state.queens.size,
      queens: state.queens.queens,
      total_queens: state.queens.queens.length,
      submission: deriveQueensSubmission(state),
    };
  },

  async addQueen(row: number, col: number): Promise<{ ok: true; total_queens: number }> {
    const state = readState();
    if (row < 0 || col < 0 || row >= state.queens.size || col >= state.queens.size) {
      throw new Error("Queen placement is out of bounds.");
    }
    if (!state.queens.queens.some((queen) => queen.row === row && queen.col === col)) {
      state.queens.queens.push({ row, col });
    }
    writeState(state);
    return { ok: true, total_queens: state.queens.queens.length };
  },

  async removeQueen(row: number, col: number): Promise<{ ok: true; total_queens: number }> {
    const state = readState();
    const index = state.queens.queens.findIndex((queen) => queen.row === row && queen.col === col);
    if (index >= 0) {
      state.queens.queens.splice(index, 1);
    }
    writeState(state);
    return { ok: true, total_queens: state.queens.queens.length };
  },

  async submitQueens(): Promise<QueensSubmitResponse> {
    const state = readState();
    state.queens.validation_started_at = new Date().toISOString();
    state.queens.last_result = "pending";
    writeState(state);

    const totalQueens = state.queens.queens.length;
    if (totalQueens >= 1337) {
      return {
        result: "win",
        total_queens: totalQueens,
      };
    }

    return {
      result: "valid",
      total_queens: totalQueens,
    };
  },

  async getTangoStatus(): Promise<TangoStatus> {
    const { tango } = readState();
    return {
      puzzle: {
        size: 6,
        values: { empty: 0, sun: 1, moon: 2 },
        fixed_cells: TANGO_FIXED_CELLS,
        initial_grid: TANGO_INITIAL_GRID,
      },
      ledger: tango.ledger,
      latest_attempt_state: tango.latest_attempt_state,
    };
  },

  async getTangoLedger(): Promise<TangoLedger> {
    return readState().tango.ledger;
  },

  async refreshTangoLedger(): Promise<TangoLedger> {
    const state = readState();
    for (const entry of state.tango.ledger.entries) {
      if (entry.status === "PENDING") {
        entry.status = "ROLLED_BACK";
      }
    }
    recalculateTangoLedger(state.tango.ledger);
    writeState(state);
    return state.tango.ledger;
  },

  async submitTango(grid: TangoGrid): Promise<TangoSubmitResponse> {
    const state = readState();
    const attemptId = crypto.randomUUID();
    const entryId = crypto.randomUUID();
    const isSolution = JSON.stringify(grid) === JSON.stringify(TANGO_SOLUTION);
    const status = isSolution ? "COMMITTED" : "ROLLED_BACK";
    state.tango.ledger.entries.push({
      entry_id: entryId,
      attempt_id: attemptId,
      status,
      amount: 100,
    });
    if (isSolution) {
      state.tango.ledger.entries.push({
        entry_id: crypto.randomUUID(),
        attempt_id: attemptId,
        status: "PLAY_FEE",
        amount: -100,
      });
    }
    state.tango.latest_attempt_state = isSolution ? "accepted" : "rejected";
    recalculateTangoLedger(state.tango.ledger);
    writeState(state);

    if (!isSolution) {
      return {
        error: "invalid_grid",
        message: "Grid rejected.",
        attempt_id: attemptId,
      };
    }

    return {
      result: "accepted",
      dollars_awarded: 100,
      attempt_id: attemptId,
    };
  },

  async buyTangoFlag(): Promise<TangoBuyFlagResponse> {
    const state = readState();
    if (state.tango.ledger.spendable_dollars < state.tango.ledger.flag_cost_dollars) {
      return { error: "not_enough_credits", message: "Not enough credits." };
    }
    state.progress.stage3.cleared = true;
    syncUnlocks(state);
    writeState(state);
    return {
      result: "win",
      flag: "NUS{placeholder_flag}",
    };
  },
};

function recalculateTangoLedger(ledger: TangoLedger) {
  ledger.committed_dollars = ledger.entries
    .filter((entry) => entry.status === "COMMITTED")
    .reduce((total, entry) => total + entry.amount, 0);
  ledger.pending_dollars = ledger.entries
    .filter((entry) => entry.status === "PENDING")
    .reduce((total, entry) => total + entry.amount, 0);
  ledger.spendable_dollars = ledger.committed_dollars + ledger.pending_dollars;
  ledger.spendable_dollars += ledger.entries
    .filter((entry) => entry.status === "PLAY_FEE")
    .reduce((total, entry) => total + entry.amount, 0);
}
