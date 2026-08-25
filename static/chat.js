const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const voiceInputButton = document.querySelector("#voice-input-button");
const resetButton = document.querySelector("#reset-button");
const preferenceResetButton = document.querySelector("#preference-reset-button");
const textSizeButton = document.querySelector("#text-size-button");
const contrastButton = document.querySelector("#contrast-button");
const languageSelect = document.querySelector("#language-select");
const sidebarToggleButton = document.querySelector("#sidebar-toggle-button");
const easyAccessStartButton = document.querySelector("#easy-access-start-button");
const tripSidebar = document.querySelector("#trip-sidebar");
const messages = document.querySelector("#messages");
const quickReplies = document.querySelector("#quick-replies");
const preferences = document.querySelector("#preference-list");
const formStatus = document.querySelector("#form-status");
const historyList = document.querySelector("#chat-history");
const historyEmpty = document.querySelector("#history-empty");
let messageCounter = 0;
let preferredSpeechVoice = null;
let activeAudio = null;
const generatedAudioUrls = new Set();
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let speechRecognition = null;
let voiceInputActive = false;
let inputBeforeSpeech = "";
let latestContext = {};
let latestSuggestions = Array.from(
  quickReplies.querySelectorAll("button[data-message]"),
  button => ({ label: button.textContent.trim(), message: button.dataset.message }),
);
const SUPPORTED_LANGUAGES = new Set(["en", "ms", "zh"]);
let currentLanguage = localStorage.getItem("jomvoyageLanguage") || "en";
if (!SUPPORTED_LANGUAGES.has(currentLanguage)) currentLanguage = "en";

