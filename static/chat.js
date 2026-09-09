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
const savedConversationsList = document.querySelector("#saved-conversations");
const savedConversationsEmpty = document.querySelector("#saved-conversations-empty");
const currentConversationTitle = document.querySelector("#current-conversation-title");
let messageCounter = 0;
let preferredSpeechVoice = null;
let activeAudio = null;
const generatedAudioUrls = new Set();
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let speechRecognition = null;
let voiceInputActive = false;
let inputBeforeSpeech = "";
let latestContext = {};
let latestSessionState = null;
let latestSuggestions = Array.from(
  quickReplies.querySelectorAll("button[data-message]"),
  button => ({ label: button.textContent.trim(), message: button.dataset.message }),
);
const SUPPORTED_LANGUAGES = new Set(["en", "ms", "zh"]);
let currentLanguage = localStorage.getItem("jomvoyageLanguage") || "en";
if (!SUPPORTED_LANGUAGES.has(currentLanguage)) currentLanguage = "en";
const SAVED_CONVERSATIONS_KEY = "jomvoyageSavedConversations";
const ACTIVE_CONVERSATION_KEY = "jomvoyageActiveConversation";
const MAX_SAVED_CONVERSATIONS = 8;
const MAX_SAVED_MESSAGES = 40;
let activeConversationId = localStorage.getItem(ACTIVE_CONVERSATION_KEY) || createConversationId();
let skipCurrentSaveOnReset = false;

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
    savedConversations: "Saved conversations",
    savedConversationsHelp: "Reopen an earlier trip and continue planning.",
    savedConversationsEmpty: "Your saved trips will appear here.",
    renameConversation: "Rename",
    deleteConversation: "Delete",
    deleteConversationConfirm: "Delete this saved conversation?",
    saveConversationName: "Save",
    cancelConversationAction: "Cancel",
    confirmDeleteConversation: "Yes, delete",
    newTripTitle: "New Malaysia Trip",
    tripTitleSuffix: "Trip",
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
    photoCredit: "Photo",
    originalRecordedDetails: "Original recorded details (English)",
    listening: "Listening… Speak your travel request.",
    voiceAdded: "Voice input added. Check the message, then press Send.",
    noSpeech: "I could not hear a message. Please try again.",
    microphoneDenied: "Microphone permission was not granted.",
    noMicrophone: "No microphone was detected.",
    recognitionUnavailable: "Voice recognition is temporarily unavailable.",
    recognitionFailed: "Voice recognition could not start. Please try again.",
    recognitionStarting: "Voice recognition is already starting.",
    preparingMaya: "Preparing Maya...",
    mayaReady: "Maya is ready.",
    findingResponse: "Finding a helpful response...",
    preferencesCleared: "Trip preferences cleared.",
    browserVoice: "Using the browser voice because generated audio is unavailable.",
    audioUnavailable: "Maya's audio is unavailable on this device.",
    storageFull: "Saved-conversation storage is full on this browser.",
    openingSavedTrip: "Opening saved trip...",
    savedTripOpened: "Saved trip opened.",
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
    savedConversations: "Perbualan tersimpan",
    savedConversationsHelp: "Buka semula perjalanan terdahulu dan teruskan merancang.",
    savedConversationsEmpty: "Perjalanan tersimpan akan dipaparkan di sini.",
    renameConversation: "Namakan semula",
    deleteConversation: "Padam",
    deleteConversationConfirm: "Padam perbualan tersimpan ini?",
    saveConversationName: "Simpan",
    cancelConversationAction: "Batal",
    confirmDeleteConversation: "Ya, padam",
    newTripTitle: "Perjalanan Malaysia Baharu",
    tripTitleSuffix: "Perjalanan",
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
    photoCredit: "Foto",
    originalRecordedDetails: "Maklumat asal yang direkodkan (Bahasa Inggeris)",
    listening: "Sedang mendengar… Sebut permintaan perjalanan anda.",
    voiceAdded: "Input suara telah ditambah. Semak mesej, kemudian tekan Hantar.",
    noSpeech: "Saya tidak dapat mendengar mesej. Sila cuba lagi.",
    microphoneDenied: "Kebenaran mikrofon tidak diberikan.",
    noMicrophone: "Mikrofon tidak dikesan.",
    recognitionUnavailable: "Pengecaman suara tidak tersedia buat sementara waktu.",
    recognitionFailed: "Pengecaman suara tidak dapat dimulakan. Sila cuba lagi.",
    recognitionStarting: "Pengecaman suara sedang dimulakan.",
    preparingMaya: "Maya sedang disediakan...",
    mayaReady: "Maya sudah bersedia.",
    findingResponse: "Sedang mencari jawapan yang sesuai...",
    preferencesCleared: "Pilihan perjalanan telah dikosongkan.",
    browserVoice: "Suara pelayar digunakan kerana audio janaan tidak tersedia.",
    audioUnavailable: "Audio Maya tidak tersedia pada peranti ini.",
    storageFull: "Ruang simpanan perbualan pada pelayar ini sudah penuh.",
    openingSavedTrip: "Membuka perjalanan tersimpan...",
    savedTripOpened: "Perjalanan tersimpan telah dibuka.",
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
    savedConversations: "已保存的对话",
    savedConversationsHelp: "重新打开之前的旅程并继续规划。",
    savedConversationsEmpty: "保存的旅程将显示在这里。",
    renameConversation: "重命名",
    deleteConversation: "删除",
    deleteConversationConfirm: "删除这个已保存的对话吗？",
    saveConversationName: "保存",
    cancelConversationAction: "取消",
    confirmDeleteConversation: "确认删除",
    newTripTitle: "新的马来西亚之旅",
    tripTitleSuffix: "之旅",
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
    photoCredit: "照片",
    originalRecordedDetails: "原始记录详情（英语）",
    listening: "正在聆听……请说出您的旅游需求。",
    voiceAdded: "语音内容已加入。请检查消息，然后按发送。",
    noSpeech: "没有听到语音，请重试。",
    microphoneDenied: "未获得麦克风权限。",
    noMicrophone: "未检测到麦克风。",
    recognitionUnavailable: "语音识别暂时无法使用。",
    recognitionFailed: "无法启动语音识别，请重试。",
    recognitionStarting: "语音识别正在启动。",
    preparingMaya: "正在准备 Maya...",
    mayaReady: "Maya 已准备就绪。",
    findingResponse: "正在寻找合适的回答...",
    preferencesCleared: "旅行偏好已清除。",
    browserVoice: "生成语音不可用，现正使用浏览器语音。",
    audioUnavailable: "此设备无法播放 Maya 的语音。",
    storageFull: "此浏览器的对话储存空间已满。",
    openingSavedTrip: "正在打开已保存的旅程...",
    savedTripOpened: "已打开保存的旅程。",
    you: "您",
  },
};

