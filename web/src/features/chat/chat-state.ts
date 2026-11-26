export type ChatOperation = {
  conversationId: string | null;
  sequence: number;
};

/** Only the latest operation for the same route may update composer state. */
export function operationIsCurrent(
  operation: ChatOperation,
  latestSequence: number,
  currentConversationId: string | null,
  createdConversationId?: string,
): boolean {
  if (operation.sequence !== latestSequence) return false;
  return currentConversationId === operation.conversationId
    || (operation.conversationId === null && currentConversationId === createdConversationId);
}

/** A newly-created id is the same draft route; every other navigation resets it. */
export function preservesDraftRoute(
  previousConversationId: string | null,
  nextConversationId: string | null,
  createdConversationId: string | null,
): boolean {
  return previousConversationId === null
    && nextConversationId !== null
    && nextConversationId === createdConversationId;
}

/** Resolve against the location at completion, not the row's stale render. */
export function archivedConversationRedirect(
  pathname: string,
  search: string,
  archivedId: string,
): string | null {
  if (pathname !== "/app") return null;
  return new URLSearchParams(search).get("conversation") === archivedId ? "/app" : null;
}

export type RunAnnouncement = "started" | "completed" | "failed" | "cancelled";
export type ObservedRun = {
  conversationId: string | null;
  jobId: string | null;
  status: string;
};

const ACTIVE: Record<string, true> = { queued: true, running: true };

function sameRun(previous: ObservedRun, current: ObservedRun): boolean {
  if (previous.conversationId !== current.conversationId) return false;
  if (previous.jobId !== null && current.jobId !== null) {
    return previous.jobId === current.jobId;
  }
  // Conversation creation returns before its job id is known.
  return previous.jobId === null || current.jobId === null;
}

/** Initial historical terminal jobs are silent; live transitions are announced once. */
export function runAnnouncement(
  previous: ObservedRun | null,
  current: ObservedRun,
): RunAnnouncement | null {
  if (ACTIVE[current.status]) {
    return !previous || !sameRun(previous, current) ? "started" : null;
  }
  if (!previous || !sameRun(previous, current) || !ACTIVE[previous.status]) return null;
  if (current.status === "succeeded") return "completed";
  if (current.status === "failed") return "failed";
  if (current.status === "cancelled") return "cancelled";
  return null;
}
