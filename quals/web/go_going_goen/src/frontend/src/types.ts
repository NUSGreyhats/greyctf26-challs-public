export type StageSlug = "pinpoint" | "queens" | "tango";

export type SessionInfo = {
  user_id: number;
  username: string;
};

export type ProgressResponse = {
  stage1: {
    cleared: boolean;
  };
  stage2: {
    cleared: boolean;
  };
  stage3: {
    cleared: boolean;
  };
  downloads: {
    stage1: boolean;
    stage2: boolean;
    stage3: boolean;
  };
};

export type PinpointStatus = {
  guesses_used: number;
  remaining_guesses: number;
  solved: boolean;
  last_result: "correct" | "wrong" | null;
  recent_guesses: string[];
};

export type PinpointGuessResponse =
  | {
      result: "correct";
    }
  | {
      result: "wrong";
      guesses_used: number;
      remaining_guesses: number;
    };

export type QueenPosition = {
  row: number;
  col: number;
};

export type QueensBoardResponse = {
  size: number;
  queens: QueenPosition[];
  total_queens: number;
  submission: {
    status: "idle" | "validating" | "failed" | "valid" | "won";
    progress_pct: number;
    last_result: "pending" | "invalid" | "valid" | "win" | null;
  };
};

export type QueensSubmitResponse =
  | {
      result: "valid";
      total_queens: number;
    }
  | {
      result: "win";
      total_queens: number;
    };

export type TangoCell = 0 | 1 | 2;
export type TangoGrid = TangoCell[][];

export type TangoFixedCell = {
  row: number;
  col: number;
  value: TangoCell;
};

export type TangoLedgerEntry = {
  entry_id: string;
  attempt_id: string;
  status: "PENDING" | "COMMITTED" | "ROLLED_BACK" | "PLAY_FEE";
  amount: number;
};

export type TangoLedger = {
  currency_symbol: "$";
  spendable_dollars: number;
  committed_dollars: number;
  pending_dollars: number;
  play_cost_dollars: number;
  flag_cost_dollars: number;
  entries: TangoLedgerEntry[];
};

export type TangoStatus = {
  puzzle: {
    size: number;
    values: {
      empty: 0;
      sun: 1;
      moon: 2;
    };
    fixed_cells: TangoFixedCell[];
    initial_grid: TangoGrid;
  };
  ledger: TangoLedger;
  latest_attempt_state: "idle" | "pending" | "validating" | "accepted" | "rejected" | "error";
};

export type DownloadStageKey = "stage1" | "stage2" | "stage3";

export type TangoSubmitResponse =
  | {
      result: "accepted";
      dollars_awarded: number;
      attempt_id: string;
    }
  | {
      error: "invalid_grid" | "validation_error" | "too_many_submissions";
      message: string;
      attempt_id?: string;
    };

export type TangoBuyFlagResponse =
  | {
      result: "win";
      flag: string;
    }
  | {
      error: "not_enough_credits";
      message: string;
    };
