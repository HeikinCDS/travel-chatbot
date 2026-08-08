const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const resetButton = document.querySelector("#reset-button");
const preferenceResetButton = document.querySelector("#preference-reset-button");
const textSizeButton = document.querySelector("#text-size-button");
const contrastButton = document.querySelector("#contrast-button");
const sidebarToggleButton = document.querySelector("#sidebar-toggle-button");
const tripSidebar = document.querySelector("#trip-sidebar");
const messages = document.querySelector("#messages");
const recommendations = document.querySelector("#recommendations");
const quickReplies = document.querySelector("#quick-replies");
const preferences = document.querySelector("#preference-list");
const formStatus = document.querySelector("#form-status");
const historyList = document.querySelector("#chat-history");
const historyEmpty = document.querySelector("#history-empty");
let messageCounter = 0;
let preferredSpeechVoice = null;

function chooseGentleVoice() {
  if (!("speechSynthesis" in window)) return null;
  const englishVoices = window.speechSynthesis.getVoices().filter(voice => {
    return voice.lang.toLowerCase().startsWith("en");
  });
  const preferences = [
    /Microsoft Sonia.*Natural/i,
    /Microsoft Jenny.*Natural/i,
    /Microsoft Aria.*Natural/i,
    /Microsoft Natasha.*Natural/i,
    /Google UK English Female/i,
    /Microsoft Zira/i,
    /female/i,
  ];
  for (const pattern of preferences) {
    const voice = englishVoices.find(candidate => pattern.test(candidate.name));
    if (voice) return voice;
  }
  return englishVoices.find(voice => /natural/i.test(voice.name))
    || englishVoices[0]
    || null;
}

function refreshPreferredVoice() {
  preferredSpeechVoice = chooseGentleVoice();
}

if ("speechSynthesis" in window) {
  refreshPreferredVoice();
  window.speechSynthesis.addEventListener("voiceschanged", refreshPreferredVoice);
}

function registerHistoryItem(row, text, sender) {
  const messageId = `conversation-message-${messageCounter}`;
  messageCounter += 1;
  row.id = messageId;
  row.tabIndex = -1;

  const listItem = document.createElement("li");
  const button = document.createElement("button");
  const speaker = document.createElement("span");
  const preview = document.createElement("span");
  button.type = "button";
  button.dataset.messageTarget = messageId;
  button.setAttribute("aria-label", `Return to ${sender === "user" ? "your" : "Maya's"} message: ${text}`);
  speaker.className = "history-speaker";
  speaker.textContent = sender === "user" ? "You" : "Maya";
  preview.className = "history-preview";
  preview.textContent = text;
  button.append(speaker, preview);
  listItem.appendChild(button);
  historyList.appendChild(listItem);
  historyEmpty.hidden = true;
}

function addMessage(text, sender) {
  const row = document.createElement("article");
  row.className = `message-row ${sender === "user" ? "user-row" : "assistant-row"}`;

  const content = document.createElement("div");
  content.className = "message-content";

  if (sender === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "assistant-mark";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "MY";
    row.appendChild(avatar);

    const name = document.createElement("p");
    name.className = "speaker-name";
    name.textContent = "Maya";
    content.appendChild(name);
  }

  const message = document.createElement("div");
  message.className = sender === "user" ? "user-message" : "assistant-message";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  message.appendChild(paragraph);
  content.appendChild(message);

  if (sender === "bot" && "speechSynthesis" in window) {
    const speakButton = document.createElement("button");
    speakButton.className = "speak-button";
    speakButton.type = "button";
    speakButton.dataset.speak = text;
    speakButton.textContent = "Read aloud";
    speakButton.setAttribute("aria-label", "Read Maya's latest reply aloud");
    content.appendChild(speakButton);
  }

  row.appendChild(content);
  messages.appendChild(row);
  registerHistoryItem(row, text, sender);
  row.scrollIntoView({ block: "nearest" });
}

const initialMessageRow = messages.querySelector(".message-row");
const initialMessageText = initialMessageRow?.querySelector(".assistant-message p")?.textContent;
if (initialMessageRow && initialMessageText) {
  registerHistoryItem(initialMessageRow, initialMessageText, "bot");
}

