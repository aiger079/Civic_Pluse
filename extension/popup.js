const API_URL = "https://civicpluse.naxiv.com";

document.addEventListener("DOMContentLoaded", async () => {
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");
  const claimInput = document.getElementById("claimInput");
  const verifyBtn = document.getElementById("verifyBtn");
  const resultBox = document.getElementById("resultBox");
  const verdictTag = document.getElementById("verdictTag");
  const confidenceText = document.getElementById("confidenceText");
  const resultSummary = document.getElementById("resultSummary");
  const sourcesContainer = document.getElementById("sourcesContainer");
  const passiveScanToggle = document.getElementById("passiveScanToggle");

  // Load toggle state from storage
  chrome.storage.local.get("civicpulse_passive_scan_enabled", (res) => {
    passiveScanToggle.checked = !!(res && res.civicpulse_passive_scan_enabled);
  });

  passiveScanToggle.addEventListener("change", () => {
    chrome.storage.local.set({
      civicpulse_passive_scan_enabled: passiveScanToggle.checked
    });
  });

  // Check health of engine
  try {
    const res = await fetch(`${API_URL}/health`);
    const data = await res.json();
    if (data.status === "online") {
      statusDot.className = "status-dot";
      statusText.innerText = "Engine Online";
    }
  } catch (err) {
    statusDot.className = "status-dot offline";
    statusText.innerText = "Engine Offline";
  }

  // Handle Verify button
  verifyBtn.addEventListener("click", async () => {
    const text = claimInput.value.trim();
    if (!text) return;

    verifyBtn.innerText = "Analyzing...";
    verifyBtn.disabled = true;

    try {
      const res = await fetch(`${API_URL}/api/fact-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, context: "chrome_popup" })
      });
      const data = await res.json();
      const a = data.analysis;

      resultBox.style.display = "block";
      verdictTag.innerText = a.verdict || "ANALYZED";
      verdictTag.className = "verdict-tag";

      if (a.verdict === "VERIFIED_TRUE") verdictTag.classList.add("tag-true");
      else if (a.verdict === "FABRICATED_HOAX") verdictTag.classList.add("tag-fake");
      else verdictTag.classList.add("tag-rumour");

      const confPct = Math.round((a.confidence !== undefined ? a.confidence : 0.35) * 100);
      confidenceText.innerText = `Confidence: ${confPct}%`;

      const providerName = a.provider_used === "gemini"
        ? "Google Gemini"
        : a.provider_used === "groq"
          ? "Groq"
          : "live search";
      const evidenceNote = a.evidence_status === "LIVE_SEARCH_RESULTS_UNVERIFIED"
        ? `Live web search via ${providerName} was used; the returned pages and verdict still need human review.`
        : a.evidence_status === "SEARCH_UNAVAILABLE"
          ? "Live search providers were unavailable, so no verdict was produced."
          : "Preliminary assessment; verify important claims with primary sources.";
      resultSummary.innerText = `${a.summary || a.explanation || ""}\n\n${evidenceNote}`;

      if (a.sources && a.sources.length > 0) {
        sourcesContainer.style.display = "block";
        sourcesContainer.textContent = "";
        const titleSpan = document.createElement("strong");
        titleSpan.textContent = a.search_performed
          ? `📑 Live search pages from ${providerName} (check relevance): `
          : "📑 Suggested references: ";
        sourcesContainer.appendChild(titleSpan);

        a.sources.forEach((s, idx) => {
          let safeUrl;
          try {
            const parsed = new URL(s.url);
            if (parsed.protocol !== "https:" || !parsed.hostname || parsed.pathname === "/" || parsed.username || parsed.password) return;
            safeUrl = parsed.href;
          } catch {
            return;
          }
          if (idx > 0) sourcesContainer.appendChild(document.createTextNode(" | "));
          const link = document.createElement("a");
          link.href = safeUrl;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = s.title || "Reference";
          link.style.color = "#60a5fa";
          link.style.textDecoration = "none";
          sourcesContainer.appendChild(link);
        });
      } else {
        sourcesContainer.style.display = "none";
      }

    } catch (err) {
      alert("Error: Ensure backend is running at " + API_URL);
    } finally {
      verifyBtn.innerText = "⚡ Verify Claim";
      verifyBtn.disabled = false;
    }
  });
});