const UI_TEXT = {
  en: {
    brandSubtitle: "Plan holiday trip in Malaysia with Maya",
    language: "Language",
    largerText: "Larger text",
    normalText: "Normal text",
    highContrast: "High contrast",
    standardColours: "Standard colours",
    newChat: "New chat",
    hideTripPanel: "Hide trip panel",
    showTripPanel: "Show trip panel",
    savedPreferences: "Saved trip preferences",
    preferencesHelp: "Maya updates these details while you chat.",
    resetPreferences: "Reset trip preferences",
    chatHistory: "Chat history",
    historyHelp: "Current conversation. Select a message to return to it.",
    historyEmpty: "Your messages will appear here.",
    eyebrow: "Plan a trip in Malaysia",
    introTitle: "Where would you like to explore?",
    introDescription: "Tell me a state and what you enjoy. I will remember your choices while we chat.",
    elderlyTrip: "Plan an elderly-friendly trip",
    howToUse: "How to use",
    howToUseText: "You may type common travel requests in English, Malay or Chinese, or tap one of the large choices. You can also mention your budget or mobility needs.",
    suggestedAnswers: "Suggested answers",
    messageMaya: "Message Maya",
    speak: "Speak",
    stop: "Stop",
    send: "Send",
    readAloud: "Read aloud",
    preparingAudio: "Preparing audio...",
    safetyNote: "Confirm prices, opening hours and accessibility with official sources before travelling.",
    welcome: "Hello, I am Maya, your JomVoyage travel companion. Which Malaysian state would you like to visit?",
    status: "Status",
    notProvided: "Not provided yet",
    category: "Category",
    accessibilityDetails: "Elderly-accessibility details",
    accessibilityReason: "Why it may suit elderly visitors",
    sources: "Sources",
    visitorInformation: "Check visitor information",
    you: "You",
  },
  ms: {
    brandSubtitle: "Rancang percutian di Malaysia bersama Maya",
    language: "Bahasa",
    largerText: "Teks lebih besar",
    normalText: "Teks biasa",
    highContrast: "Kontras tinggi",
    standardColours: "Warna biasa",
    newChat: "Sembang baharu",
    hideTripPanel: "Sembunyikan panel perjalanan",
    showTripPanel: "Tunjukkan panel perjalanan",
    savedPreferences: "Pilihan perjalanan tersimpan",
    preferencesHelp: "Maya mengemas kini maklumat ini semasa anda berbual.",
    resetPreferences: "Tetapkan semula pilihan perjalanan",
    chatHistory: "Sejarah sembang",
    historyHelp: "Perbualan semasa. Pilih mesej untuk kembali kepadanya.",
    historyEmpty: "Mesej anda akan dipaparkan di sini.",
    eyebrow: "Rancang perjalanan di Malaysia",
    introTitle: "Ke manakah anda ingin pergi?",
    introDescription: "Beritahu saya negeri dan minat anda. Saya akan mengingati pilihan anda semasa kita berbual.",
    elderlyTrip: "Rancang perjalanan mesra warga emas",
    howToUse: "Cara menggunakan",
    howToUseText: "Anda boleh menaip permintaan perjalanan biasa dalam bahasa Inggeris, Melayu atau Cina, atau memilih salah satu butang besar. Anda juga boleh menyatakan bajet atau keperluan mobiliti.",
    suggestedAnswers: "Cadangan jawapan",
    messageMaya: "Mesej kepada Maya",
    speak: "Bercakap",
    stop: "Berhenti",
    send: "Hantar",
    readAloud: "Baca kuat",
    preparingAudio: "Menyediakan audio...",
    safetyNote: "Sahkan harga, waktu operasi dan kemudahan akses dengan sumber rasmi sebelum melancong.",
    welcome: "Helo, saya Maya, teman perjalanan JomVoyage anda. Negeri manakah di Malaysia yang ingin anda lawati?",
    status: "Status",
    notProvided: "Belum diberikan",
    category: "Kategori",
    accessibilityDetails: "Maklumat akses untuk warga emas",
    accessibilityReason: "Mengapa tempat ini mungkin sesuai untuk warga emas",
    sources: "Sumber",
    visitorInformation: "Semak maklumat pelawat",
    you: "Anda",
  },
  zh: {
    brandSubtitle: "与 Maya 一起规划马来西亚假期",
    language: "语言",
    largerText: "放大字体",
    normalText: "标准字体",
    highContrast: "高对比度",
    standardColours: "标准颜色",
    newChat: "新对话",
    hideTripPanel: "隐藏行程面板",
    showTripPanel: "显示行程面板",
    savedPreferences: "已保存的旅行偏好",
    preferencesHelp: "聊天时，Maya 会更新这些资料。",
    resetPreferences: "重设旅行偏好",
    chatHistory: "聊天记录",
    historyHelp: "当前对话。选择一条消息即可返回查看。",
    historyEmpty: "您的消息将显示在这里。",
    eyebrow: "规划马来西亚之旅",
    introTitle: "您想探索哪里？",
    introDescription: "告诉我您想去的州属和兴趣。聊天期间，我会记住您的选择。",
    elderlyTrip: "规划长者友善之旅",
    howToUse: "使用方法",
    howToUseText: "您可以用英语、马来语或中文输入常见的旅游需求，也可以点击大按钮，并说明预算或行动需求。",
    suggestedAnswers: "建议回答",
    messageMaya: "给 Maya 发消息",
    speak: "语音输入",
    stop: "停止",
    send: "发送",
    readAloud: "朗读",
    preparingAudio: "正在准备语音...",
    safetyNote: "出行前请通过官方来源确认价格、开放时间和无障碍设施。",
    welcome: "您好，我是 Maya，您的 JomVoyage 旅行伙伴。您想前往马来西亚的哪个州属？",
    status: "状态",
    notProvided: "尚未提供",
    category: "类别",
    accessibilityDetails: "长者无障碍详情",
    accessibilityReason: "为何此地点可能适合长者",
    sources: "资料来源",
    visitorInformation: "查看访客资料",
    you: "您",
  },
};

function t(key) {
  return UI_TEXT[currentLanguage]?.[key] || UI_TEXT.en[key] || key;
}

