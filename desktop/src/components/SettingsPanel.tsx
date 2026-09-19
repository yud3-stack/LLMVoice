import { useRef, useEffect } from "react";
import type { Voice } from "../hooks/useTauriCommands";
import type { Translation, UiLanguage } from "../i18n";

interface SettingsPanelProps {
  voices: Voice[];
  language: UiLanguage;
  onLanguage: (value: UiLanguage) => void;
  onAdd: () => void;
  onClose: () => void;
  t: Translation;
}

export function SettingsPanel({ voices, language, onLanguage, onAdd, onClose, t }: SettingsPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Small delay to avoid immediate close on open
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handleClickOutside);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [onClose]);

  return (
    <div id="settings-panel" className="visible" ref={panelRef} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="settings-sheet" ref={sheetRef}>
        <button className="settings-close" onClick={onClose}>×</button>
        <span className="modal-kicker">{t.preferences}</span>
        <h2>{t.settings}</h2>
        <div className="settings-tabs">
          <button className="active">{t.voiceLibrary}</button>
          <button>{t.general}</button>
        </div>
        <div className="settings-section">
          <div>
            <strong>{t.localVoices}</strong>
            <span>{t.referenceDescription}</span>
          </div>
          <button className="add-voice-button" onClick={onAdd}>{t.addVoice}</button>
        </div>
        <div className="settings-voices">
          {voices.length ? (
            voices.map((voice) => (
              <div className="settings-voice" key={voice.name}>
                <span className="settings-voice-icon">♪</span>
                <span>
                  <strong>{voice.name}</strong>
                  <small>{t.localReference}</small>
                </span>
                <i>{t.ready}</i>
              </div>
            ))
          ) : (
            <span className="outputs-empty">{t.noVoices}</span>
          )}
        </div>
        <div className="settings-language">
          <label htmlFor="language-select">{t.interfaceLanguage}</label>
          <select
            id="language-select"
            value={language}
            onChange={(e) => onLanguage(e.target.value as UiLanguage)}
          >
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </select>
        </div>
        <div className="settings-note">{t.localOnly}</div>
      </div>
    </div>
  );
}