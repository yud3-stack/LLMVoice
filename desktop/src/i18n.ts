export type UiLanguage = "tr" | "en";

const messages = {
  en: {
    localWorkspace: "Local workspace", localVoiceWorkspace: "LOCAL VOICE WORKSPACE", personalWorkspace: "Personal workspace",
    findProject: "Find a project or voice", newVoiceover: "New voiceover", freshNarration: "Start a fresh narration session",
    localProject: "Local project · Updated recently", noProjects: "No saved projects yet", engineReady: "Local engine ready",
    turkishEnabled: "XTTS-v2 · Turkish enabled", settings: "Settings", allProjects: "All projects", saved: "Saved",
    unsaved: "Unsaved changes", save: "Save", script: "SCRIPT", voiceoverScript: "Voiceover script", characters: "characters",
    writeScript: "Write or paste your script here...", plainText: "Plain text · UTF-8", savedWithProject: "Saved with project",
    setup: "SETUP", voiceover: "Voiceover", voice: "VOICE", chooseVoice: "Choose a voice", noVoices: "No voices installed",
    profile: "PROFILE", balanced: "Balanced", natural: "Natural", expressive: "Expressive", language: "LANGUAGE",
    speed: "SPEED", output: "OUTPUT", render: "Render voiceover", newSession: "NEW SESSION", createVoiceover: "Create a voiceover project",
    sessionDescription: "Give your session a name to create a local project.", projectName: "Project name", createProject: "Create project",
    preferences: "PREFERENCES", voiceLibrary: "Voice library", general: "General", localVoices: "Local voices",
    referenceDescription: "Reference recordings available to your projects.", addVoice: "+ Add voice", interfaceLanguage: "Interface language",
    localOnly: "Audio stays on this computer. Nothing is uploaded.", loadingVoices: "Loading voices...", localReference: "Local voice reference",
    ready: "READY", recentVoiceovers: "Recent voiceovers", noRendered: "No rendered files yet.", showFolder: "Show in folder", playAudio: "Play audio",
    nowPlaying: "Now playing", preparing: "Preparing render", generating: "Generating voiceover", renderComplete: "Render complete",
    renderedSuccess: "Voiceover rendered successfully.", voiceName: "Voice name", renameProject: "Rename project", deleteProject: "Delete project", feedbackKicker: "FEEDBACK", feedbackTitle: "Share your feedback", feedbackDescription: "Tell us what would make LLMVoice better.", feedbackPlaceholder: "Write your feedback...", feedbackSubmit: "Open feedback form",
  },
  tr: {
    localWorkspace: "Yerel çalışma alanı", localVoiceWorkspace: "YEREL SES ÇALIŞMA ALANI", personalWorkspace: "Kişisel çalışma alanı",
    findProject: "Proje veya ses ara", newVoiceover: "Yeni seslendirme", freshNarration: "Yeni bir anlatım oturumu başlatın",
    localProject: "Yerel proje · Yakın zamanda güncellendi", noProjects: "Kayıtlı proje yok", engineReady: "Yerel motor hazır",
    turkishEnabled: "XTTS-v2 · Türkçe etkin", settings: "Ayarlar", allProjects: "Tüm projeler", saved: "Kaydedildi",
    unsaved: "Kaydedilmemiş değişiklikler", save: "Kaydet", script: "METİN", voiceoverScript: "Seslendirme metni", characters: "karakter",
    writeScript: "Metninizi buraya yazın veya yapıştırın...", plainText: "Düz metin · UTF-8", savedWithProject: "Projeyle birlikte kaydedildi",
    setup: "KURULUM", voiceover: "Seslendirme", voice: "SES", chooseVoice: "Ses seçin", noVoices: "Yüklü ses yok",
    profile: "PROFİL", balanced: "Dengeli", natural: "Doğal", expressive: "Duygulu", language: "DİL",
    speed: "HIZ", output: "ÇIKTI", render: "Seslendirmeyi oluştur", newSession: "YENİ OTURUM", createVoiceover: "Seslendirme projesi oluştur",
    sessionDescription: "Yerel bir proje oluşturmak için oturumunuza bir ad verin.", projectName: "Proje adı", createProject: "Proje oluştur",
    preferences: "TERCİHLER", voiceLibrary: "Ses kitaplığı", general: "Genel", localVoices: "Yerel sesler",
    referenceDescription: "Projelerinizde kullanılabilecek referans kayıtları.", addVoice: "+ Ses ekle", interfaceLanguage: "Arayüz dili",
    localOnly: "Ses bilgisayarınızda kalır. Hiçbir şey yüklenmez.", loadingVoices: "Sesler yükleniyor...", localReference: "Yerel ses referansı",
    ready: "HAZIR", recentVoiceovers: "Son seslendirmeler", noRendered: "Henüz oluşturulmuş dosya yok.", showFolder: "Klasörde göster", playAudio: "Sesi çal",
    nowPlaying: "Şimdi çalıyor", preparing: "Oluşturma hazırlanıyor", generating: "Seslendirme oluşturuluyor", renderComplete: "Oluşturma tamamlandı",
    renderedSuccess: "Seslendirme başarıyla oluşturuldu.", voiceName: "Ses adı", renameProject: "Projeyi yeniden adlandır", deleteProject: "Projeyi sil", feedbackKicker: "GERİ BİLDİRİM", feedbackTitle: "Geri bildiriminizi paylaşın", feedbackDescription: "LLMVoice'u daha iyi hale getirmek için önerinizi yazın.", feedbackPlaceholder: "Geri bildiriminizi yazın...", feedbackSubmit: "Geri bildirim formunu aç",
  },
} as const;

export type Translation = Record<keyof typeof messages.en, string>;
export const translations: Record<UiLanguage, Translation> = messages;
export const getUiLanguage = (): UiLanguage => localStorage.getItem("llmvoice.ui-language") === "en" ? "en" : "tr";
