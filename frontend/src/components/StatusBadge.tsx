import clsx from "clsx";

const COLORS: Record<string, string> = {
  pending: "status-pending",
  planning: "status-planning",
  executing: "status-executing",
  awaiting_approval: "status-awaiting_approval",
  succeeded: "status-succeeded",
  failed: "status-failed",
  cancelled: "status-cancelled",
  approved: "status-approved",
  rejected: "status-rejected",
  expired: "status-expired",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = COLORS[status] ?? "status-pending";
  return <span className={clsx("badge status-badge", cls)}>{status.replaceAll("_", " ")}</span>;
}
