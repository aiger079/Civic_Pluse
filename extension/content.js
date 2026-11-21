// CivicPulse Content Script — Preliminary Fact-Check Assistant & Privacy-Gated Scanner

(function() {
  console.log("🛡️ CivicPulse Fact-Checker loaded on:", window.location.hostname);

  // Inject Modal Container if not present
  function ensureModalContainer() {
    let container = document.getElementById("civicpulse-overlay-root");
    if (!container) {
      container = document.createElement("div");
      container.id = "civicpulse-overlay-root";
      document.body.appendChild(container);
    }
    return container;
  }

  // Show Scanning Modal with Transparency details
  function showScanning(text) {
    const root = ensureModalContainer();
    const domain = window.location.hostname;
    
    // Clear previous
    root.textContent = "";

    const backdrop = document.createElement("div");
    backdrop.className = "civicpulse-modal-backdrop";
    backdrop.id = "civicpulse-backdrop";

    const modal = document.createElement("div");
    modal.className = "civicpulse-modal";

    const header = document.createElement("div");
    header.className = "civicpulse-modal-header";
    header.innerHTML = `
      <div class="civicpulse-brand">
        <span class="civicpulse-logo">🛡️</span>
        <h3>CivicPulse Intelligence</h3>
      </div>
    `;
    const closeBtn = document.createElement("button");
    closeBtn.className = "civicpulse-close-btn";
    closeBtn.innerHTML = "&times;";
    closeBtn.onclick = removeModal;
    header.appendChild(closeBtn);

    const body = document.createElement("div");
    body.className = "civicpulse-modal-body";

    const spinnerBox = document.createElement("div");
    spinnerBox.className = "civicpulse-spinner-box";
    spinnerBox.innerHTML = `
      <div class="civicpulse-spinner"></div>
      <div>
        <p style="font-weight: 600;">Preparing a preliminary model assessment...</p>
        <p style="font-size: 11px; color: #94a3b8; margin-top: 2px;">
          Suggested references are not checked live.
        </p>
      </div>
    `;

    // Transparency Note
    const privacyNote = document.createElement("div");
    privacyNote.className = "civicpulse-privacy-notice";
    privacyNote.innerHTML = `
      <strong>🔒 Data disclosure:</strong> This text and the website domain (<code>${domain}</code>) are sent to the CivicPulse backend. It searches with Groq and may send the claim and domain to Google Gemini Search if Groq is unavailable or returns no usable sources. Cookies, logins, and browsing history are not sent.
    `;

    const quoteEl = document.createElement("p");
    quoteEl.className = "civicpulse-selected-quote";
    quoteEl.textContent = `"${text}"`;

    body.appendChild(spinnerBox);
    body.appendChild(privacyNote);
    body.appendChild(quoteEl);

    modal.appendChild(header);
    modal.appendChild(body);
    backdrop.appendChild(modal);
    root.appendChild(backdrop);

    backdrop.onclick = (e) => {
      if (e.target.id === "civicpulse-backdrop") removeModal();
    };
  }

  // Show Auditable Result Modal
  function showResult(data) {
    const root = ensureModalContainer();
    root.textContent = "";

    const a = data.analysis || {};
    const verdict = a.verdict || "ANALYZED";
    const confPct = Math.round((a.confidence !== undefined ? a.confidence : 0.35) * 100);
    const truthEstimate = a.model_estimate?.truth_score ?? a.truth_score ?? 0.5;
    const falseEstimate = a.model_estimate?.falsehood_score ?? a.falsehood_score ?? 0.5;
    const truthPct = Math.round(Math.max(0, Math.min(1, truthEstimate)) * 100);
    const falsePct = Math.round(Math.max(0, Math.min(1, falseEstimate)) * 100);
    const isUncertain = !!a.uncertainty_state;

    let pillClass = "pill-rumour";
    let verdictIcon = "⚠️";
    if (verdict === "VERIFIED_TRUE") {
      pillClass = "pill-true";
      verdictIcon = "✅";
    } else if (verdict === "FABRICATED_HOAX" || verdict === "DISPUTED_RUMOUR") {
      pillClass = "pill-fake";
      verdictIcon = "🚨";
    }

    const backdrop = document.createElement("div");
    backdrop.className = "civicpulse-modal-backdrop";
    backdrop.id = "civicpulse-backdrop";

    const modal = document.createElement("div");
    modal.className = "civicpulse-modal";

    const header = document.createElement("div");
    header.className = "civicpulse-modal-header";
    header.innerHTML = `
      <div class="civicpulse-brand">
        <span class="civicpulse-logo">${verdictIcon}</span>
        <h3>CivicPulse Auditable Verdict</h3>
      </div>
    `;
    const closeBtn = document.createElement("button");
    closeBtn.className = "civicpulse-close-btn";
    closeBtn.innerHTML = "&times;";
    closeBtn.onclick = removeModal;
    header.appendChild(closeBtn);

    const body = document.createElement("div");
    body.className = "civicpulse-modal-body";

    // Verdict and Confidence
    const topRow = document.createElement("div");
    topRow.style.display = "flex";
    topRow.style.justifyContent = "space-between";
    topRow.style.alignItems = "center";

    const pill = document.createElement("div");
    pill.className = `civicpulse-verdict-pill ${pillClass}`;
    pill.textContent = verdict;

    const confSpan = document.createElement("span");
    confSpan.style.fontSize = "12px";
    confSpan.style.color = "#94a3b8";
    confSpan.style.fontWeight = "600";
    confSpan.textContent = `Confidence: ${confPct}%`;

    topRow.appendChild(pill);
    topRow.appendChild(confSpan);
    body.appendChild(topRow);

    // Uncertainty Warning if evidence missing
    if (isUncertain) {
      const warnBox = document.createElement("div");
      warnBox.className = "civicpulse-uncertainty-box";
      warnBox.innerHTML = `
        <strong>⚠️ Preliminary result:</strong> Live search may have retrieved sources, but the verdict and source relevance can still be wrong. Confirm important claims with primary sources.
      `;
      body.appendChild(warnBox);
    }

    // Probability Meters
    const meters = document.createElement("div");
    meters.className = "civicpulse-meter-group";
    meters.innerHTML = `
      <div class="civicpulse-meter-label">
        <span>Truth Probability</span>
        <span><strong>${truthPct}%</strong></span>
      </div>
      <div class="civicpulse-bar-bg">
        <div class="civicpulse-bar-fill truth" style="width: ${truthPct}%;"></div>
      </div>
      <div class="civicpulse-meter-label" style="margin-top: 6px;">
        <span>Falsehood / Hoax Probability</span>
        <span><strong>${falsePct}%</strong></span>
      </div>
      <div class="civicpulse-bar-bg">
        <div class="civicpulse-bar-fill fake" style="width: ${falsePct}%;"></div>
      </div>
    `;
    body.appendChild(meters);

    // Summary & Explanation (Rendered safely via textContent)
    const summaryEl = document.createElement("div");
    summaryEl.className = "civicpulse-summary";
    summaryEl.textContent = a.summary || "";
    body.appendChild(summaryEl);

    const explanationEl = document.createElement("div");
    explanationEl.className = "civicpulse-explanation";
    explanationEl.textContent = a.explanation || "";
    body.appendChild(explanationEl);

    // Sources & Citations
    if (a.sources && a.sources.length > 0) {
      const sourcesBox = document.createElement("div");
      sourcesBox.className = "civicpulse-sources-box";
      
      const sourcesHeading = document.createElement("h5");
      sourcesHeading.textContent = a.search_performed
        ? "📑 Live search pages (check relevance):"
        : "📑 Suggested references:";
      sourcesHeading.style.fontSize = "11.5px";
      sourcesHeading.style.color = "#93c5fd";
      sourcesHeading.style.marginBottom = "6px";
      sourcesBox.appendChild(sourcesHeading);

      const sourcesList = document.createElement("ul");
      sourcesList.style.listStyle = "none";
      sourcesList.style.padding = "0";

      for (const s of a.sources) {
        let safeUrl;
        try {
          const parsed = new URL(s.url);
          if (parsed.protocol !== "https:" || !parsed.hostname || parsed.pathname === "/" || parsed.username || parsed.password) continue;
          safeUrl = parsed.href;
        } catch {
          continue;
        }
        const li = document.createElement("li");
        li.style.marginBottom = "4px";
        li.style.fontSize = "11px";

        const aTag = document.createElement("a");
        aTag.href = safeUrl;
        aTag.target = "_blank";
        aTag.rel = "noopener noreferrer";
        aTag.textContent = `🔗 ${s.title || s.url}`;
        aTag.style.color = "#60a5fa";
        aTag.style.textDecoration = "none";

        li.appendChild(aTag);
        sourcesList.appendChild(li);
      }
      sourcesBox.appendChild(sourcesList);
      body.appendChild(sourcesBox);
    }

    // Actionable Advice
    if (a.actionable_advice) {
      const adviceEl = document.createElement("div");
      adviceEl.className = "civicpulse-advice";
      adviceEl.textContent = `💡 Actionable Advice: ${a.actionable_advice}`;
      body.appendChild(adviceEl);
    }

    modal.appendChild(header);
    modal.appendChild(body);
    backdrop.appendChild(modal);
    root.appendChild(backdrop);

    backdrop.onclick = (e) => {
      if (e.target.id === "civicpulse-backdrop") removeModal();
    };
  }

  // Floating On-Screen Alert
  function showOnScreenAlert(text, verdict, explanation) {
    if (document.getElementById("civicpulse-onscreen-banner")) return;

    const banner = document.createElement("div");
    banner.id = "civicpulse-onscreen-banner";
    banner.className = "civicpulse-floating-alert";

    const icon = document.createElement("div");
    icon.className = "civicpulse-alert-icon";
    icon.textContent = "⚠️";

    const content = document.createElement("div");
    content.className = "civicpulse-alert-content";

    const title = document.createElement("h4");
    title.textContent = `CivicPulse Alert: ${verdict}`;

    const snippet = document.createElement("p");
    snippet.className = "civicpulse-alert-snippet";
    snippet.textContent = `"${text.slice(0, 90)}..."`;

    const reason = document.createElement("p");
    reason.className = "civicpulse-alert-reason";
      reason.textContent = explanation || "Disputed against an admin-attested local ledger claim.";

    content.appendChild(title);
    content.appendChild(snippet);
    content.appendChild(reason);

    const actions = document.createElement("div");
    actions.className = "civicpulse-alert-actions";

    const dismissBtn = document.createElement("button");
    dismissBtn.className = "civicpulse-btn-dismiss";
    dismissBtn.innerHTML = "&times;";
    dismissBtn.onclick = () => banner.remove();
    actions.appendChild(dismissBtn);

    banner.appendChild(icon);
    banner.appendChild(content);
    banner.appendChild(actions);

    document.body.appendChild(banner);

    setTimeout(() => {
      if (banner && banner.parentNode) banner.remove();
    }, 12000);
  }

  function removeModal() {
    const root = document.getElementById("civicpulse-overlay-root");
    if (root) root.textContent = "";
  }

  // Message listener from background worker
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "SHOW_SCANNING_MODAL") {
      showScanning(msg.text);
    } else if (msg.type === "SHOW_FACT_CHECK_RESULT") {
      showResult(msg.data);
    } else if (msg.type === "SHOW_ERROR_MODAL") {
      alert("CivicPulse Error: " + msg.error);
    }
  });

  // Passive On-Screen Scanner: Strictly opt-in
  chrome.storage.local.get("civicpulse_passive_scan_enabled", (res) => {
    const isOptedIn = res && res.civicpulse_passive_scan_enabled === true;
    if (!isOptedIn) {
      console.log("ℹ️ CivicPulse passive on-screen scanner is OFF (Opt-in required).");
      return;
    }

    console.log("✅ CivicPulse passive on-screen scanner is active (Opted In).");

    const VIRAL_PANIC_TRIGGERS = [
      /transformer blast.*blackout/i,
      /transformer exploded.*blackout/i,
      /5g radiation.*shutting down/i,
      /drinking boiled garlic.*cures/i,
      /3 din tak.*light nahi aayegi/i
    ];

    let scannedTexts = new Set();

    function scanVisibleText() {
      const candidates = document.querySelectorAll("h1, h2, h3, p, span, div[data-text]");
      for (const el of candidates) {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text.length > 25 && text.length < 350 && !scannedTexts.has(text)) {
          for (const regex of VIRAL_PANIC_TRIGGERS) {
            if (regex.test(text)) {
              scannedTexts.add(text);
              chrome.runtime.sendMessage({
                type: "CHECK_TEXT_API",
                text: text,
                domain: window.location.hostname
              }, (res) => {
                if (res && res.success && res.data && res.data.analysis) {
                  const a = res.data.analysis;
                  if (a.falsehood_score >= 0.65 || a.verdict === "FABRICATED_HOAX" || a.verdict === "DISPUTED_RUMOUR") {
                    showOnScreenAlert(text, a.verdict, a.summary || a.explanation);
                  }
                }
              });
              break;
            }
          }
        }
      }
    }

    setTimeout(scanVisibleText, 3000);
    window.addEventListener("scroll", debounce(scanVisibleText, 2500), { passive: true });
  });

  function debounce(fn, delay) {
    let timer = null;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }
})();
