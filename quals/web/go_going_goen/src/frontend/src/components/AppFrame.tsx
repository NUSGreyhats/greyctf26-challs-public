import { type JSX } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faServer } from "@fortawesome/free-solid-svg-icons";
import { Link, NavLink, Outlet } from "react-router-dom";

import { stageMeta, stageOrder } from "../config";
import { StatusBadge } from "./StatusBadge";
import type { ProgressResponse, SessionInfo, StageSlug } from "../types";

type AppFrameProps = {
  session: SessionInfo | null;
  progress: ProgressResponse | null;
};

function isUnlocked(progress: ProgressResponse | null, stage: StageSlug) {
  if (!progress) {
    return false;
  }
  if (stage === "pinpoint") {
    return true;
  }
  if (stage === "queens") {
    return progress.stage1.cleared;
  }
  return progress.stage2.cleared;
}

export const AppFrame = ({
  session,
  progress,
}: AppFrameProps): JSX.Element => {
  function canAccessStage(stage: StageSlug) {
    if (!session) {
      return false;
    }
    return isUnlocked(progress, stage);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <Link to="/" className="brand-link">
            <h1>Go Going Goen</h1>
          </Link>
          <p className="session-label">Not affiliated with or endorsed by LinkedIn</p>
        </div>
        <div className="session-box">
          <div>
            <p className="session-label">Session</p>
            <strong>{session ? "Connected" : "Not connected"}</strong>
          </div>
          <StatusBadge tone={session ? "success" : "muted"}>
            <>
              {session ? "Connected" : "Not connected"}
              <FontAwesomeIcon icon={faServer} className="button-icon" />
            </>
          </StatusBadge>
        </div>
      </header>

      <div className="layout">
        <aside className="rail">
          <div className="rail-head">
            <NavLink to="/" className="rail-meta-link" end>
              Overview
            </NavLink>
            <NavLink to="/progress" className="rail-meta-link">
              Progress
            </NavLink>
          </div>
          <ul className="progress-tree" aria-label="Stage progress">
            {stageOrder.map((stage) => {
              const meta = stageMeta[stage];
              const unlocked = canAccessStage(stage);
              const cleared =
                stage === "pinpoint"
                  ? Boolean(progress?.stage1.cleared)
                  : stage === "queens"
                    ? Boolean(progress?.stage2.cleared)
                    : Boolean(progress?.stage3.cleared);
              return (
                <li key={stage} className="tree-node">
                  <NavLink to={meta.path} className="tree-link">
                    <span
                      className={[
                        "tree-marker",
                        cleared ? "tree-marker--cleared" : unlocked ? "tree-marker--open" : "tree-marker--locked",
                      ].join(" ")}
                    />
                    <span className="tree-copy">
                      <span className="tree-stage">Stage {meta.index}</span>
                      <span>{meta.title}</span>
                      <span className="tree-state">
                        {cleared ? "clear" : unlocked ? "open" : "locked"}
                      </span>
                    </span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </aside>

        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