function labelFor(key) {
  return key.replaceAll("_", " ").replace(/^./, value => value.toUpperCase());
}

function showPreferences(context) {
  preferences.replaceChildren();
  const entries = Object.entries(context || {}).filter(([, value]) => {
    return value !== null && value !== "" && (!Array.isArray(value) || value.length > 0);
  });
  if (!entries.length) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = "Status";
    detail.textContent = "Not provided yet";
    wrapper.append(term, detail);
    preferences.appendChild(wrapper);
    return;
  }
  for (const [key, rawValue] of entries) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = labelFor(key);
    detail.textContent = Array.isArray(rawValue) ? rawValue.join(", ") : String(rawValue);
    wrapper.append(term, detail);
    preferences.appendChild(wrapper);
  }
}

function showRecommendations(items) {
  recommendations.replaceChildren();
  for (const item of items || []) {
    const card = document.createElement("article");
    card.className = "recommendation-card";

    if (item.image_url) {
      const figure = document.createElement("figure");
      figure.className = "recommendation-image";
      const image = document.createElement("img");
      image.src = item.image_url;
      image.alt = `Source photograph of ${item.attraction_name || "the attraction"}`;
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      figure.appendChild(image);
      if (item.image_attribution || item.image_license) {
        const caption = document.createElement("figcaption");
        const attribution = [item.image_attribution, item.image_license]
          .filter(Boolean)
          .join(" — ");
        if (item.image_page_url) {
          const creditLink = document.createElement("a");
          creditLink.href = item.image_page_url;
          creditLink.target = "_blank";
          creditLink.rel = "noopener noreferrer";
          creditLink.textContent = `Photo: ${attribution}`;
          caption.appendChild(creditLink);
        } else {
          caption.textContent = `Photo: ${attribution}`;
        }
        figure.appendChild(caption);
      }
      card.appendChild(figure);
    }

    const title = document.createElement("h3");
    title.textContent = item.attraction_name || "Attraction";
    const location = document.createElement("p");
    location.textContent = [item.city_district, item.state_territory].filter(Boolean).join(", ");
    const category = document.createElement("p");
    category.textContent = item.primary_category ? `Category: ${item.primary_category}` : "";
    const description = document.createElement("p");
    description.className = "recommendation-description";
    description.textContent = item.display_description || item.short_description || "";
    card.append(title, location, category, description);

    const facts = [
      item.cost_summary,
      item.duration_summary,
      item.accessibility_summary,
    ].filter(Boolean);
    if (facts.length) {
      const factList = document.createElement("ul");
      factList.className = "recommendation-facts";
      for (const fact of facts) {
        const listItem = document.createElement("li");
        listItem.textContent = fact;
        factList.appendChild(listItem);
      }
      card.appendChild(factList);
    }

    if (item.verification_note) {
      const note = document.createElement("p");
      note.className = "verification-note";
      note.textContent = item.verification_note;
      card.appendChild(note);
    }

    const sourceLinks = Array.isArray(item.source_links) && item.source_links.length
      ? item.source_links
      : [{ title: "Visitor information", url: item.official_url || item.source_url }];
    const validSources = sourceLinks.filter(source => source && source.url);
    if (validSources.length) {
      const sourceBlock = document.createElement("div");
      sourceBlock.className = "source-links";
      const sourceHeading = document.createElement("strong");
      sourceHeading.textContent = "Sources";
      sourceBlock.appendChild(sourceHeading);
      for (const source of validSources) {
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.title || "Check visitor information";
        sourceBlock.appendChild(link);
      }
      card.appendChild(sourceBlock);
    }
    recommendations.appendChild(card);
  }
}

function showQuickReplies(suggestions) {
  quickReplies.replaceChildren();
  for (const suggestion of suggestions || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = suggestion.label;
    button.dataset.message = suggestion.message;
    quickReplies.appendChild(button);
  }
}

async function sendJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

