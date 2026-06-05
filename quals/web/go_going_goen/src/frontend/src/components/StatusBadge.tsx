import type { JSX } from "react";

type StatusBadgeProps = {
  tone: "active" | "muted" | "success" | "warning";
  children: JSX.Element | string;
};

export const StatusBadge = ({ tone, children }: StatusBadgeProps): JSX.Element => {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
};