const HISTORY_TOPICS = {
  en: {
    greeting: "Welcome",
    help: "Help",
    out_of_scope: "Travel questions only",
    low_confidence: "Clarify request",
    clarify_preferences: "Trip preferences",
    clarify_accessibility: "Accessibility needs",
    recommend: "Recommendations",
    alternative: "More options",
    no_alternatives: "No more options",
    no_results: "No matching places",
    information: "Attraction details",
    information_unavailable: "Attraction details",
    choose_recommendation: "Choose a place",
    comparison: "Place comparison",
    comparison_unavailable: "Place comparison",
    request_refinement: "Change preferences",
    change_location: "Change location",
    change_interest: "Change interest",
    change_budget: "Change budget",
    change_accessibility: "Change accessibility",
    show_previous_options: "Previous options",
    previous_options_unavailable: "Previous options",
    confirm_attraction: "Confirm place",
    reset: "New trip",
    reset_preferences: "Reset preferences",
    preferences_unchanged: "Preferences unchanged",
    goodbye: "Goodbye",
    response: "Reply",
    more_options: "More options",
  },
  ms: {
    greeting: "Selamat datang",
    help: "Bantuan",
    out_of_scope: "Soalan perjalanan sahaja",
    low_confidence: "Jelaskan permintaan",
    clarify_preferences: "Pilihan perjalanan",
    clarify_accessibility: "Keperluan aksesibiliti",
    recommend: "Cadangan tempat",
    alternative: "Pilihan tambahan",
    no_alternatives: "Tiada pilihan lagi",
    no_results: "Tiada tempat sepadan",
    information: "Maklumat tarikan",
    information_unavailable: "Maklumat tarikan",
    choose_recommendation: "Pilih tempat",
    comparison: "Perbandingan tempat",
    comparison_unavailable: "Perbandingan tempat",
    request_refinement: "Ubah pilihan",
    change_location: "Ubah lokasi",
    change_interest: "Ubah minat",
    change_budget: "Ubah bajet",
    change_accessibility: "Ubah aksesibiliti",
    show_previous_options: "Pilihan terdahulu",
    previous_options_unavailable: "Pilihan terdahulu",
    confirm_attraction: "Sahkan tempat",
    reset: "Perjalanan baharu",
    reset_preferences: "Tetapkan semula pilihan",
    preferences_unchanged: "Pilihan tidak berubah",
    goodbye: "Selamat tinggal",
    response: "Jawapan",
    more_options: "Pilihan tambahan",
  },
  zh: {
    greeting: "欢迎",
    help: "帮助",
    out_of_scope: "仅限旅游问题",
    low_confidence: "说明请求",
    clarify_preferences: "旅行偏好",
    clarify_accessibility: "无障碍需求",
    recommend: "景点推荐",
    alternative: "更多选择",
    no_alternatives: "没有更多选择",
    no_results: "没有符合的地点",
    information: "景点详情",
    information_unavailable: "景点详情",
    choose_recommendation: "选择地点",
    comparison: "地点比较",
    comparison_unavailable: "地点比较",
    request_refinement: "更改偏好",
    change_location: "更改地点",
    change_interest: "更改兴趣",
    change_budget: "更改预算",
    change_accessibility: "更改无障碍需求",
    show_previous_options: "之前的选择",
    previous_options_unavailable: "之前的选择",
    confirm_attraction: "确认地点",
    reset: "新旅程",
    reset_preferences: "重设偏好",
    preferences_unchanged: "偏好未更改",
    goodbye: "再见",
    response: "回复",
    more_options: "更多选择",
  },
};

function t(key) {
  return UI_TEXT[currentLanguage]?.[key] || UI_TEXT.en[key] || key;
}