const LOCALIZED_LABELS = {
  ms: {
    "Show me more options": "Tunjukkan lebih banyak pilihan",
    "Minimal walking": "Sedikit berjalan",
    "Wheelchair access": "Akses kerusi roda",
    "Nearby seats": "Tempat duduk berdekatan",
    "No special requirements": "Tiada keperluan khas",
    "Easiest access": "Akses paling mudah",
    "Lowest cost": "Kos paling rendah",
    "Shortest visit": "Lawatan paling singkat",
    Nature: "Alam semula jadi",
    nature: "alam semula jadi",
    Beach: "Pantai",
    History: "Sejarah",
    Wildlife: "Hidupan liar",
    Relaxation: "Santai",
    "Low walking": "Sedikit berjalan",
    "Step-free access": "Akses tanpa tangga",
    "Resting seats": "Tempat duduk rehat",
    "Accessible toilet": "Tandas mesra OKU",
    "Nearby parking": "Tempat letak kereta berdekatan",
    "Parking proximity": "Kedekatan tempat letak kereta",
    "Shelter or shade": "Tempat berteduh",
    "Walking difficulty": "Kesukaran berjalan",
    Shelter: "Tempat berteduh",
    "Overall elderly suitability": "Kesesuaian keseluruhan untuk warga emas",
    "Not recorded": "Tidak direkodkan",
    "Visitor information": "Maklumat pelawat",
    "Accessibility information": "Maklumat aksesibiliti",
    Suitable: "Sesuai",
    Partial: "Sebahagian",
    Yes: "Ya",
    No: "Tidak",
    State: "Negeri",
    Interests: "Minat",
    "Maximum fee": "Bayaran maksimum",
    "Elderly friendly": "Mesra warga emas",
    "Wheelchair accessible": "Boleh diakses kerusi roda",
    "Accessibility needs": "Keperluan aksesibiliti",
  },
  zh: {
    "Show me more options": "显示更多选择",
    "Minimal walking": "少量步行",
    "Wheelchair access": "轮椅通道",
    "Nearby seats": "附近休息座椅",
    "No special requirements": "没有特殊需求",
    "Easiest access": "最容易到达",
    "Lowest cost": "最低费用",
    "Shortest visit": "最短游览时间",
    Nature: "自然",
    nature: "自然",
    Beach: "海滩",
    History: "历史",
    Wildlife: "野生动物",
    Relaxation: "休闲",
    "Low walking": "少量步行",
    "Step-free access": "无台阶通道",
    "Resting seats": "休息座椅",
    "Accessible toilet": "无障碍厕所",
    "Nearby parking": "附近停车位",
    "Parking proximity": "停车距离",
    "Shelter or shade": "遮阳或有盖空间",
    "Walking difficulty": "步行难度",
    Shelter: "遮蔽处",
    "Overall elderly suitability": "整体长者适宜度",
    "Not recorded": "未记录",
    "Visitor information": "访客资料",
    "Accessibility information": "无障碍资料",
    Suitable: "适合",
    Partial: "部分适合",
    Yes: "是",
    No: "否",
    State: "州属",
    Interests: "兴趣",
    "Maximum fee": "最高费用",
    "Elderly friendly": "长者友善",
    "Wheelchair accessible": "轮椅无障碍",
    "Accessibility needs": "无障碍需求",
  },
};

function localizeLabel(label) {
  return LOCALIZED_LABELS[currentLanguage]?.[label] || label;
}

