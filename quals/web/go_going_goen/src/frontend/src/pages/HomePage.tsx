import type { JSX } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faLock, faPlay } from "@fortawesome/free-solid-svg-icons";
import { Link } from "react-router-dom";

import { stageMeta, stageOrder } from "../config";
import { StatusBadge } from "../components/StatusBadge";
import type { ProgressResponse, SessionInfo, StageSlug } from "../types";

type HomePageProps = {
  progress: ProgressResponse;
  session: SessionInfo | null;
};

function isUnlocked(progress: ProgressResponse, stage: StageSlug) {
  if (stage === "pinpoint") {
    return true;
  }
  if (stage === "queens") {
    return progress.stage1.cleared;
  }
  return progress.stage2.cleared;
}

export const HomePage = ({ progress, session }: HomePageProps): JSX.Element => {
  function canAccessStage(stage: StageSlug) {
    if (!session) {
      return false;
    }
    return isUnlocked(progress, stage);
  }

  return (
    <section className="stack-lg">
      <div className="card-grid">
        {stageOrder.map((stage) => {
          const meta = stageMeta[stage];
          const unlocked = canAccessStage(stage);
          const cleared =
            stage === "pinpoint"
              ? progress.stage1.cleared
              : stage === "queens"
                ? progress.stage2.cleared
                : progress.stage3.cleared;

          return (
            <article key={stage} className="card challenge-card">
              <div className="card-heading">
                <div>
                  <p className="card-kicker">Stage {meta.index}</p>
                  <h3>{meta.title}</h3>
                </div>
                <StatusBadge tone={cleared ? "success" : unlocked ? "active" : "muted"}>
                  {cleared ? "cleared" : unlocked ? "playable" : "locked"}
                </StatusBadge>
              </div>
              <p>{meta.shortDescription}</p>
              <div className="button-row">
                <Link className="button-link" to={meta.path}>
                  <span className="button-label">
                    <span>{unlocked ? "Play" : "Locked"}</span>
                    <FontAwesomeIcon
                      icon={unlocked ? faPlay : faLock}
                      className="button-icon"
                    />
                  </span>
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
};