const LOCALIZED_LABELS = {
  ms: {
    "Show me more options": "Tunjukkan lebih banyak pilihan",
    "Switch to elderly-friendly trip": "Tukar kepada perjalanan mesra warga emas",
    Location: "Lokasi",
    Interest: "Minat",
    Budget: "Bajet",
    Accessibility: "Aksesibiliti",
    "Up to RM20": "Sehingga RM20",
    "Up to RM50": "Sehingga RM50",
    "Up to RM100": "Sehingga RM100",
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
    "Suitable with assistance": "Sesuai dengan bantuan",
    "Not recommended": "Tidak disyorkan",
    Low: "Rendah",
    Moderate: "Sederhana",
    High: "Tinggi",
    Near: "Dekat",
    Far: "Jauh",
    Unknown: "Tidak diketahui",
    "Not measured": "Tidak diukur",
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
    "Elderly access needs": "Keperluan akses warga emas",
    Adventure: "Pengembaraan",
    "Beach and Island": "Pantai dan pulau",
    Culture: "Budaya",
    "Family Attraction": "Tarikan keluarga",
    "Farm and Visitor Experience": "Ladang dan pengalaman pelawat",
    Food: "Makanan",
    "Heritage and History": "Warisan dan sejarah",
    "Heritage and Visitor Attraction": "Warisan dan tarikan pelawat",
    "Museum and Gallery": "Muzium dan galeri",
    "Park and Recreation": "Taman dan rekreasi",
    "Performance and Culture": "Persembahan dan budaya",
    "Religious Site": "Tempat keagamaan",
    "Scenic Transport": "Pengangkutan pemandangan",
    Shopping: "Membeli-belah",
    "Theme Park": "Taman tema",
    "Urban Attraction": "Tarikan bandar",
    "Wellness and Relaxation": "Kesejahteraan dan santai",
  },
  zh: {
    "Show me more options": "显示更多选择",
    "Switch to elderly-friendly trip": "切换为长者友善旅程",
    Location: "地点",
    Interest: "兴趣",
    Budget: "预算",
    Accessibility: "无障碍需求",
    "Up to RM20": "最高 RM20",
    "Up to RM50": "最高 RM50",
    "Up to RM100": "最高 RM100",
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
    "Suitable with assistance": "适合在协助下游览",
    "Not recommended": "不建议",
    Low: "低",
    Moderate: "中等",
    High: "高",
    Near: "附近",
    Far: "较远",
    Unknown: "未知",
    "Not measured": "未测量",
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
    "Elderly access needs": "长者通行需求",
    Adventure: "探险",
    "Beach and Island": "海滩与岛屿",
    Culture: "文化",
    "Family Attraction": "家庭景点",
    "Farm and Visitor Experience": "农场与参观体验",
    Food: "美食",
    "Heritage and History": "文化遗产与历史",
    "Heritage and Visitor Attraction": "文化遗产景点",
    "Museum and Gallery": "博物馆与美术馆",
    "Park and Recreation": "公园与休闲",
    "Performance and Culture": "表演与文化",
    "Religious Site": "宗教场所",
    "Scenic Transport": "观景交通",
    Shopping: "购物",
    "Theme Park": "主题乐园",
    "Urban Attraction": "城市景点",
    "Wellness and Relaxation": "康养与休闲",
  },
};

function localizeLabel(label) {
  return LOCALIZED_LABELS[currentLanguage]?.[label] || label;
}

function localizedCardDescription(item) {
  const original = item.display_description || item.short_description || "";
  if (currentLanguage === "en" || !original) return original;
  const name = item.attraction_name || (currentLanguage === "zh" ? "该景点" : "Tempat ini");
  const category = localizeLabel(item.primary_category || (currentLanguage === "zh" ? "旅游" : "pelancongan"));
  const location = [item.city_district, item.state_territory].filter(Boolean)
    .join(currentLanguage === "zh" ? "、" : ", ");
  if (currentLanguage === "zh") {
    return location
      ? `${name}是位于${location}的${category}景点。`
      : `${name}属于${category}景点。`;
  }
  return location
    ? `${name} ialah tarikan ${String(category).toLocaleLowerCase("ms-MY")} di ${location}.`
    : `${name} ialah tarikan ${String(category).toLocaleLowerCase("ms-MY")}.`;
}

function localizedFact(fact) {
  if (currentLanguage === "en" || !fact) return fact;
  let match = String(fact).match(/^Recorded entrance fee: RM(.+)$/i);
  if (match) return currentLanguage === "zh"
    ? `记录的入场费：RM${match[1]}`
    : `Bayaran masuk yang direkodkan: RM${match[1]}`;
  match = String(fact).match(/^Recorded entrance-fee range: RM(.+)-RM(.+)$/i);
  if (match) return currentLanguage === "zh"
    ? `记录的入场费范围：RM${match[1]}–RM${match[2]}`
    : `Julat bayaran masuk yang direkodkan: RM${match[1]}–RM${match[2]}`;
  match = String(fact).match(/^Recorded entrance fee starts from RM(.+)$/i);
  if (match) return currentLanguage === "zh"
    ? `记录的入场费从 RM${match[1]} 起`
    : `Bayaran masuk yang direkodkan bermula dari RM${match[1]}`;
  match = String(fact).match(/^Suggested visit duration: about (.+) hour\(s\)$/i);
  if (match) return currentLanguage === "zh"
    ? `建议游览时间：约 ${match[1]} 小时`
    : `Tempoh lawatan yang dicadangkan: kira-kira ${match[1]} jam`;
  if (/^Free entry is recorded$/i.test(String(fact))) {
    return currentLanguage === "zh" ? "记录为免费入场" : "Kemasukan percuma direkodkan";
  }
  return fact;
}

