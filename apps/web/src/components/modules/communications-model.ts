/**
 * RECON OS — communications presentation model (pure).
 *
 * Decides how CommunicationsSection presents its manual Send control based
 * on AUTOMATIC_COMMUNICATIONS_ENABLED (echoed on IntelligenceEnvelope as
 * automatic_communications_enabled — see routers/intelligence.py). Kept
 * JSX-free and dependency-free, same as pipeline-model.ts, so it can be
 * unit-tested without a component-testing framework (none is set up in
 * this project). No backend or delivery-status logic lives here — this
 * only decides which UI state to show.
 */

export type CommunicationsPresentation = {
  mode: "automatic" | "manual";
  headline: string;
  detail: string;
  /** false = the manual Send control should be demoted to a small,
   *  clearly-secondary fallback rather than presented as the primary CTA. */
  showSendAsPrimary: boolean;
};

export function deriveCommunicationsPresentation(
  automaticCommunicationsEnabled: boolean
): CommunicationsPresentation {
  if (automaticCommunicationsEnabled) {
    return {
      mode: "automatic",
      headline: "AUTOMATIC COMMUNICATIONS ENABLED",
      detail:
        "Communications are sent automatically after the appropriate action or recovery event — no manual send is required in normal operation.",
      showSendAsPrimary: false,
    };
  }
  return {
    mode: "manual",
    headline: "AUTOMATIC COMMUNICATIONS DISABLED",
    detail: "Automatic communications are disabled — use the controls below to send manually.",
    showSendAsPrimary: true,
  };
}