function localizeReply(data) {
  if (currentLanguage === "en") return data.reply;
  const names = (data.recommendations || [])
    .map(item => item.attraction_name)
    .filter(Boolean)
    .join(currentLanguage === "zh" ? "、" : ", ");
  const state = data.context?.state || (currentLanguage === "zh" ? "该州属" : "negeri tersebut");
  const hasState = Boolean(data.context?.state);

  if (currentLanguage === "ms") {
    const replies = {
      greeting: "Helo! Beritahu saya negeri di Malaysia yang ingin anda lawati.",
      help: "Anda boleh memberitahu saya negeri, minat, bajet bayaran masuk serta keperluan keluarga, warga emas atau akses kerusi roda.",
      out_of_scope: "Saya direka untuk membantu perancangan perjalanan dan tarikan di Malaysia. Sila masukkan mesej berkaitan perjalanan.",
      low_confidence: "Saya kurang memahami permintaan itu. Sila tanya tentang perjalanan di Malaysia, seperti negeri dan jenis tarikan yang anda minati.",
      request_refinement: "Pilihan manakah yang ingin anda ubah: lokasi, minat, bajet atau aksesibiliti?",
      clarify_accessibility: "Apakah keperluan akses yang paling penting untuk pelancong tersebut? Pilih satu di bawah atau taipkan beberapa keperluan.",
      no_alternatives: "Tiada lagi pilihan lain yang sepadan. Cuba ubah salah satu pilihan perjalanan anda.",
      previous_options_unavailable: "Belum ada cadangan terdahulu dalam perbualan ini. Beritahu saya negeri dan jenis tempat yang anda minati.",
      show_previous_options: "Sudah tentu. Berikut ialah pilihan terdahulu. Anda boleh memilih nama tempat atau meminta saya membandingkannya.",
      information_unavailable: "Sila minta cadangan terlebih dahulu, kemudian saya boleh menerangkan salah satu tempat yang dicadangkan.",
      choose_recommendation: "Tempat cadangan yang manakah ingin anda ketahui? Pilih salah satu nama tempat di bawah.",
      comparison_unavailable: "Maklumat yang direkodkan tidak mencukupi untuk perbandingan ini. Pilih nama tempat atau cuba perbandingan lain.",
      goodbye: "Selamat tinggal. Semoga anda seronok merancang perjalanan di Malaysia.",
      reset: "Pilihan perjalanan anda telah dipadamkan. Ke manakah anda ingin pergi?",
      reset_preferences: "Pilihan perjalanan tersimpan telah dipadamkan. Negeri manakah di Malaysia yang ingin anda terokai seterusnya?",
    };
    if (data.action === "recommend" || data.action === "alternative") {
      const prefix = data.action === "alternative" ? "Berikut ialah pilihan tambahan" : "Saya menemui";
      return `${prefix}: ${names}. Saya telah membandingkan kos, tempoh lawatan dan aksesibiliti yang direkodkan. Pilihan manakah paling sesuai? Pilih nama tempat atau minta akses termudah, kos terendah atau lawatan tersingkat.`;
    }
    if (data.action === "clarify_preferences") {
      return hasState
        ? `Apakah jenis tarikan yang anda minati di ${state}?`
        : "Negeri manakah di Malaysia yang ingin anda lawati?";
    }
    if (data.action === "no_results") {
      return `Saya tidak menemui padanan tepat di ${state}. Pilihan anda masih disimpan. Cuba jenis tarikan atau negeri yang lain.`;
    }
    if (data.action === "comparison" && names) {
      return `${names} ialah padanan paling kuat berdasarkan maklumat yang direkodkan. Berikut ialah butirannya untuk membantu anda membuat keputusan.`;
    }
    return replies[data.action] || data.reply;
  }

  const replies = {
    greeting: "您好！请告诉我您想前往马来西亚的哪个州属。",
    help: "您可以告诉我州属、兴趣、入场费预算，以及家庭、长者或轮椅通行需求。",
    out_of_scope: "我的功能是协助规划马来西亚旅游和景点。请输入与旅游相关的消息。",
    low_confidence: "我不太明白这个旅游请求。请说明马来西亚的州属和您喜欢的景点类型。",
    request_refinement: "您想更改哪项偏好：地点、兴趣、预算还是无障碍需求？",
    clarify_accessibility: "旅客最重要的无障碍需求是什么？请选择下方一项，或输入多项需求。",
    no_alternatives: "没有更多符合条件的选择。请尝试更改其中一项旅行偏好。",
    previous_options_unavailable: "这次对话中还没有较早的推荐。请告诉我州属和您喜欢的地点类型。",
    show_previous_options: "当然可以。以下是之前的选择。您可以选择地点名称，或让我进行比较。",
    information_unavailable: "请先要求推荐，然后我才能说明其中一个建议景点。",
    choose_recommendation: "您想了解哪个建议地点？请选择下方其中一个地点名称。",
    comparison_unavailable: "目前记录的资料不足以进行这项比较。请选择地点名称或尝试其他比较方式。",
    goodbye: "再见。祝您愉快地规划马来西亚之旅。",
    reset: "您的旅行偏好已清除。您想去哪里？",
    reset_preferences: "已清除保存的旅行偏好。接下来您想探索马来西亚的哪个州属？",
  };
  if (data.action === "recommend" || data.action === "alternative") {
    const prefix = data.action === "alternative" ? "这里有更多选择" : "我找到了";
    return `${prefix}：${names}。我已比较所记录的费用、建议游览时间和无障碍情况。哪个选择最适合您？请选择地点名称，或询问最容易到达、费用最低或游览时间最短的地点。`;
  }
  if (data.action === "clarify_preferences") {
    return hasState
      ? `您对${state}的哪类景点感兴趣？`
      : "您想前往马来西亚的哪个州属？";
  }
  if (data.action === "no_results") {
    return `我在${state}找不到完全符合条件的景点。您的偏好仍已保存，请尝试其他景点类型或州属。`;
  }
  if (data.action === "comparison" && names) {
    return `根据已记录的资料，${names}是最符合条件的选择。以下详情可帮助您决定是否合适。`;
  }
  return replies[data.action] || data.reply;
}

function resizeMessageInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
}

function setVoiceInputState(active) {
  voiceInputActive = active;
  voiceInputButton.setAttribute("aria-pressed", String(active));
  voiceInputButton.classList.toggle("is-listening", active);
  voiceInputButton.querySelector(".voice-button-label").textContent = active
    ? t("stop")
    : t("speak");
}

if (SpeechRecognition) {
  speechRecognition = new SpeechRecognition();
  speechRecognition.lang = "en-MY";
  speechRecognition.continuous = false;
  speechRecognition.interimResults = true;

  speechRecognition.addEventListener("start", () => {
    setVoiceInputState(true);
    formStatus.textContent = "Listening… Speak your travel request.";
  });

  speechRecognition.addEventListener("result", event => {
    let transcript = "";
    for (let index = 0; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    input.value = [inputBeforeSpeech, transcript.trim()].filter(Boolean).join(" ");
    resizeMessageInput();
  });

  speechRecognition.addEventListener("end", () => {
    setVoiceInputState(false);
    formStatus.textContent = input.value.trim()
      ? "Voice input added. Check the message, then press Send."
      : "I could not hear a message. Please try again.";
    input.focus();
  });

  speechRecognition.addEventListener("error", event => {
    setVoiceInputState(false);
    const messages = {
      "not-allowed": "Microphone permission was not granted.",
      "no-speech": "I could not hear any speech. Please try again.",
      "audio-capture": "No microphone was detected.",
      network: "Voice recognition is temporarily unavailable.",
    };
    formStatus.textContent = messages[event.error]
      || "Voice recognition could not start. Please try again.";
  });

  voiceInputButton.addEventListener("click", () => {
    if (voiceInputActive) {
      speechRecognition.stop();
      return;
    }
    inputBeforeSpeech = input.value.trim();
    try {
      speechRecognition.start();
    } catch (error) {
      formStatus.textContent = "Voice recognition is already starting.";
    }
  });
} else {
  voiceInputButton.disabled = true;
  voiceInputButton.title = "Voice input is not supported by this browser.";
  voiceInputButton.setAttribute(
    "aria-label",
    "Voice input is not supported by this browser",
  );
}

function chooseGentleVoice() {
  if (!("speechSynthesis" in window)) return null;
  const languagePrefix = currentLanguage === "zh"
    ? "zh"
    : currentLanguage === "ms" ? "ms" : "en";
  const matchingVoices = window.speechSynthesis.getVoices().filter(voice => {
    return voice.lang.toLowerCase().startsWith(languagePrefix);
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
    const voice = matchingVoices.find(candidate => pattern.test(candidate.name));
    if (voice) return voice;
  }
  return matchingVoices.find(voice => /natural/i.test(voice.name))
    || matchingVoices[0]
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
  speaker.textContent = sender === "user" ? t("you") : "Maya";
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

  if (sender === "bot") {
    const speakButton = document.createElement("button");
    speakButton.className = "speak-button";
    speakButton.type = "button";
    speakButton.dataset.speak = text;
    speakButton.textContent = t("readAloud");
    speakButton.setAttribute("aria-label", "Read Maya's latest reply aloud");
    content.appendChild(speakButton);
  }

  row.appendChild(content);
  messages.appendChild(row);
  registerHistoryItem(row, text, sender);
  row.scrollIntoView({ block: "nearest" });
  return row;
}

const initialMessageRow = messages.querySelector(".message-row");
const initialMessageText = initialMessageRow?.querySelector(".assistant-message p")?.textContent;
if (initialMessageRow && initialMessageText) {
  initialMessageRow.chatData = {
    reply: UI_TEXT.en.welcome,
    action: "greeting",
    context: {},
    recommendations: [],
    suggestions: [],
  };
}

// Loading the NLP model can be the slowest part of the first message. Start it
// while the welcome screen is visible so the first reply feels faster.
formStatus.textContent = "Preparing Maya...";
fetch("/api/warmup")
  .then(response => {
    if (!response.ok) throw new Error("Warm-up failed");
    formStatus.textContent = "Maya is ready.";
    window.setTimeout(() => {
      if (formStatus.textContent === "Maya is ready.") formStatus.textContent = "";
    }, 2500);
  })
  .catch(() => {
    if (formStatus.textContent === "Preparing Maya...") formStatus.textContent = "";
  });

function labelFor(key) {
  const labels = {
    accessibility_needs: "Elderly access needs",
    elderly_friendly: "Elderly friendly",
    wheelchair_accessible: "Wheelchair accessible",
  };
  const label = labels[key]
    || key.replaceAll("_", " ").replace(/^./, value => value.toUpperCase());
  return localizeLabel(label);
}

function displayPreferenceValue(key, rawValue) {
  const accessibilityLabels = {
    low_walking: "Minimal walking",
    step_free: "Step-free access",
    seating: "Resting seats",
    accessible_toilet: "Accessible toilet",
    nearby_parking: "Nearby parking",
    shelter: "Shelter or shade",
  };
  if (Array.isArray(rawValue)) {
    return rawValue
      .map(value => {
        const label = key === "accessibility_needs"
          ? accessibilityLabels[value] || value
          : value;
        return localizeLabel(label);
      })
      .join(", ");
  }
  if (typeof rawValue === "boolean") return localizeLabel(rawValue ? "Yes" : "No");
  return localizeLabel(String(rawValue));
}

function showPreferences(context) {
  latestContext = context || {};
  preferences.replaceChildren();
  const preferenceOrder = [
    "state",
    "interests",
    "elderly_friendly",
    "accessibility_needs",
    "wheelchair_accessible",
    "maximum_fee",
    "duration_days",
    "duration_hours",
    "family_friendly",
  ];
  const entries = Object.entries(context || {})
    .filter(([, value]) => {
      return value !== null && value !== "" && (!Array.isArray(value) || value.length > 0);
    })
    .sort(([firstKey], [secondKey]) => {
      const firstIndex = preferenceOrder.indexOf(firstKey);
      const secondIndex = preferenceOrder.indexOf(secondKey);
      return (firstIndex < 0 ? preferenceOrder.length : firstIndex)
        - (secondIndex < 0 ? preferenceOrder.length : secondIndex);
    });
  if (!entries.length) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = t("status");
    detail.textContent = t("notProvided");
    wrapper.append(term, detail);
    preferences.appendChild(wrapper);
    return;
  }
  for (const [key, rawValue] of entries) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = labelFor(key);
    detail.textContent = displayPreferenceValue(key, rawValue);
    wrapper.append(term, detail);
    preferences.appendChild(wrapper);
  }
}