function localizedAccessibilityReason() {
  if (currentLanguage === "ms") {
    return "Sumber merekodkan kemudahan atau batasan akses yang diringkaskan dalam jadual di atas.";
  }
  if (currentLanguage === "zh") {
    return "资料来源记录了上表所概述的无障碍设施或限制。";
  }
  return "";
}

function localizedAccessibilityNote() {
  if (currentLanguage === "ms") {
    return "Jadual di atas menunjukkan maklumat akses yang direkodkan. Buka maklumat asal di bawah untuk membaca butiran dan batasan khusus.";
  }
  if (currentLanguage === "zh") {
    return "上表显示已记录的无障碍资料。展开下方的原始记录，可查看具体详情和限制。";
  }
  return "";
}

function appendOriginalEnglishDetails(card, text) {
  if (currentLanguage === "en" || !text) return;
  const details = document.createElement("details");
  details.className = "original-recorded-details";
  const summary = document.createElement("summary");
  summary.textContent = t("originalRecordedDetails");
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  details.append(summary, paragraph);
  card.appendChild(details);
}

function localizeReply(data) {
  const reply = localizeReplyBody(data);
  const unchanged = data.unchanged_preferences || {};
  if (currentLanguage === "en" || !Object.keys(unchanged).length) return reply;
  const interestOnly = Object.keys(unchanged).length === 1 && unchanged.interests;
  const interests = translatedInterests(data.context || {});
  if (currentLanguage === "ms") {
    return (interestOnly ? `Minat anda sudah ditetapkan kepada ${interests}. `
      : "Pilihan tersebut sudah disimpan. ") + reply;
  }
  return (interestOnly ? `您的兴趣已经设为${interests}。`
    : "这些偏好已经保存。") + reply;
}

function translatedInterests(context) {
  return (context.interests || []).map(value =>
    localizeLabel(value.replace(/^./, letter => letter.toUpperCase())),
  ).join(currentLanguage === "zh" ? "、" : ", ");
}

function localizedNoResults(data) {
  const context = data.context || {};
  const chinese = currentLanguage === "zh";
  const state = context.state || (chinese ? "该州属" : "negeri tersebut");
  const interests = translatedInterests(context);
  const needs = [];
  if (context.wheelchair_accessible) needs.push(chinese ? "已记录的轮椅通行设施" : "akses kerusi roda yang direkodkan");
  if (context.elderly_friendly) needs.push(chinese ? "已记录的长者适宜度" : "kesesuaian warga emas yang direkodkan");
  if (context.family_friendly) needs.push(chinese ? "适合家庭" : "mesra keluarga");
  if (context.maximum_fee != null) needs.push(chinese ? `入场费不超过 RM${context.maximum_fee}` : `bayaran masuk tidak melebihi RM${context.maximum_fee}`);
  const accessLabels = {
    low_walking: ["少量步行", "berjalan minimum"],
    step_free: ["无台阶通道", "akses tanpa tangga"],
    seating: ["休息座椅", "tempat duduk rehat"],
    accessible_toilet: ["无障碍厕所", "tandas mesra OKU"],
    nearby_parking: ["附近停车位", "tempat letak kereta berdekatan"],
    shelter: ["遮阳或有盖空间", "tempat berteduh"],
  };
  for (const need of context.accessibility_needs || []) {
    needs.push(accessLabels[need]?.[chinese ? 0 : 1] || need);
  }
  if (chinese) {
    const requirements = needs.length ? `，并同时符合以下需求：${needs.join("、")}` : "";
    return `在现有记录中，我找不到位于${state}的${interests}景点${requirements}。这不代表这样的地点不存在。您的偏好仍已保存。您想更改地点、兴趣还是无障碍需求？`;
  }
  const requirements = needs.length ? ` yang memenuhi semua keperluan ini: ${needs.join("; ")}` : "";
  return `Dalam maklumat yang direkodkan, saya tidak menemui padanan tepat untuk tarikan ${interests} di ${state}${requirements}. Ini tidak bermakna tempat sedemikian tidak wujud. Pilihan anda masih disimpan. Pilihan manakah yang ingin anda ubah: lokasi, minat atau aksesibiliti?`;
}

