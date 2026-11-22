const API_URL = "https://civic-pluse-sooty.vercel.app";

document.addEventListener("DOMContentLoaded", () => {
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
    const enabledByDefault = !res || res.civicpulse_passive_scan_enabled === undefined;
    passiveScanToggle.checked = enabledByDefault || res.civicpulse_passive_scan_enabled === true;
    if (enabledByDefault) {
      chrome.storage.local.set({ civicpulse_passive_scan_enabled: true });
    }
  });

  passiveScanToggle.addEventListener("change", () => {
    chrome.storage.local.set({
      civicpulse_passive_scan_enabled: passiveScanToggle.checked
    });
  });

  fetch(`${API_URL}/health`)
    .then(res => res.json())
    .then(data => {
      if (data.status !== "online") throw new Error("Backend unavailable");
      statusDot.className = "status-dot";
      statusText.innerText = "Engine Online";
    })
    .catch(() => {
      statusDot.className = "status-dot offline";
      statusText.innerText = "Engine Offline";
    });

  function showRequestError(label, message) {
    resultBox.style.display = "block";
    verdictTag.innerText = label;
    verdictTag.className = "verdict-tag tag-neutral";
    confidenceText.innerText = "";
    resultSummary.innerText = message;
    sourcesContainer.style.display = "none";
  }

  // Handle Verify button
  verifyBtn.addEventListener("click", async () => {
    const text = claimInput.value.trim();
    if (text.length < 5 || text.length > 1500) {
      showRequestError("Check claim length", "Enter a claim between 5 and 1,500 characters.");
      return;
    }

    verifyBtn.innerText = "Analyzing...";
    verifyBtn.disabled = true;
    resultBox.style.display = "none";

    try {
      const res = await fetch(`${API_URL}/api/fact-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          context: "chrome_popup",
          allow_public_reference_search: true,
          allow_web_search: true
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 429) {
          showRequestError("Request limit reached", "Wait a minute before checking this claim again.");
        } else {
          showRequestError("Check failed", typeof data.detail === "string" ? data.detail : "Try again in a moment.");
        }
        return;
      }
      const a = data.analysis;
      if (!a || typeof a.verdict !== "string") {
        showRequestError("Check failed", "CivicPulse returned an incomplete response. Try again in a moment.");
        return;
      }
      const evidence = describeCivicPulseEvidence(a);

      resultBox.style.display = "block";
      verdictTag.innerText = evidence?.label || a.verdict;
      verdictTag.className = "verdict-tag";

      if (evidence) verdictTag.classList.add("tag-neutral");
      else if (a.verdict === "VERIFIED_TRUE") verdictTag.classList.add("tag-true");
      else if (a.verdict === "FABRICATED_HOAX") verdictTag.classList.add("tag-fake");
      else verdictTag.classList.add("tag-rumour");

      confidenceText.innerText = !evidence && Number.isFinite(a.confidence)
        ? `Confidence: ${Math.round(a.confidence * 100)}%`
        : "";

      if (evidence) {
        const details = evidence.message ? [evidence.message] : [a.summary, a.explanation];
        resultSummary.innerText = [...details, evidence.advice]
          .filter(Boolean).join("\n\n");
      } else {
        resultSummary.innerText = [a.summary || a.explanation, "Review the evidence before relying on this preliminary assessment."]
          .filter(Boolean).join("\n\n");
      }

      const sourceList = getCivicPulseSourceList(a);
      if (sourceList.links.length > 0) {
        sourcesContainer.style.display = "block";
        sourcesContainer.textContent = "";
        const titleSpan = document.createElement("strong");
        titleSpan.textContent = `📑 ${sourceList.label}: `;
        sourcesContainer.appendChild(titleSpan);

        sourceList.links.forEach((s, idx) => {
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

    } catch {
      showRequestError("Connection failed", "CivicPulse could not be reached. Check your connection and try again.");
    } finally {
      verifyBtn.innerText = "⚡ Verify Claim";
      verifyBtn.disabled = false;
    }
  });
});
