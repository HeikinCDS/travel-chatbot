const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const resetButton = document.querySelector("#reset-button");
const textSizeButton = document.querySelector("#text-size-button");
const messages = document.querySelector("#messages");
const recommendations = document.querySelector("#recommendations");
const quickReplies = document.querySelector("#quick-replies");
const preferences = document.querySelector("#preference-list");
const formStatus = document.querySelector("#form-status");

function addMessage(text, sender) {
  const row = document.createElement("article");
  row.className = `message-row ${sender === "user" ? "user-row" : "bot-row"}`;

  const content = document.createElement("div");
  if (sender === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "🤖";
    row.appendChild(avatar);

    const name = document.createElement("p");
    name.className = "speaker-name";
    name.textContent = "Travel Companion";
    content.appendChild(name);
  }

  const bubble = document.createElement("div");
  bubble.className = `message ${sender === "user" ? "user-message" : "bot-message"}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  bubble.appendChild(paragraph);
  content.appendChild(bubble);
  row.appendChild(content);
  messages.appendChild(row);
  row.scrollIntoView({ block: "nearest" });
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
    const title = document.createElement("h3");
    title.textContent = item.attraction_name || "Attraction";
    const location = document.createElement("p");
    location.textContent = [item.city_district, item.state_territory].filter(Boolean).join(", ");
    const category = document.createElement("p");
    category.textContent = item.primary_category ? `Category: ${item.primary_category}` : "";
    const description = document.createElement("p");
    description.textContent = item.short_description || "";
    card.append(title, location, category, description);

    const source = item.official_url || item.source_url;
    if (source) {
      const link = document.createElement("a");
      link.href = source;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Check official information";
      card.appendChild(link);
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
  formStatus.textContent = "Finding a helpful response…";
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

quickReplies.addEventListener("click", event => {
  const button = event.target.closest("button[data-message]");
  if (button) submitMessage(button.dataset.message);
});

resetButton.addEventListener("click", async () => {
  resetButton.disabled = true;
  try {
    const data = await sendJson("/api/reset");
    messages.replaceChildren();
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

textSizeButton.addEventListener("click", () => {
  const enabled = document.body.classList.toggle("large-text");
  textSizeButton.setAttribute("aria-pressed", String(enabled));
  textSizeButton.innerHTML = enabled
    ? '<span aria-hidden="true">A</span> Normal text'
    : '<span aria-hidden="true">A+</span> Larger text';
});