function localizeReplyBody(data) {
  if (currentLanguage === "en") return data.reply;
  const names = (data.recommendations || [])
    .map(item => item.attraction_name)
    .filter(Boolean)
    .join(currentLanguage === "zh" ? "、" : ", ");
  const state = data.context?.state || (currentLanguage === "zh" ? "该州属" : "negeri tersebut");
  const hasState = Boolean(data.context?.state);

  if (currentLanguage === "ms") {
    const replies = {
      greeting: UI_TEXT.ms.welcome,
      help: "Anda boleh memberitahu saya negeri, minat, bajet bayaran masuk serta keperluan keluarga, warga emas atau akses kerusi roda.",
      out_of_scope: "Saya direka untuk membantu perancangan perjalanan dan tarikan di Malaysia. Sila masukkan mesej berkaitan perjalanan.",
      low_confidence: "Saya kurang memahami permintaan itu. Sila tanya tentang perjalanan di Malaysia, seperti negeri dan jenis tarikan yang anda minati.",
      request_refinement: "Pilihan manakah yang ingin anda ubah: lokasi, minat atau aksesibiliti?",
      change_location: "Negeri atau wilayah persekutuan manakah yang ingin anda lawati sebagai ganti?",
      change_interest: "Apakah jenis tarikan lain yang anda minati?",
      change_budget: "Apakah bajet maksimum baharu untuk bayaran masuk? Pilih jumlah di bawah atau taip jumlah lain dalam RM.",
      change_accessibility: "Apakah bantuan aksesibiliti atau mobiliti yang paling penting?",
      clarify_accessibility: "Apakah keperluan akses yang paling penting untuk pelancong tersebut? Pilih satu di bawah atau taipkan beberapa keperluan.",
      no_alternatives: "Tiada lagi pilihan lain yang sepadan. Pilihan manakah yang ingin anda ubah: lokasi, minat atau aksesibiliti?",
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
      const accessibilityNeedCount =
        (data.context?.accessibility_needs || []).length
        + (data.context?.wheelchair_accessible ? 1 : 0);
      const multipleNeeds = accessibilityNeedCount > 1
        ? " Setiap tempat memenuhi sekurang-kurangnya satu keperluan aksesibiliti yang dipilih. Tempat yang memenuhi lebih banyak keperluan disenaraikan dahulu."
        : "";
      return `${prefix}: ${names}. Saya telah membandingkan kos, tempoh lawatan dan aksesibiliti yang direkodkan. Pilihan manakah paling sesuai? Pilih nama tempat atau minta akses termudah, kos terendah atau lawatan tersingkat.${multipleNeeds}`;
    }
    if (data.action === "clarify_preferences") {
      return hasState
        ? `Apakah jenis tarikan yang anda minati di ${state}?`
        : "Negeri manakah di Malaysia yang ingin anda lawati?";
    }
    if (data.action === "no_results") {
      return localizedNoResults(data);
    }
    if (data.action === "comparison" && names) {
      return `${names} ialah padanan paling kuat berdasarkan maklumat yang direkodkan. Berikut ialah butirannya untuk membantu anda membuat keputusan.`;
    }
    return replies[data.action] || data.reply;
  }

  const replies = {
    greeting: UI_TEXT.zh.welcome,
    help: "您可以告诉我州属、兴趣、入场费预算，以及家庭、长者或轮椅通行需求。",
    out_of_scope: "我的功能是协助规划马来西亚旅游和景点。请输入与旅游相关的消息。",
    low_confidence: "我不太明白这个旅游请求。请说明马来西亚的州属和您喜欢的景点类型。",
    request_refinement: "您想更改哪项偏好：地点、兴趣还是无障碍需求？",
    change_location: "您想改去马来西亚的哪个州属或联邦直辖区？",
    change_interest: "您想改选哪一种景点类型？",
    change_budget: "您的新入场费上限是多少？请选择下方金额，或输入其他 RM 金额。",
    change_accessibility: "哪项无障碍或行动辅助对旅客最重要？",
    clarify_accessibility: "旅客最重要的无障碍需求是什么？请选择下方一项，或输入多项需求。",
    no_alternatives: "没有更多符合条件的选择。您想更改地点、兴趣还是无障碍需求？",
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
    const accessibilityNeedCount =
      (data.context?.accessibility_needs || []).length
      + (data.context?.wheelchair_accessible ? 1 : 0);
    const multipleNeeds = accessibilityNeedCount > 1
      ? " 每个地点至少符合一项您选择的无障碍需求，符合较多需求的地点会优先显示。"
      : "";
    return `${prefix}：${names}。我已比较所记录的费用、建议游览时间和无障碍情况。哪个选择最适合您？请选择地点名称，或询问最容易到达、费用最低或游览时间最短的地点。${multipleNeeds}`;
  }
  if (data.action === "clarify_preferences") {
    return hasState
      ? `您对${state}的哪类景点感兴趣？`
      : "您想前往马来西亚的哪个州属？";
  }
  if (data.action === "no_results") {
    return localizedNoResults(data);
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
    formStatus.textContent = t("listening");
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
      ? t("voiceAdded")
      : t("noSpeech");
    input.focus();
  });

  speechRecognition.addEventListener("error", event => {
    setVoiceInputState(false);
    const messages = {
      "not-allowed": t("microphoneDenied"),
      "no-speech": t("noSpeech"),
      "audio-capture": t("noMicrophone"),
      network: t("recognitionUnavailable"),
    };
    formStatus.textContent = messages[event.error]
      || t("recognitionFailed");
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
      formStatus.textContent = t("recognitionStarting");
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

function shortenHistoryTopic(value, maximumLength = 30) {
  const cleaned = String(value || "").replace(/\s+/g, " ").trim();
  if (cleaned.length <= maximumLength) return cleaned;
  return `${cleaned.slice(0, maximumLength - 1).trimEnd()}…`;
}

function createConversationId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `trip-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readSavedConversations() {
  try {
    const saved = JSON.parse(localStorage.getItem(SAVED_CONVERSATIONS_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter(item => item && item.id) : [];
  } catch (error) {
    return [];
  }
}

function writeSavedConversations(conversations) {
  try {
    localStorage.setItem(
      SAVED_CONVERSATIONS_KEY,
      JSON.stringify(conversations.slice(0, MAX_SAVED_CONVERSATIONS)),
    );
    return true;
  } catch (error) {
    formStatus.textContent = t("storageFull");
    return false;
  }
}

function titleCase(value) {
  return String(value || "").replace(/\b\w/g, letter => letter.toUpperCase());
}

function automaticConversationTitle(context) {
  const state = context?.state;
  const interest = context?.interests?.[0];
  const parts = [];
  if (state) parts.push(state);
  if (interest) parts.push(titleCase(localizeLabel(interest)));
  if (!parts.length) return t("newTripTitle");
  if (currentLanguage === "zh") return `${parts.join(" · ")}${t("tripTitleSuffix")}`;
  if (currentLanguage === "ms") return `${t("tripTitleSuffix")}: ${parts.join(" · ")}`;
  return `${parts.join(" ")} ${t("tripTitleSuffix")}`;
}

function displayedConversationTitle(conversation) {
  if (!conversation) return t("newTripTitle");
  return conversation.customTitle
    ? (conversation.title || t("newTripTitle"))
    : automaticConversationTitle(conversation.context || {});
}

function conversationMessages() {
  return Array.from(messages.querySelectorAll(".message-row"))
    .slice(-MAX_SAVED_MESSAGES)
    .map(row => {
      const sender = row.classList.contains("user-row") ? "user" : "bot";
      const text = row.querySelector(
        sender === "user" ? ".user-message p" : ".assistant-message p",
      )?.textContent || "";
      return {
        sender,
        text,
        chatData: sender === "bot" && row.chatData ? row.chatData : null,
      };
    });
}

function saveCurrentConversation() {
  const savedMessages = conversationMessages();
  if (!savedMessages.some(message => message.sender === "user")) return;

  const conversations = readSavedConversations();
  const existing = conversations.find(item => item.id === activeConversationId);
  const conversation = {
    id: activeConversationId,
    title: existing?.customTitle
      ? existing.title
      : automaticConversationTitle(latestContext),
    customTitle: Boolean(existing?.customTitle),
    updatedAt: new Date().toISOString(),
    language: currentLanguage,
    context: latestContext,
    sessionState: latestSessionState || { context: latestContext },
    messages: savedMessages,
  };
  const next = [conversation, ...conversations.filter(item => item.id !== activeConversationId)]
    .sort((first, second) => String(second.updatedAt).localeCompare(String(first.updatedAt)));
  if (writeSavedConversations(next)) {
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, activeConversationId);
    currentConversationTitle.textContent = conversation.title;
    renderSavedConversations();
  }
}

function savedDateLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const locale = currentLanguage === "zh" ? "zh-CN" : currentLanguage === "ms" ? "ms-MY" : "en-MY";
  return date.toLocaleString(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderSavedConversations() {
  const conversations = readSavedConversations();
  savedConversationsList.replaceChildren();
  savedConversationsEmpty.hidden = conversations.length > 0;

  for (const conversation of conversations) {
    const conversationTitle = displayedConversationTitle(conversation);
    const item = document.createElement("li");
    item.className = "saved-conversation-item";
    item.classList.toggle("active", conversation.id === activeConversationId);

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "saved-conversation-open";
    openButton.dataset.openConversation = conversation.id;
    openButton.setAttribute("aria-label", `Open saved trip: ${conversationTitle}`);
    const title = document.createElement("strong");
    title.textContent = conversationTitle;
    const date = document.createElement("small");
    date.textContent = savedDateLabel(conversation.updatedAt);
    openButton.append(title, date);

    const actions = document.createElement("div");
    actions.className = "saved-conversation-actions";
    const renameButton = document.createElement("button");
    renameButton.type = "button";
    renameButton.dataset.renameConversation = conversation.id;
    renameButton.textContent = t("renameConversation");
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.dataset.deleteConversation = conversation.id;
    deleteButton.textContent = t("deleteConversation");
    actions.append(renameButton, deleteButton);

    item.append(openButton, actions);
    savedConversationsList.appendChild(item);
  }
}

function clearConversationDisplay() {
  clearGeneratedAudio();
  messages.replaceChildren();
  historyList.replaceChildren();
  historyEmpty.hidden = false;
  messageCounter = 0;
}

async function openSavedConversation(conversationId, saveCurrent = true) {
  const conversation = readSavedConversations().find(item => item.id === conversationId);
  if (!conversation) return;
  if (saveCurrent && conversationId !== activeConversationId) saveCurrentConversation();

  formStatus.textContent = t("openingSavedTrip");
  try {
    const restored = await sendJson("/api/restore-session", {
      session_state: conversation.sessionState || { context: conversation.context || {} },
    });
    activeConversationId = conversation.id;
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, activeConversationId);
    latestSessionState = restored.session_state;
    latestContext = restored.context || {};
    if (SUPPORTED_LANGUAGES.has(conversation.language)) {
      currentLanguage = conversation.language;
      localStorage.setItem("jomvoyageLanguage", currentLanguage);
      applyLanguage();
    }

    clearConversationDisplay();
    let lastBotData = null;
    for (const savedMessage of conversation.messages || []) {
      const text = savedMessage.sender === "bot" && savedMessage.chatData
        ? localizeReply(savedMessage.chatData)
        : savedMessage.text;
      const row = addMessage(text, savedMessage.sender);
      if (savedMessage.sender === "bot" && savedMessage.chatData) {
        row.chatData = savedMessage.chatData;
        refreshHistoryItem(row);
        showRecommendations(savedMessage.chatData.recommendations, row);
        lastBotData = savedMessage.chatData;
      }
    }
    currentConversationTitle.textContent = displayedConversationTitle(conversation);
    showPreferences(latestContext);
    showQuickReplies(lastBotData?.suggestions || []);
    renderSavedConversations();
    formStatus.textContent = t("savedTripOpened");
  } catch (error) {
    formStatus.textContent = error.message;
  }
  input.focus();
}

function userHistoryTopic(text) {
  const normalized = text.trim();
  const moreOptionsPattern = /(?:show|give|显示|查看|tunjukkan).*?(?:more|additional|更多|其他|lebih banyak|lain).*?(?:options?|choices?|选择|pilihan)/i;
  if (moreOptionsPattern.test(normalized)) {
    return HISTORY_TOPICS[currentLanguage].more_options;
  }

  const informationPatterns = [
    /(?:tell me about|information about)\s+(.+)/i,
    /(?:ceritakan tentang|maklumat tentang)\s+(.+)/i,
    /(?:告诉我关于|介绍一下)\s*(.+)/,
  ];
  for (const pattern of informationPatterns) {
    const match = normalized.match(pattern);
    if (match?.[1]) return shortenHistoryTopic(match[1]);
  }

  const stateNames = normalized.match(
    /\b(?:Kuala Lumpur|Negeri Sembilan|Johor|Kedah|Kelantan|Melaka|Malacca|Pahang|Penang|Perak|Perlis|Putrajaya|Sabah|Sarawak|Selangor|Terengganu|Labuan)\b/i,
  );
  if (stateNames) return stateNames[0];

  if (normalized.length <= 30) return localizeLabel(normalized);
  const words = normalized.split(/\s+/).slice(0, 5).join(" ");
  return shortenHistoryTopic(words || normalized);
}

function historyTopic(row, text, sender) {
  if (sender === "user") return userHistoryTopic(text);
  const action = row.chatData?.action || "response";
  return HISTORY_TOPICS[currentLanguage]?.[action]
    || HISTORY_TOPICS.en[action]
    || HISTORY_TOPICS[currentLanguage].response;
}

function refreshHistoryItem(row, text = row.historyText, sender = row.historySender) {
  if (!text || !sender) return;
  const button = historyList.querySelector(`[data-message-target="${row.id}"]`);
  if (!button) return;
  const topic = historyTopic(row, text, sender);
  const speaker = sender === "user" ? t("you") : "Maya";
  button.querySelector(".history-speaker").textContent = `${speaker} — ${topic}`;
  button.setAttribute(
    "aria-label",
    `Return to ${sender === "user" ? "your" : "Maya's"} ${topic} message: ${text}`,
  );
}

function registerHistoryItem(row, text, sender) {
  const messageId = `conversation-message-${messageCounter}`;
  messageCounter += 1;
  row.id = messageId;
  row.tabIndex = -1;
  row.historyText = text;
  row.historySender = sender;

  const listItem = document.createElement("li");
  const button = document.createElement("button");
  const speaker = document.createElement("span");
  const preview = document.createElement("span");
  button.type = "button";
  button.dataset.messageTarget = messageId;
  button.setAttribute("aria-label", `Return to ${sender === "user" ? "your" : "Maya's"} message: ${text}`);
  speaker.className = "history-speaker";
  speaker.textContent = `${sender === "user" ? t("you") : "Maya"} — ${historyTopic(row, text, sender)}`;
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
formStatus.textContent = t("preparingMaya");
fetch("/api/warmup")
  .then(response => {
    if (!response.ok) throw new Error("Warm-up failed");
    formStatus.textContent = t("mayaReady");
    window.setTimeout(() => {
      if (formStatus.textContent === t("mayaReady")) formStatus.textContent = "";
    }, 2500);
  })
  .catch(() => {
    if (formStatus.textContent === t("preparingMaya")) formStatus.textContent = "";
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
      image.addEventListener("error", () => figure.remove(), { once: true });
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
          creditLink.textContent = `${t("photoCredit")}: ${attribution}`;
          caption.appendChild(creditLink);
        } else {
          caption.textContent = `${t("photoCredit")}: ${attribution}`;
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
    description.textContent = localizedCardDescription(item);
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
        listItem.textContent = localizedFact(fact);
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
      reasonText.textContent = currentLanguage === "en"
        ? item.accessibility_reason
        : localizedAccessibilityReason();
      reasonSection.append(reasonHeading, reasonText);
      card.appendChild(reasonSection);
    }

    if (item.accessibility_notes) {
      const accessNote = document.createElement("p");
      accessNote.className = "accessibility-note";
      accessNote.textContent = currentLanguage === "en"
        ? item.accessibility_notes
        : localizedAccessibilityNote();
      card.appendChild(accessNote);
    }

    const originalAccessibilityDetails = [
      item.accessibility_reason,
      item.accessibility_notes,
    ].filter((value, index, values) => value && values.indexOf(value) === index).join("\n\n");
    appendOriginalEnglishDetails(card, originalAccessibilityDetails);

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
  formStatus.textContent = t("findingResponse");
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
    refreshHistoryItem(replyRow);
    latestSessionState = data.session_state || latestSessionState;
    showPreferences(data.context);
    showRecommendations(data.recommendations, replyRow);
    replyRow.scrollIntoView({ block: "nearest" });
    showQuickReplies(data.suggestions);
    saveCurrentConversation();
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

savedConversationsList.addEventListener("click", async event => {
  const openButton = event.target.closest("button[data-open-conversation]");
  if (openButton) {
    await openSavedConversation(openButton.dataset.openConversation);
    return;
  }

  const renameButton = event.target.closest("button[data-rename-conversation]");
  if (renameButton) {
    const conversations = readSavedConversations();
    const conversation = conversations.find(
      item => item.id === renameButton.dataset.renameConversation,
    );
    if (!conversation) return;
    const item = renameButton.closest(".saved-conversation-item");
    const actions = item.querySelector(".saved-conversation-actions");
    const input = document.createElement("input");
    input.className = "saved-conversation-name-input";
    input.value = conversation.title;
    input.maxLength = 45;
    input.setAttribute("aria-label", "Saved conversation name");
    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.dataset.saveConversationName = conversation.id;
    saveButton.textContent = t("saveConversationName");
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.dataset.cancelConversationAction = "true";
    cancelButton.textContent = t("cancelConversationAction");
    actions.replaceChildren(input, saveButton, cancelButton);
    input.focus();
    input.select();
    return;
  }

  const saveNameButton = event.target.closest("button[data-save-conversation-name]");
  if (saveNameButton) {
    const item = saveNameButton.closest(".saved-conversation-item");
    const input = item.querySelector(".saved-conversation-name-input");
    const title = input?.value.trim();
    if (!title) return;
    const conversations = readSavedConversations();
    const conversation = conversations.find(
      entry => entry.id === saveNameButton.dataset.saveConversationName,
    );
    if (!conversation) return;
    conversation.title = shortenHistoryTopic(title, 45);
    conversation.customTitle = true;
    writeSavedConversations(conversations);
    if (conversation.id === activeConversationId) {
      currentConversationTitle.textContent = conversation.title;
    }
    renderSavedConversations();
    return;
  }

  if (event.target.closest("button[data-cancel-conversation-action]")) {
    renderSavedConversations();
    return;
  }

  const deleteButton = event.target.closest("button[data-delete-conversation]");
  if (deleteButton) {
    const item = deleteButton.closest(".saved-conversation-item");
    const actions = item.querySelector(".saved-conversation-actions");
    const question = document.createElement("span");
    question.className = "saved-conversation-confirmation";
    question.textContent = t("deleteConversationConfirm");
    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.dataset.confirmDeleteConversation = deleteButton.dataset.deleteConversation;
    confirmButton.textContent = t("confirmDeleteConversation");
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.dataset.cancelConversationAction = "true";
    cancelButton.textContent = t("cancelConversationAction");
    actions.replaceChildren(question, confirmButton, cancelButton);
    confirmButton.focus();
    return;
  }

  const confirmDeleteButton = event.target.closest(
    "button[data-confirm-delete-conversation]",
  );
  if (!confirmDeleteButton) return;
  const conversationId = confirmDeleteButton.dataset.confirmDeleteConversation;
  const remaining = readSavedConversations().filter(item => item.id !== conversationId);
  writeSavedConversations(remaining);
  if (conversationId === activeConversationId) {
    skipCurrentSaveOnReset = true;
    resetButton.click();
  } else {
    renderSavedConversations();
  }
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
      formStatus.textContent = t("browserVoice");
    } else {
      formStatus.textContent = t("audioUnavailable");
    }
    button.textContent = t("readAloud");
  } finally {
    button.disabled = false;
  }
}

resetButton.addEventListener("click", async () => {
  resetButton.disabled = true;
  if (!skipCurrentSaveOnReset) saveCurrentConversation();
  skipCurrentSaveOnReset = false;
  clearGeneratedAudio();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const data = await sendJson("/api/reset");
    activeConversationId = createConversationId();
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, activeConversationId);
    latestSessionState = data.session_state;
    clearConversationDisplay();
    const replyRow = addMessage(localizeReply(data), "bot");
    replyRow.chatData = data;
    refreshHistoryItem(replyRow);
    showPreferences({});
    showQuickReplies(data.suggestions);
    currentConversationTitle.textContent = t("newTripTitle");
    renderSavedConversations();
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
    refreshHistoryItem(replyRow);
    latestSessionState = data.session_state || latestSessionState;
    showPreferences(data.context);
    showRecommendations(data.recommendations, replyRow);
    showQuickReplies(data.suggestions);
    saveCurrentConversation();
    formStatus.textContent = t("preferencesCleared");
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
  if (speechRecognition) {
    speechRecognition.lang = currentLanguage === "zh"
      ? "zh-CN"
      : currentLanguage === "ms" ? "ms-MY" : "en-MY";
  }

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
  const activeSavedConversation = readSavedConversations().find(
    conversation => conversation.id === activeConversationId,
  );
  currentConversationTitle.textContent = displayedConversationTitle(activeSavedConversation);
  renderSavedConversations();
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
renderSavedConversations();
window.addEventListener("beforeunload", saveCurrentConversation);

const savedActiveConversation = readSavedConversations().find(
  conversation => conversation.id === activeConversationId,
);
if (savedActiveConversation) {
  openSavedConversation(activeConversationId, false);
} else {
  sendJson("/api/reset")
    .then(data => { latestSessionState = data.session_state; })
    .catch(() => {});
}
