import { useEffect, useState, type CSSProperties, type FormEvent, type JSX } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowRotateLeft,
  faChessQueen,
  faCircleQuestion,
  faCoins,
  faDownload,
  faLock,
  faMoon,
  faPaperPlane,
  faRotate,
  faSun,
} from "@fortawesome/free-solid-svg-icons";

import { POLL_INTERVAL_MS, stageMeta } from "../config";
import { Modal } from "../components/Modal";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import type {
  DownloadStageKey,
  PinpointStatus,
  ProgressResponse,
  QueensBoardResponse,
  SessionInfo,
  StageSlug,
  TangoCell,
  TangoGrid,
  TangoStatus,
} from "../types";

type StagePageProps = {
  stage: StageSlug;
  progress: ProgressResponse;
  session: SessionInfo | null;
  onRefreshProgress: () => Promise<void>;
};

function isStageUnlocked(stage: StageSlug, progress: ProgressResponse) {
  if (stage === "pinpoint") {
    return true;
  }
  if (stage === "queens") {
    return progress.stage1.cleared;
  }
  return progress.stage2.cleared;
}

function isFixedTangoCell(status: TangoStatus, row: number, col: number) {
  return status.puzzle.fixed_cells.some((cell) => cell.row === row && cell.col === col);
}

function tangoCellLabel(value: TangoCell) {
  if (value === 1) {
    return "sun";
  }
  if (value === 2) {
    return "moon";
  }
  return "blank";
}

function renderTangoCellIcon(value: TangoCell) {
  if (value === 1) {
    return <FontAwesomeIcon icon={faSun} className="tango-board__icon" />;
  }
  if (value === 2) {
    return <FontAwesomeIcon icon={faMoon} className="tango-board__icon" />;
  }
  return <span className="tango-board__blank" aria-hidden="true" />;
}

