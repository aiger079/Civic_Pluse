// Shared by the popup and the on-page result dialog.
function describeCivicPulseEvidence(analysis) {
  switch (analysis.evidence_status) {
    case "SEARCH_UNAVAILABLE":
      return {
        label: "Live search unavailable",
        advice: "Try again in a moment or check a trusted primary source."
      };
    case "NO_USABLE_SEARCH_SOURCES":
      return {
        label: "No usable sources",
        advice: "Try checking one specific claim. Add names, a date, or a location if you know them."
      };
    default:
      return analysis.verdict === "INSUFFICIENT_EVIDENCE"
        ? {
          label: "Insufficient evidence",
          advice: "Review any linked sources and look for independent evidence that addresses the claim."
        }
        : null;
  }
}

function labelCivicPulseSources(analysis) {
  switch (analysis.provider_used) {
    case "wikimedia": return "Wikipedia articles (check relevance)";
    case "gemini": return "Google Gemini Search sources (check relevance)";
    case "groq": return "Groq live search sources (check relevance)";
    default: return analysis.search_performed
      ? "Live search sources (check relevance)"
      : "Suggested references";
  }
}
