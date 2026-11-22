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
        <p style="font-weight: 600;">Looking for evidence about this claim…</p>
        <p style="font-size: 11px; color: #94a3b8; margin-top: 2px;">
          Review any sources the check returns.
        </p>
      </div>
    `;

    // Transparency Note
    const privacyNote = document.createElement("div");
    privacyNote.className = "civicpulse-privacy-notice";
    const privacyHeading = document.createElement("strong");
    privacyHeading.textContent = "🔒 Data disclosure";
    privacyNote.append(
      privacyHeading,
      ` CivicPulse sends the selected text and site domain (${domain}) to its backend. The configured provider (Google Gemini or Groq) may receive that information. If Google Search fails or finds no usable sources, CivicPulse may send a short public search query to Tavily or a public topic to Wikipedia. Neither receives the site domain. CivicPulse does not send cookies, logins, or browsing history.`
    );

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

    const a = data?.analysis || {};
    const verdict = a.verdict;
    const evidence = describeCivicPulseEvidence(a);
    const hasVerdict = typeof verdict === "string" && !!verdict && !evidence;

    let pillClass = hasVerdict ? "pill-rumour" : "pill-neutral";
    let verdictIcon = "⚠️";
    if (hasVerdict && verdict === "VERIFIED_TRUE") {
      pillClass = "pill-true";
      verdictIcon = "✅";
    } else if (hasVerdict && (verdict === "FABRICATED_HOAX" || verdict === "DISPUTED_RUMOUR")) {
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
        <h3>CivicPulse Fact Check</h3>
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
    pill.textContent = evidence?.label || verdict || "Check failed";
    topRow.appendChild(pill);
    if (hasVerdict && Number.isFinite(a.confidence)) {
      const confSpan = document.createElement("span");
      confSpan.style.fontSize = "12px";
      confSpan.style.color = "#94a3b8";
      confSpan.style.fontWeight = "600";
      confSpan.textContent = `Confidence: ${Math.round(a.confidence * 100)}%`;
      topRow.appendChild(confSpan);
    }
    body.appendChild(topRow);

    // Uncertain preliminary assessments still need review.
    if (hasVerdict && a.uncertainty_state) {
      const warnBox = document.createElement("div");
      warnBox.className = "civicpulse-uncertainty-box";
      warnBox.innerHTML = `
        <strong>⚠️ Preliminary result:</strong> Live search may have retrieved sources, but the verdict and source relevance can still be wrong. Confirm important claims with primary sources.
      `;
      body.appendChild(warnBox);
    }

    const truthEstimate = a.model_estimate?.truth_score ?? a.truth_score;
    const falseEstimate = a.model_estimate?.falsehood_score ?? a.falsehood_score;
    const assessedExcerpts = a.provider_used === "wikimedia" || a.provider_used === "tavily";
    if (hasVerdict && !assessedExcerpts && Number.isFinite(truthEstimate) && Number.isFinite(falseEstimate)) {
      const truthPct = Math.round(Math.max(0, Math.min(1, truthEstimate)) * 100);
      const falsePct = Math.round(Math.max(0, Math.min(1, falseEstimate)) * 100);
      const meters = document.createElement("div");
      meters.className = "civicpulse-meter-group";
      meters.innerHTML = `
        <div class="civicpulse-meter-label">
          <span>Model-estimated truth</span>
          <span><strong>${truthPct}%</strong></span>
        </div>
        <div class="civicpulse-bar-bg">
          <div class="civicpulse-bar-fill truth" style="width: ${truthPct}%;"></div>
        </div>
        <div class="civicpulse-meter-label" style="margin-top: 6px;">
          <span>Model-estimated falsehood</span>
          <span><strong>${falsePct}%</strong></span>
        </div>
        <div class="civicpulse-bar-bg">
          <div class="civicpulse-bar-fill fake" style="width: ${falsePct}%;"></div>
        </div>
      `;
      body.appendChild(meters);
    }

    // Summary & Explanation (Rendered safely via textContent)
    const summaryEl = document.createElement("div");
    summaryEl.className = "civicpulse-summary";
    summaryEl.textContent = evidence?.message || a.summary || (verdict ? "" : "CivicPulse returned an incomplete response. Try again in a moment.");
    if (summaryEl.textContent) body.appendChild(summaryEl);

    const explanationEl = document.createElement("div");
    explanationEl.className = "civicpulse-explanation";
    explanationEl.textContent = evidence?.message ? "" : a.explanation || "";
    if (explanationEl.textContent) body.appendChild(explanationEl);

    // Sources & Citations
    const sourceList = getCivicPulseSourceList(a);
    if (sourceList.links.length > 0) {
      const sourcesBox = document.createElement("div");
      sourcesBox.className = "civicpulse-sources-box";
      
      const sourcesHeading = document.createElement("h5");
      sourcesHeading.textContent = `📑 ${sourceList.label}:`;
      sourcesHeading.style.fontSize = "11.5px";
      sourcesHeading.style.color = "#93c5fd";
      sourcesHeading.style.marginBottom = "6px";
      sourcesBox.appendChild(sourcesHeading);

      const sourcesList = document.createElement("ul");
      sourcesList.style.listStyle = "none";
      sourcesList.style.padding = "0";

      for (const s of sourceList.links) {
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
    const advice = evidence?.advice || a.actionable_advice;
    if (advice) {
      const adviceEl = document.createElement("div");
      adviceEl.className = "civicpulse-advice";
      adviceEl.textContent = advice;
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

  // Automatic visible-claim scanner. It checks visible text snippets only and
  // starts enabled on install; users can turn it off from the popup.
  const PASSIVE_SCAN_KEY = "civicpulse_passive_scan_enabled";
  const CANDIDATE_SELECTOR = [
    "h1", "h2", "h3", "p", "li", "blockquote",
    "[data-pre-plain-text] .selectable-text",
    "[data-testid='msg-container'] .selectable-text",
    "ytd-comment-thread-renderer #content-text",
    "ytd-text-inline-expander #content",
    "span[dir='auto']"
  ].join(",");
  const checkedTexts = new Set();
  let scannerCleanup = null;

  function normalizeClaimText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function rememberCheckedText(text) {
    checkedTexts.add(text);
    if (checkedTexts.size > 500) {
      checkedTexts.delete(checkedTexts.values().next().value);
    }
  }

  function highlightFalseClaim(element, analysis) {
    const verdict = String(analysis.verdict || "").toUpperCase();
    const hasLiveSources = analysis.search_performed === true
      && Array.isArray(analysis.sources)
      && analysis.sources.length > 0;
    const flaggedFalse = hasLiveSources
      && (verdict === "FABRICATED_HOAX" || verdict === "DISPUTED_RUMOUR");

    if (!flaggedFalse || !element.isConnected) return false;

    element.classList.add("civicpulse-false-claim");
    element.dataset.civicpulseVerdict = verdict;
    element.setAttribute(
      "data-civicpulse-note",
      "CivicPulse's preliminary live-search assessment flagged this claim. Check the linked sources before relying on it."
    );
    showOnScreenAlert(
      normalizeClaimText(element.innerText),
      verdict,
      analysis.summary || analysis.explanation || "Check the linked sources before relying on this preliminary assessment."
    );
    return true;
  }

  function startPassiveScanner() {
    if (scannerCleanup || !document.body) return;

    const queue = [];
    const queuedTexts = new Set();
    const MAX_QUEUE_SIZE = 20;
    const MIN_REQUEST_INTERVAL_MS = 10000;
    let active = true;
    let isChecking = false;
    let nextCheckTimer = null;
    let scanTimer = null;
    let lastRequestAt = 0;

    function isVisibleClaimElement(element) {
      if (!element.isConnected || element.closest(
        "#civicpulse-overlay-root, script, style, noscript, input, textarea, select, button, a, nav, header, footer, aside, [contenteditable='true']"
      )) return false;

      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none"
        && style.visibility !== "hidden"
        && Number(style.opacity) !== 0
        && rect.width > 0
        && rect.height > 0
        && rect.right > 0
        && rect.left < window.innerWidth
        && rect.bottom > 0
        && rect.top < window.innerHeight;
    }

    function checkQueue() {
      if (!active || isChecking || queue.length === 0 || !document.visibilityState || document.visibilityState === "hidden") return;
      const wait = Math.max(0, MIN_REQUEST_INTERVAL_MS - (Date.now() - lastRequestAt));
      if (wait > 0) {
        if (!nextCheckTimer) nextCheckTimer = setTimeout(() => {
          nextCheckTimer = null;
          checkQueue();
        }, wait);
        return;
      }

      const item = queue.shift();
      queuedTexts.delete(item.text);
      if (checkedTexts.has(item.text) || !isVisibleClaimElement(item.element)) {
        checkQueue();
        return;
      }

      isChecking = true;
      lastRequestAt = Date.now();
      chrome.runtime.sendMessage({
        type: "CHECK_TEXT_API",
        text: item.text,
        domain: window.location.hostname,
        passive: true
      }, (response) => {
        isChecking = false;
        if (!active) return;
        if (response && response.rate_limited) {
          if (active) {
            queuedTexts.add(item.text);
            queue.unshift(item);
            nextCheckTimer = setTimeout(() => {
              nextCheckTimer = null;
              checkQueue();
            }, 60000);
          }
          return;
        }

        rememberCheckedText(item.text);
        if (chrome.runtime.lastError) {
          console.debug("CivicPulse automatic check was unavailable.");
        } else if (response && response.success && response.data && response.data.analysis) {
          const matchingVisibleElements = Array.from(document.querySelectorAll(CANDIDATE_SELECTOR))
            .filter(element => isVisibleClaimElement(element)
              && normalizeClaimText(element.innerText || element.textContent) === item.text);
          const targets = matchingVisibleElements.length > 0 ? matchingVisibleElements : [item.element];
          targets.forEach(element => highlightFalseClaim(element, response.data.analysis));
        }
        if (queue.length > 0) {
          checkQueue();
        } else if (active) {
          nextCheckTimer = setTimeout(() => {
            nextCheckTimer = null;
            scanVisibleText();
          }, MIN_REQUEST_INTERVAL_MS);
        }
      });
    }

    function scanVisibleText() {
      if (!active) return;
      const candidates = document.querySelectorAll(CANDIDATE_SELECTOR);
      let added = 0;
      for (const element of candidates) {
        if (!isVisibleClaimElement(element)) continue;
        const text = normalizeClaimText(element.innerText || element.textContent);
        if (text.length < 40 || text.length > 350 || checkedTexts.has(text) || queuedTexts.has(text)) continue;

        queuedTexts.add(text);
        queue.push({ element, text });
        added += 1;
        if (queue.length >= MAX_QUEUE_SIZE || added >= 5) break;
      }
      checkQueue();
    }

    const scheduleScan = debounce(() => {
      if (!active) return;
      if (scanTimer) clearTimeout(scanTimer);
      scanTimer = setTimeout(scanVisibleText, 800);
    }, 350);
    const observer = new MutationObserver(scheduleScan);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    window.addEventListener("scroll", scheduleScan, { passive: true });
    window.addEventListener("resize", scheduleScan, { passive: true });
    document.addEventListener("visibilitychange", scheduleScan);
    scannerCleanup = () => {
      active = false;
      observer.disconnect();
      window.removeEventListener("scroll", scheduleScan);
      window.removeEventListener("resize", scheduleScan);
      document.removeEventListener("visibilitychange", scheduleScan);
      if (nextCheckTimer) clearTimeout(nextCheckTimer);
      if (scanTimer) clearTimeout(scanTimer);
      queue.length = 0;
      queuedTexts.clear();
      scannerCleanup = null;
    };
    scanVisibleText();
  }

  function stopPassiveScanner() {
    if (scannerCleanup) scannerCleanup();
    document.querySelectorAll(".civicpulse-false-claim").forEach(element => {
      element.classList.remove("civicpulse-false-claim");
      delete element.dataset.civicpulseVerdict;
      element.removeAttribute("data-civicpulse-note");
    });
    const banner = document.getElementById("civicpulse-onscreen-banner");
    if (banner) banner.remove();
  }

  chrome.storage.local.get(PASSIVE_SCAN_KEY, (settings) => {
    const enabled = settings[PASSIVE_SCAN_KEY] !== false;
    if (settings[PASSIVE_SCAN_KEY] === undefined) {
      chrome.storage.local.set({ [PASSIVE_SCAN_KEY]: true });
    }
    if (enabled) startPassiveScanner();
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[PASSIVE_SCAN_KEY]) return;
    if (changes[PASSIVE_SCAN_KEY].newValue === false) stopPassiveScanner();
    else startPassiveScanner();
  });

  function debounce(fn, delay) {
    let timer = null;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }
})();