export const StagePage = ({ stage, progress, session, onRefreshProgress }: StagePageProps): JSX.Element => {
  const [howToOpen, setHowToOpen] = useState(false);
  const [pinpoint, setPinpoint] = useState<PinpointStatus | null>(null);
  const [queens, setQueens] = useState<QueensBoardResponse | null>(null);
  const [tangoStatus, setTangoStatus] = useState<TangoStatus | null>(null);
  const [tangoGrid, setTangoGrid] = useState<TangoGrid | null>(null);
  const [guess, setGuess] = useState("");
  const [isValidatingQueens, setIsValidatingQueens] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [pinpointFeedback, setPinpointFeedback] = useState<{ tone: "muted" | "success" | "warning"; text: string } | null>(
    null,
  );
  const unlocked = Boolean(session) && isStageUnlocked(stage, progress);
  const meta = stageMeta[stage];
  const sourceStage: DownloadStageKey = stage === "pinpoint" ? "stage1" : stage === "queens" ? "stage2" : "stage3";
  const sourceUnlocked =
    sourceStage === "stage1"
      ? progress.downloads.stage1
      : sourceStage === "stage2"
        ? progress.downloads.stage2
        : progress.downloads.stage3;

  async function loadStageState() {
    if (stage === "pinpoint") {
      setPinpoint(await api.getPinpointStatus());
    }
    if (stage === "queens") {
      setQueens(await api.getQueensBoard());
    }
    if (stage === "tango") {
      const status = await api.getTangoStatus();
      setTangoStatus(status);
      setTangoGrid((current) => current ?? (status.puzzle.initial_grid.map((row) => [...row]) as TangoGrid));
    }
  }

  useEffect(() => {
    if (!unlocked) {
      return;
    }
    void loadStageState();
  }, [stage, unlocked]);

  useEffect(() => {
    if (stage !== "queens") {
      return;
    }

    if (queens?.submission.status !== "validating" && !isValidatingQueens) {
      return;
    }

    const interval = window.setInterval(() => {
      void api.getQueensBoard().then(setQueens);
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [stage, queens?.submission.status, isValidatingQueens]);

  useEffect(() => {
    if (stage !== "tango" || tangoStatus?.latest_attempt_state !== "validating") {
      return;
    }

    const interval = window.setInterval(() => {
      void api.getTangoStatus().then(setTangoStatus);
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [stage, tangoStatus?.latest_attempt_state]);

  function handleSourceDownload(stageKey: DownloadStageKey) {
    window.location.href = api.getDownloadUrl(stageKey);
  }

  async function handleStageReset() {
    await api.resetStage(stage);
    if (stage === "tango") {
      const status = await api.getTangoStatus();
      setTangoStatus(status);
      setTangoGrid(status.puzzle.initial_grid.map((row) => [...row]) as TangoGrid);
      await onRefreshProgress();
      setFlash(`${meta.title} state reset.`);
      return;
    }
    await loadStageState();
    await onRefreshProgress();
    if (stage === "pinpoint") {
      setFlash(null);
      setPinpointFeedback(null);
      return;
    }
    setFlash(`${meta.title} state reset.`);
  }

  async function handleGuessSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const response = await api.submitGuess(guess);
      setFlash(null);
      setGuess("");
      await loadStageState();
      await onRefreshProgress();
      setPinpointFeedback({
        tone: response.result === "correct" ? "success" : "muted",
        text: response.result === "correct" ? "Stage 2 unlocked." : "Guess submitted.",
      });
    } catch (error) {
      setFlash(null);
      const message = error instanceof Error ? error.message : "Could not submit guess.";
      setPinpointFeedback({ tone: "warning", text: message });
    }
  }

  async function handleQueenSquareClick(row: number, col: number, occupied: boolean) {
    if (occupied) {
      await api.removeQueen(row, col);
    } else {
      await api.addQueen(row, col);
    }
    setFlash(null);
    await loadStageState();
  }

  async function handleQueensSubmit() {
    setIsValidatingQueens(true);
    await api.submitQueens();
    setIsValidatingQueens(false);
    await loadStageState();
    await onRefreshProgress();
  }

  function handleTangoCellClick(row: number, col: number) {
    if (!tangoStatus || !tangoGrid || isFixedTangoCell(tangoStatus, row, col)) {
      return;
    }
    setTangoGrid((current) => {
      if (!current) {
        return current;
      }
      return current.map((line, lineIndex) =>
        lineIndex === row
          ? line.map((cell, cellIndex) => (cellIndex === col ? (((cell + 1) % 3) as TangoCell) : cell))
          : [...line],
      ) as TangoGrid;
    });
  }

  async function handleTangoSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tangoGrid) {
      return;
    }
    const response = await api.submitTango(tangoGrid);
    await loadStageState();
    await onRefreshProgress();
    setFlash("result" in response ? `$${response.dollars_awarded} credited.` : `${response.message}`);
  }

  async function handleTangoBuyFlag() {
    const response = await api.buyTangoFlag();
    await loadStageState();
    await onRefreshProgress();
    setFlash("result" in response ? `Final flag: ${response.flag}` : response.message);
  }

  async function handleTangoRefreshLedger() {
    const ledger = await api.refreshTangoLedger();
    setTangoStatus((current) => (current ? { ...current, ledger } : current));
    setFlash(
      `Ledger refreshed. Pending credits were settled and spendable balance is now $${ledger.spendable_dollars}.`,
    );
  }

  if (!unlocked) {
    return (
      <section className="stack-lg">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Stage {meta.index}</p>
            <h2>{meta.title}</h2>
          </div>
          <StatusBadge tone="muted">locked</StatusBadge>
        </div>
        <article className="card">
          <p>{meta.shortDescription}</p>
          <p>Clear the prior stage to unlock this stage</p>
        </article>
      </section>
    );
  }

  return (
    <section className="stack-lg">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Stage {meta.index}</p>
          <h2>{meta.title}</h2>
        </div>
        <div className="button-row stage-actions">
          <button type="button" className="ghost-button" onClick={() => setHowToOpen(true)}>
            <span className="button-label">
              <span>How to Play</span>
              <FontAwesomeIcon icon={faCircleQuestion} className="button-icon" />
            </span>
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={!sourceUnlocked}
            onClick={() => handleSourceDownload(sourceStage)}
          >
            <span className="button-label">
              <span>{sourceUnlocked ? "Source" : "Source Locked"}</span>
              <FontAwesomeIcon icon={sourceUnlocked ? faDownload : faLock} className="button-icon" />
            </span>
          </button>
          <button type="button" onClick={() => void handleStageReset()}>
            <span className="button-label">
              <span>Reset</span>
              <FontAwesomeIcon icon={faArrowRotateLeft} className="button-icon" />
            </span>
          </button>
        </div>
      </div>

      {flash ? <p className="flash-banner">{flash}</p> : null}

      <div className="stage-grid">
        <article className="card game-panel">{renderGamePanel()}</article>
        <aside className="card status-panel">
          <div className="status-panel__header">
            <h3>Status</h3>
            {stage === "tango" ? (
              <button
                type="button"
                className="ghost-button icon-button"
                title="Refresh ledger (settles pending credits)"
                aria-label="Refresh ledger (settles pending credits)"
                onClick={() => void handleTangoRefreshLedger()}
              >
                <FontAwesomeIcon icon={faRotate} className="button-icon" />
              </button>
            ) : null}
          </div>
          {renderStatusPanel()}
        </aside>
      </div>

      <Modal title={`${meta.title}: How to Play`} open={howToOpen} onClose={() => setHowToOpen(false)}>
        <ul className="modal-list">
          {meta.modalBody.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Modal>
    </section>
  );

  function renderGamePanel() {
    if (stage === "pinpoint" && pinpoint) {
      const recentGuesses = pinpoint.recent_guesses ?? [];
      return (
        <div className="stack-md">
          <div className="guess-history">
            {[...recentGuesses].reverse().map((entry, index) => (
              <div key={`${entry ?? "empty"}-${index}`} className={`guess-chip${entry ? "" : " guess-chip--empty"}`}>
                {entry ?? "\u00A0"}
              </div>
            ))}
          </div>
          <form className="stack-sm" onSubmit={(event) => void handleGuessSubmit(event)}>
            <input
              value={guess}
              onChange={(event) => setGuess(event.target.value)}
              placeholder="Guess the 5-letter word"
              maxLength={5}
            />
            {pinpointFeedback ? <p className={`inline-feedback inline-feedback--${pinpointFeedback.tone}`}>{pinpointFeedback.text}</p> : null}
            <button type="submit">
              <span className="button-label">
                <span>Submit</span>
                <FontAwesomeIcon icon={faPaperPlane} className="button-icon" />
              </span>
            </button>
          </form>
        </div>
      );
    }

    if (stage === "queens" && queens) {
      const occupiedSquares = new Set(queens.queens.map((queen) => `${queen.row}-${queen.col}`));
      const boardCells = Array.from({ length: queens.size * queens.size }, (_, index) => {
        const row = Math.floor(index / queens.size);
        const col = index % queens.size;
        const occupied = occupiedSquares.has(`${row}-${col}`);
        return { row, col, occupied };
      });

      return (
        <div className="stack-md">
          <div
            className="queens-board"
            style={{ "--queens-board-size": queens.size } as CSSProperties}
            role="grid"
            aria-label={`${queens.size} by ${queens.size} queens board`}
          >
            {boardCells.map((cell) => (
              <button
                type="button"
                key={`${cell.row}-${cell.col}`}
                className={[
                  "queens-board__cell",
                  cell.occupied ? "queens-board__cell--occupied" : "",
                ].join(" ")}
                role="gridcell"
                aria-pressed={cell.occupied}
                aria-label={
                  cell.occupied
                    ? `Row ${cell.row}, column ${cell.col}, queen`
                    : `Row ${cell.row}, column ${cell.col}, empty`
                }
                title={
                  cell.occupied
                    ? `row ${cell.row}, col ${cell.col}: queen`
                    : `row ${cell.row}, col ${cell.col}`
                }
                onClick={() => void handleQueenSquareClick(cell.row, cell.col, cell.occupied)}
              >
                {cell.occupied ? <FontAwesomeIcon icon={faChessQueen} className="queens-board__queen" /> : null}
              </button>
            ))}
          </div>
          <button type="button" disabled={isValidatingQueens} onClick={() => void handleQueensSubmit()}>
            {isValidatingQueens ? (
              <span className="button-label">
                <span>Validating...</span>
                <FontAwesomeIcon icon={faRotate} className="button-icon button-icon--spin" />
              </span>
            ) : (
              <span className="button-label">
                <span>Submit Board</span>
                <FontAwesomeIcon icon={faPaperPlane} className="button-icon" />
              </span>
            )}
          </button>
        </div>
      );
    }

    if (stage === "tango" && tangoStatus && tangoGrid) {
      const boardCells = tangoGrid.flatMap((rowValues, row) =>
        rowValues.map((value, col) => ({
          row,
          col,
          value,
          fixed: isFixedTangoCell(tangoStatus, row, col),
        })),
      );
      return (
        <div className="stack-md">
          <form className="stack-sm" onSubmit={(event) => void handleTangoSubmit(event)}>
            <div
              className="tango-board"
              style={{ "--tango-board-size": tangoStatus.puzzle.size } as CSSProperties}
              role="grid"
              aria-label="Tango grid"
            >
              {boardCells.map((cell) => (
                <button
                  type="button"
                  key={`${cell.row}-${cell.col}`}
                  className={[
                    "tango-board__cell",
                    cell.value === 1 ? "tango-board__cell--sun" : "",
                    cell.value === 2 ? "tango-board__cell--moon" : "",
                    cell.fixed ? "tango-board__cell--fixed" : "",
                  ].join(" ")}
                  role="gridcell"
                  aria-label={`Row ${cell.row + 1}, column ${cell.col + 1}, ${tangoCellLabel(cell.value)}${cell.fixed ? ", fixed" : ""}`}
                  title={`${cell.fixed ? "fixed clue" : "editable"}: ${tangoCellLabel(cell.value)}`}
                  onClick={() => handleTangoCellClick(cell.row, cell.col)}
                >
                  {renderTangoCellIcon(cell.value)}
                </button>
              ))}
            </div>
            <div className="button-row">
              <button type="submit">
                <span className="button-label">
                  <span>Submit Grid</span>
                  <FontAwesomeIcon icon={faPaperPlane} className="button-icon" />
                </span>
              </button>
              <button type="button" onClick={() => void handleTangoBuyFlag()}>
                <span className="button-label">
                  <span>Buy Flag</span>
                  <FontAwesomeIcon icon={faCoins} className="button-icon" />
                </span>
              </button>
            </div>
          </form>
        </div>
      );
    }

    return <p>Loading stage shell...</p>;
  }

  function renderStatusPanel() {
    if (stage === "pinpoint" && pinpoint) {
      return (
        <ul className="summary-list">
          <li>
            <span>Remaining guesses</span>
            <strong>{pinpoint.remaining_guesses}</strong>
          </li>
          <li>
            <span>Last result</span>
            <StatusBadge tone={pinpoint.last_result === "correct" ? "success" : "muted"}>
              {pinpoint.last_result ?? "none"}
            </StatusBadge>
          </li>
        </ul>
      );
    }

    if (stage === "queens" && queens) {
      return (
        <ul className="summary-list">
          <li>
            <span>Total queens</span>
            <strong>{queens.total_queens}</strong>
          </li>
          <li>
            <span>Submission status</span>
            <StatusBadge tone={queens.submission.status === "won" ? "success" : "active"}>
              {queens.submission.status}
            </StatusBadge>
          </li>
          <li>
            <span>Progress</span>
            <strong>{queens.submission.progress_pct}%</strong>
          </li>
          <li>
            <span>Last submit result</span>
            <strong>{queens.submission.last_result ?? "none"}</strong>
          </li>
        </ul>
      );
    }

    if (stage === "tango" && tangoStatus) {
      return (
        <ul className="summary-list">
          <li>
            <span>Spendable</span>
            <strong>
              {tangoStatus.ledger.currency_symbol}
              {tangoStatus.ledger.spendable_dollars} / {tangoStatus.ledger.currency_symbol}
              {tangoStatus.ledger.flag_cost_dollars}
            </strong>
          </li>
          <li>
            <span>Committed</span>
            <strong>{tangoStatus.ledger.currency_symbol}{tangoStatus.ledger.committed_dollars}</strong>
          </li>
          <li>
            <span>Pending</span>
            <strong>{tangoStatus.ledger.currency_symbol}{tangoStatus.ledger.pending_dollars}</strong>
          </li>
          <li>
            <span>Play cost</span>
            <strong>{tangoStatus.ledger.currency_symbol}{tangoStatus.ledger.play_cost_dollars}</strong>
          </li>
          <li>
            <span>Latest attempt</span>
            <StatusBadge tone={tangoStatus.latest_attempt_state === "accepted" ? "success" : tangoStatus.latest_attempt_state === "error" ? "warning" : "active"}>
              {tangoStatus.latest_attempt_state}
            </StatusBadge>
          </li>
          <li>
            <span>Ledger entries</span>
            <strong>{tangoStatus.ledger.entries.length}</strong>
          </li>
        </ul>
      );
    }

    return <p>Loading status...</p>;
  }
};
