import type { JSX } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppFrame } from "./components/AppFrame";
import { useShellData } from "./hooks/useShellData";
import { HomePage } from "./pages/HomePage";
import { ProgressPage } from "./pages/ProgressPage";
import { StagePage } from "./pages/StagePage";

export const App = (): JSX.Element => {
  const shell = useShellData();

  if (shell.loading) {
    return <div className="screen-message">Loading challenge shell...</div>;
  }

  if (shell.error && !shell.progress) {
    return (
      <div className="screen-message">
        <p>{shell.error}</p>
        <button type="button" onClick={() => void shell.refresh()}>
          Retry
        </button>
      </div>
    );
  }

  if (shell.needsAuth || !shell.progress) {
    return (
      <div className="screen-message">
        <h1>Go Going Goen</h1>
        <p>Open this challenge from CTFd to receive your team link.</p>
        <p className="session-label">Not affiliated with or endorsed by LinkedIn</p>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        element={
          <AppFrame
            session={shell.session}
            progress={shell.progress}
          />
        }
      >
        <Route path="/" element={<HomePage progress={shell.progress} session={shell.session} />} />
        <Route
          path="/progress"
          element={<ProgressPage progress={shell.progress} onResetAll={shell.resetAll} />}
        />
        <Route
          path="/play/pinpoint"
          element={
            <StagePage
              stage="pinpoint"
              progress={shell.progress}
              session={shell.session}
              onRefreshProgress={shell.refresh}
            />
          }
        />
        <Route
          path="/play/queens"
          element={
            <StagePage
              stage="queens"
              progress={shell.progress}
              session={shell.session}
              onRefreshProgress={shell.refresh}
            />
          }
        />
        <Route
          path="/play/tango"
          element={
            <StagePage
              stage="tango"
              progress={shell.progress}
              session={shell.session}
              onRefreshProgress={shell.refresh}
            />
          }
        />
        <Route path="/play/crossclimb" element={<Navigate to="/play/tango" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
};
