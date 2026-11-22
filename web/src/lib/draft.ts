/** Clear only the text that was sent; anything typed during the request stays. */
export function clearSubmittedDraft(current: string, submitted: string): string {
  return current === submitted ? "" : current;
}
