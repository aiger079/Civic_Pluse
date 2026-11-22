// Shared by the popup and the on-page result dialog.
function describeCivicPulseEvidence(analysis) {
  switch (analysis.evidence_status) {
    case "SEARCH_UNAVAILABLE":
      return {
        label: "Live search unavailable",
        message: "CivicPulse could not complete a live search for this claim.",
        advice: "Try again later or check the original source directly."
      };
    case "NO_USABLE_SEARCH_SOURCES":
      if (Array.isArray(analysis.search_results) && analysis.search_results.length > 0) {
        return {
          label: "Unconfirmed after web search",
          advice: "Check an official source for the specific detail in the claim."
        };
      }
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
    case "tavily": return "Web search results (Tavily)";
    case "wikimedia": return "Wikipedia articles (check relevance)";
    case "gemini": return "Google Gemini Search sources (check relevance)";
    case "groq": return "Groq live search sources (check relevance)";
    default: return analysis.search_performed
      ? "Live search sources (check relevance)"
      : "Suggested references";
  }
}

function getCivicPulseSourceList(analysis) {
  if (Array.isArray(analysis.sources) && analysis.sources.length > 0) {
    return { label: labelCivicPulseSources(analysis), links: analysis.sources };
  }
  return {
    label: "Related pages for further review",
    links: Array.isArray(analysis.search_results) ? analysis.search_results : []
  };
}
