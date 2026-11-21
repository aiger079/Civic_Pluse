// CivicPulse Background Service Worker (Manifest V3)
const DEFAULT_API_URL = "https://civicpluse.naxiv.com";

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
          context: pageDomain(tab.url)
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
    fetch(`${DEFAULT_API_URL}/api/fact-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: request.text,
          context: sender.tab ? pageDomain(sender.tab.url) : "popup"
      })
    })
    .then(async r => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        sendResponse({ success: false, error: data.detail || `Fact-check request failed (${r.status}).` });
        return;
      }
      sendResponse({ success: true, data });
    })
    .catch(err => sendResponse({ success: false, error: err.message }));
    
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