function showRecommendations(items, messageRow) {
  if (!messageRow || !Array.isArray(items) || !items.length) return;

  const content = messageRow.querySelector(".message-content");
  if (!content) return;
  content.classList.add("has-recommendations");

  const recommendationGroup = document.createElement("section");
  recommendationGroup.className = "recommendations message-recommendations";
  recommendationGroup.setAttribute(
    "aria-label",
    "Attractions recommended in this reply",
  );
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
    category.textContent = item.primary_category
      ? `${t("category")}: ${localizeLabel(item.primary_category)}`
      : "";
    const description = document.createElement("p");
    description.className = "recommendation-description";
    description.textContent = item.display_description || item.short_description || "";
    card.append(title, location, category, description);

    const facts = [
      item.cost_summary,
      item.duration_summary,
      Array.isArray(item.accessibility_features)
        ? null
        : item.accessibility_summary,
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

    if (Array.isArray(item.accessibility_features) && item.accessibility_features.length) {
      const accessSection = document.createElement("section");
      accessSection.className = "accessibility-details";
      accessSection.setAttribute("aria-label", `Accessibility details for ${item.attraction_name || "this attraction"}`);

      const accessHeading = document.createElement("h4");
      accessHeading.textContent = t("accessibilityDetails");
      const accessList = document.createElement("dl");
      accessList.className = "accessibility-feature-list";

      for (const feature of item.accessibility_features) {
        const row = document.createElement("div");
        row.className = `accessibility-feature accessibility-${feature.status || "unknown"}`;
        const label = document.createElement("dt");
        label.textContent = localizeLabel(feature.label);
        const value = document.createElement("dd");
        value.textContent = localizeLabel(feature.value);
        row.append(label, value);
        accessList.appendChild(row);
      }
      accessSection.append(accessHeading, accessList);
      card.appendChild(accessSection);
    }

    if (item.accessibility_reason) {
      const reasonSection = document.createElement("section");
      reasonSection.className = "accessibility-reason";
      const reasonHeading = document.createElement("h4");
      reasonHeading.textContent = t("accessibilityReason");
      const reasonText = document.createElement("p");
      reasonText.textContent = item.accessibility_reason;
      reasonSection.append(reasonHeading, reasonText);
      card.appendChild(reasonSection);
    }

    if (item.accessibility_notes) {
      const accessNote = document.createElement("p");
      accessNote.className = "accessibility-note";
      accessNote.textContent = item.accessibility_notes;
      card.appendChild(accessNote);
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
    const evidenceLinks = Array.isArray(item.accessibility_evidence_links)
      ? item.accessibility_evidence_links
      : [];
    const seenSourceUrls = new Set();
    const validSources = [...evidenceLinks, ...sourceLinks].filter(source => {
      if (!source || !source.url || seenSourceUrls.has(source.url)) return false;
      seenSourceUrls.add(source.url);
      return true;
    });
    if (validSources.length) {
      const sourceBlock = document.createElement("div");
      sourceBlock.className = "source-links";
      const sourceHeading = document.createElement("strong");
      sourceHeading.textContent = t("sources");
      sourceBlock.appendChild(sourceHeading);
      for (const source of validSources) {
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = localizeLabel(source.title) || t("visitorInformation");
        sourceBlock.appendChild(link);
      }
      card.appendChild(sourceBlock);
    }
    recommendationGroup.appendChild(card);
  }
  content.appendChild(recommendationGroup);
}

function showQuickReplies(suggestions) {
  latestSuggestions = suggestions || [];
  quickReplies.replaceChildren();
  for (const suggestion of suggestions || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = localizeLabel(suggestion.label);
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
    const data = await sendJson("/api/chat", {
      message,
      language: currentLanguage,
    });
    const localizedReply = localizeReply(data);
    const replyRow = addMessage(localizedReply, "bot");
    replyRow.chatData = data;
    showPreferences(data.context);
    showRecommendations(data.recommendations, replyRow);
    replyRow.scrollIntoView({ block: "nearest" });
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

easyAccessStartButton.addEventListener("click", () => {
  submitMessage("I am planning a comfortable trip for an elderly traveller");
});

input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  resizeMessageInput();
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
  if (button) playSpeechAudio(button);
});

function stopActiveAudio() {
  if (!activeAudio) return;
  activeAudio.pause();
  activeAudio.currentTime = 0;
  activeAudio = null;
}

function clearGeneratedAudio() {
  stopActiveAudio();
  for (const url of generatedAudioUrls) URL.revokeObjectURL(url);
  generatedAudioUrls.clear();
}

function useBrowserSpeechFallback(text) {
  if (!("speechSynthesis" in window)) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  if (preferredSpeechVoice) {
    utterance.voice = preferredSpeechVoice;
    utterance.lang = preferredSpeechVoice.lang;
  } else {
    utterance.lang = currentLanguage === "zh"
      ? "zh-CN"
      : currentLanguage === "ms" ? "ms-MY" : "en-MY";
  }
  utterance.rate = 0.86;
  utterance.pitch = 1.02;
  window.speechSynthesis.speak(utterance);
  return true;
}

async function playSpeechAudio(button) {
  const content = button.closest(".message-content");
  let player = content?.querySelector("audio.maya-audio-player");
  if (player?.src) {
    stopActiveAudio();
    activeAudio = player;
    player.currentTime = 0;
    await player.play();
    button.textContent = t("readAloud");
    return;
  }

  button.disabled = true;
  button.textContent = t("preparingAudio");
  try {
    const response = await fetch("/api/speech", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: button.dataset.speak,
        language: currentLanguage,
      }),
    });
    if (!response.ok) throw new Error("Audio generation failed");
    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);
    generatedAudioUrls.add(audioUrl);
    player = document.createElement("audio");
    player.className = "maya-audio-player";
    player.controls = false;
    player.hidden = true;
    player.preload = "metadata";
    player.src = audioUrl;
    player.setAttribute("aria-label", "Maya's spoken response");
    player.addEventListener("ended", () => {
      if (activeAudio === player) activeAudio = null;
      button.textContent = t("readAloud");
    });
    content?.appendChild(player);
    stopActiveAudio();
    activeAudio = player;
    await player.play();
    button.textContent = t("readAloud");
  } catch (error) {
    if (useBrowserSpeechFallback(button.dataset.speak)) {
      formStatus.textContent = "Using the browser voice because generated audio is unavailable.";
    } else {
      formStatus.textContent = "Maya's audio is unavailable on this device.";
    }
    button.textContent = t("readAloud");
  } finally {
    button.disabled = false;
  }
}

