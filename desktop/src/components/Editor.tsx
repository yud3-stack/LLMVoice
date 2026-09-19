import { useState } from "react";
import { ArrowLeft, Save, FileText } from "lucide-react";
import { VoicePicker } from "./VoicePicker";
import type { Project, Voice } from "../hooks/useTauriCommands";
import type { Translation } from "../i18n";

interface EditorProps {
  project: Project;
  script: string;
  voices: Voice[];
  selectedVoice: string;
  onVoiceChange: (voice: string) => void;
  profile: string;
  onProfileChange: (profile: string) => void;
  language: string;
  onLanguageChange: (language: string) => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  outputFormat: string;
  onOutputFormatChange: (format: string) => void;
  saved: boolean;
  rendering: boolean;
  onScriptChange: (script: string) => void;
  onBack: () => void;
  onSave: () => void;
  onRender: () => void;
  t: Translation;
}

const profiles = ["balanced", "natural", "expressive"] as const;
const languages = ["tr", "en"] as const;
const formats = ["mp3", "wav"] as const;

export function Editor({
  project,
  script,
  voices,
  selectedVoice,
  onVoiceChange,
  profile,
  onProfileChange,
  language,
  onLanguageChange,
  speed,
  onSpeedChange,
  outputFormat,
  onOutputFormatChange,
  saved,
  rendering,
  onScriptChange,
  onBack,
  onSave,
  onRender,
  t,
}: EditorProps) {
  const [voiceOpen, setVoiceOpen] = useState(false);

  return (
    <main className="editor-workspace">
      <div className="editor-top">
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={16} />{t.allProjects}
        </button>
        <div className="editor-title">
          <FileText size={15} />
          <strong>{project.name}</strong>
          <span>{saved ? t.saved : t.unsaved}</span>
        </div>
        <button className="save-button" onClick={onSave}>
          <Save size={15} />{t.save}
        </button>
      </div>
      <div className="editor-layout">
        <section className="script-surface">
          <div className="surface-heading">
            <div>
              <span className="modal-kicker">{t.script}</span>
              <h2>{t.voiceoverScript}</h2>
            </div>
            <span className="script-meta">{script.length} {t.characters}</span>
          </div>
          <textarea
            autoFocus
            value={script}
            onChange={(e) => onScriptChange(e.target.value)}
            placeholder={t.writeScript}
            spellCheck={false}
          />
          <div className="surface-foot">
            <span><FileText size={13} />{t.plainText}</span>
            <span>{t.savedWithProject}</span>
          </div>
        </section>
        <aside className="inspector">
          <div className="inspector-heading">
            <span className="modal-kicker">{t.setup}</span>
            <h2>{t.voiceover}</h2>
          </div>
          <label>
            {t.voice}
            <VoicePicker voices={voices} selectedVoice={selectedVoice} onChange={onVoiceChange} t={t} />
          </label>
          <label>
            {t.profile}
            <div className="editor-controls">
              <select
                value={profile}
                onChange={(e) => onProfileChange(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p} value={p}>{t[p as keyof Translation]}</option>
                ))}
              </select>
            </div>
          </label>
          <label>
            {t.language}
            <div className="editor-controls">
              <select
                value={language}
                onChange={(e) => onLanguageChange(e.target.value)}
              >
                {languages.map((l) => (
                  <option key={l} value={l}>{t[l === "tr" ? "turkish" : "english"]}</option>
                ))}
              </select>
            </div>
          </label>
          <label>
            {t.speed}
            <div className="editor-controls">
              <input
                type="range"
                min="0.5"
                max="2"
                step="0.1"
                value={speed}
                onChange={(e) => onSpeedChange(Number(e.target.value))}
              />
              <span className="speed-value">{speed.toFixed(1)}x</span>
            </div>
          </label>
          <label>
            {t.output}
            <div className="editor-controls">
              <select
                value={outputFormat}
                onChange={(e) => onOutputFormatChange(e.target.value)}
              >
                {formats.map((f) => (
                  <option key={f} value={f}>{f.toUpperCase()}</option>
                ))}
              </select>
            </div>
          </label>
          <button className="render-button" onClick={onRender} disabled={!script.trim() || rendering}>
            {rendering ? t.generating : t.render}
          </button>
        </aside>
      </div>
    </main>
  );
}
