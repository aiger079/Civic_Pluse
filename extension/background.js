// CivicPulse Background Service Worker (Manifest V3)
const DEFAULT_API_URL = "https://civic-pluse-sooty.vercel.app";
const PASSIVE_QUOTA_STORAGE_KEY = "civicpulse_passive_check_timestamps";
const PASSIVE_QUOTA_LIMIT = 8;
const PASSIVE_QUOTA_WINDOW_MS = 60 * 1000;
let passiveQuotaSerial = Promise.resolve();

function reservePassiveCheckSlot() {
  const reservation = passiveQuotaSerial.then(async () => {
    const now = Date.now();
    const stored = await chrome.storage.local.get(PASSIVE_QUOTA_STORAGE_KEY);
    const recent = (stored[PASSIVE_QUOTA_STORAGE_KEY] || [])
      .filter(timestamp => Number.isFinite(timestamp) && now - timestamp < PASSIVE_QUOTA_WINDOW_MS);

    if (recent.length >= PASSIVE_QUOTA_LIMIT) {
      await chrome.storage.local.set({ [PASSIVE_QUOTA_STORAGE_KEY]: recent });
      return false;
    }

    recent.push(now);
    await chrome.storage.local.set({ [PASSIVE_QUOTA_STORAGE_KEY]: recent });
    return true;
  });
  passiveQuotaSerial = reservation.then(() => undefined, () => undefined);
  return reservation;
}

async function runTextCheck(request, sender, sendResponse) {
  try {
    const text = String(request.text || "").trim();
    if (!text || text.length > 350) {
      sendResponse({ success: false, error: "The visible claim is empty or too long to check." });
      return;
    }

    if (request.passive && !(await reservePassiveCheckSlot())) {
      sendResponse({ success: false, rate_limited: true });
      return;
    }

    const response = await fetch(`${DEFAULT_API_URL}/api/fact-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        context: sender.tab ? pageDomain(sender.tab.url) : "popup"
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      sendResponse({
        success: false,
        rate_limited: response.status === 429,
        error: data.detail || `Fact-check request failed (${response.status}).`
      });
      return;
    }
    sendResponse({ success: true, data });
  } catch (err) {
    sendResponse({ success: false, error: err.message || "The CivicPulse backend could not be reached." });
  }
}

function pageDomain(rawUrl) {
  try {
    return new URL(rawUrl).hostname || "web_selection";
  } catch {
    return "web_selection";
  }
}

// Set up Context Menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "civicpulse_fact_check",
    title: "🛡️ Verify with CivicPulse AI (\"%s\")",
    contexts: ["selection"]
  });
  console.log("CivicPulse extension context menu registered.");
});

// Handle Context Menu click
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "civicpulse_fact_check" && info.selectionText) {
    const selectedText = info.selectionText.trim();
    if (!selectedText) return;

    // Send loading signal to content script
    chrome.tabs.sendMessage(tab.id, {
      type: "SHOW_SCANNING_MODAL",
      text: selectedText
    }).catch(() => {});

    try {
      const response = await fetch(`${DEFAULT_API_URL}/api/fact-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: selectedText,
          context: pageDomain(tab.url),
          allow_public_reference_search: false,
          allow_web_search: false
        })
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `Fact-check request failed (${response.status}).`);
      }
      
      // Send result back to content script to display pop-up
      chrome.tabs.sendMessage(tab.id, {
        type: "SHOW_FACT_CHECK_RESULT",
        data: data
      }).catch(err => console.error("Error communicating with tab:", err));

    } catch (err) {
      chrome.tabs.sendMessage(tab.id, {
        type: "SHOW_ERROR_MODAL",
        error: err.message || "Could not reach CivicPulse engine. Make sure the backend is running."
      }).catch(() => {});
    }
  }
});

// Listen to messages from content scripts or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "CHECK_TEXT_API") {
    runTextCheck(request, sender, sendResponse);
    return true; // Keep channel open for async response
  }

  if (request.type === "CHECK_ENGINE_HEALTH") {
    fetch(`${DEFAULT_API_URL}/health`)
      .then(r => r.json())
      .then(data => sendResponse({ online: true, data }))
      .catch(() => sendResponse({ online: false }));
    return true;
  }
});