resetButton.addEventListener("click", async () => {
  resetButton.disabled = true;
  clearGeneratedAudio();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const data = await sendJson("/api/reset");
    messages.replaceChildren();
    historyList.replaceChildren();
    historyEmpty.hidden = false;
    messageCounter = 0;
    const replyRow = addMessage(localizeReply(data), "bot");
    replyRow.chatData = data;
    showPreferences({});
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
  stopActiveAudio();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const data = await sendJson("/api/reset-preferences");
    const replyRow = addMessage(localizeReply(data), "bot");
    replyRow.chatData = data;
    showPreferences(data.context);
    showRecommendations(data.recommendations, replyRow);
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
  textSizeButton.querySelector(".control-label").textContent = largeText
    ? t("normalText")
    : t("largerText");
  contrastButton.querySelector(".control-label").textContent = highContrast
    ? t("standardColours")
    : t("highContrast");
}

function applySavedSidebarSetting() {
  const visible = localStorage.getItem("tripPanelVisible") !== "false";
  tripSidebar.hidden = !visible;
  document.body.classList.toggle("sidebar-hidden", !visible);
  sidebarToggleButton.setAttribute("aria-expanded", String(visible));
  sidebarToggleButton.querySelector(".control-label").textContent = visible
    ? t("hideTripPanel")
    : t("showTripPanel");
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

function rebuildLocalizedHistory() {
  historyList.replaceChildren();
  messageCounter = 0;
  const rows = messages.querySelectorAll(".message-row");
  for (const row of rows) {
    const sender = row.classList.contains("user-row") ? "user" : "bot";
    const text = row.querySelector(
      sender === "user" ? ".user-message p" : ".assistant-message p",
    )?.textContent;
    if (text) registerHistoryItem(row, text, sender);
  }
}

function applyLanguage() {
  document.documentElement.lang = currentLanguage === "zh" ? "zh-CN" : currentLanguage;
  languageSelect.value = currentLanguage;
  document.querySelectorAll("[data-i18n]").forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(element => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });

  refreshPreferredVoice();

  messages.querySelectorAll(".assistant-row").forEach(row => {
    if (!row.chatData) return;
    const localized = localizeReply(row.chatData);
    const paragraph = row.querySelector(".assistant-message p");
    const speakButton = row.querySelector("button[data-speak]");
    if (paragraph) paragraph.textContent = localized;
    if (speakButton) {
      speakButton.dataset.speak = localized;
      speakButton.textContent = t("readAloud");
    }
    row.querySelector(".message-recommendations")?.remove();
    row.querySelector(".message-content")?.classList.remove("has-recommendations");
    showRecommendations(row.chatData.recommendations, row);
  });

  showPreferences(latestContext);
  showQuickReplies(latestSuggestions);
  applySavedDisplaySettings();
  applySavedSidebarSetting();
  rebuildLocalizedHistory();
}

languageSelect.addEventListener("change", () => {
  currentLanguage = SUPPORTED_LANGUAGES.has(languageSelect.value)
    ? languageSelect.value
    : "en";
  localStorage.setItem("jomvoyageLanguage", currentLanguage);
  applyLanguage();
});

applyLanguage();