async function submitMessage(message) {
  addMessage(message, "user");
  input.value = "";
  input.style.height = "auto";
  formStatus.textContent = "Finding a helpful response...";
  sendButton.disabled = true;
  quickReplies.querySelectorAll("button").forEach(button => { button.disabled = true; });

  try {
    const data = await sendJson("/api/chat", { message });
    addMessage(data.reply, "bot");
    showPreferences(data.context);
    showRecommendations(data.recommendations);
    showQuickReplies(data.suggestions);
    formStatus.textContent = "";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  const message = input.value.trim();
  if (message) submitMessage(message);
});

input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});

quickReplies.addEventListener("click", event => {
  const button = event.target.closest("button[data-message]");
  if (button) submitMessage(button.dataset.message);
});

historyList.addEventListener("click", event => {
  const button = event.target.closest("button[data-message-target]");
  if (!button) return;
  const target = document.getElementById(button.dataset.messageTarget);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.focus({ preventScroll: true });
});

messages.addEventListener("click", event => {
  const button = event.target.closest("button[data-speak]");
  if (!button || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(button.dataset.speak);
  if (preferredSpeechVoice) {
    utterance.voice = preferredSpeechVoice;
    utterance.lang = preferredSpeechVoice.lang;
  } else {
    utterance.lang = "en-MY";
  }
  utterance.rate = 0.86;
  utterance.pitch = 1.02;
  window.speechSynthesis.speak(utterance);
});

resetButton.addEventListener("click", async () => {
  resetButton.disabled = true;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const data = await sendJson("/api/reset");
    messages.replaceChildren();
    historyList.replaceChildren();
    historyEmpty.hidden = false;
    messageCounter = 0;
    addMessage(data.reply, "bot");
    showPreferences({});
    showRecommendations([]);
    showQuickReplies(data.suggestions);
    formStatus.textContent = "";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    resetButton.disabled = false;
    input.focus();
  }
});

preferenceResetButton.addEventListener("click", async () => {
  preferenceResetButton.disabled = true;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const data = await sendJson("/api/reset-preferences");
    addMessage(data.reply, "bot");
    showPreferences(data.context);
    showRecommendations(data.recommendations);
    showQuickReplies(data.suggestions);
    formStatus.textContent = "Trip preferences cleared.";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    preferenceResetButton.disabled = false;
    input.focus();
  }
});

function applySavedDisplaySettings() {
  const largeText = localStorage.getItem("largeText") === "true";
  const highContrast = localStorage.getItem("highContrast") === "true";
  document.body.classList.toggle("large-text", largeText);
  document.body.classList.toggle("high-contrast", highContrast);
  textSizeButton.setAttribute("aria-pressed", String(largeText));
  contrastButton.setAttribute("aria-pressed", String(highContrast));
  textSizeButton.querySelector(".control-label").textContent = largeText ? "Normal text" : "Larger text";
  contrastButton.querySelector(".control-label").textContent = highContrast ? "Standard colours" : "High contrast";
}

function applySavedSidebarSetting() {
  const visible = localStorage.getItem("tripPanelVisible") !== "false";
  tripSidebar.hidden = !visible;
  document.body.classList.toggle("sidebar-hidden", !visible);
  sidebarToggleButton.setAttribute("aria-expanded", String(visible));
  sidebarToggleButton.querySelector(".control-label").textContent = visible
    ? "Hide trip panel"
    : "Show trip panel";
  sidebarToggleButton.querySelector("span[aria-hidden='true']").textContent = visible
    ? "◀"
    : "▶";
}

sidebarToggleButton.addEventListener("click", () => {
  const visible = tripSidebar.hidden;
  localStorage.setItem("tripPanelVisible", String(visible));
  applySavedSidebarSetting();
});

textSizeButton.addEventListener("click", () => {
  const enabled = !document.body.classList.contains("large-text");
  localStorage.setItem("largeText", String(enabled));
  applySavedDisplaySettings();
});

contrastButton.addEventListener("click", () => {
  const enabled = !document.body.classList.contains("high-contrast");
  localStorage.setItem("highContrast", String(enabled));
  applySavedDisplaySettings();
});

applySavedDisplaySettings();
applySavedSidebarSetting();
