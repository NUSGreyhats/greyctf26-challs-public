import type { JSX } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowRotateLeft } from "@fortawesome/free-solid-svg-icons";
import { StatusBadge } from "../components/StatusBadge";
import type { ProgressResponse } from "../types";

type ProgressPageProps = {
  progress: ProgressResponse;
  onResetAll: () => Promise<void>;
};

export const ProgressPage = ({ progress, onResetAll }: ProgressPageProps): JSX.Element => {
  const unlockRows = [
    { label: "Queens access", unlocked: progress.stage1.cleared },
    { label: "Tango access", unlocked: progress.stage2.cleared },
  ];

  return (
    <section className="stack-lg">
      <div className="section-heading">
        <div>
          <h2>Progress</h2>
        </div>
        <button type="button" onClick={() => void onResetAll()}>
          <span className="button-label">
            <span>Reset All</span>
            <FontAwesomeIcon icon={faArrowRotateLeft} className="button-icon" />
          </span>
        </button>
      </div>

      <div className="panel-grid">
        <article className="card">
          <h3>Clears</h3>
          <ul className="summary-list">
            <li>
              <span>Pinpoint</span>
              <StatusBadge tone={progress.stage1.cleared ? "success" : "muted"}>
                {progress.stage1.cleared ? "cleared" : "pending"}
              </StatusBadge>
            </li>
            <li>
              <span>Queens</span>
              <StatusBadge tone={progress.stage2.cleared ? "success" : "muted"}>
                {progress.stage2.cleared ? "cleared" : "pending"}
              </StatusBadge>
            </li>
            <li>
              <span>Tango</span>
              <StatusBadge tone={progress.stage3.cleared ? "success" : "muted"}>
                {progress.stage3.cleared ? "cleared" : "pending"}
              </StatusBadge>
            </li>
          </ul>
        </article>

        <article className="card">
          <h3>Stage Access</h3>
          <ul className="summary-list">
            {unlockRows.map((row) => (
              <li key={row.label}>
                <span>{row.label}</span>
                <StatusBadge tone={row.unlocked ? "active" : "muted"}>
                  {row.unlocked ? "unlocked" : "locked"}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h3>Download Gates</h3>
          <ul className="summary-list">
            <li>
              <span>Stage 1 source</span>
              <StatusBadge tone={progress.downloads.stage1 ? "active" : "muted"}>
                {progress.downloads.stage1 ? "unlocked" : "locked"}
              </StatusBadge>
            </li>
            <li>
              <span>Stage 2 source</span>
              <StatusBadge tone={progress.downloads.stage2 ? "active" : "muted"}>
                {progress.downloads.stage2 ? "unlocked" : "locked"}
              </StatusBadge>
            </li>
            <li>
              <span>Stage 3 source</span>
              <StatusBadge tone={progress.downloads.stage3 ? "active" : "muted"}>
                {progress.downloads.stage3 ? "unlocked" : "locked"}
              </StatusBadge>
            </li>
          </ul>
        </article>
      </div>
    </section>
  );
};
