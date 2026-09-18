import { useState, useRef, useEffect } from "react";
import type { Voice } from "../hooks/useTauriCommands";
import type { Translation } from "../i18n";

interface VoicePickerProps {
  voices: Voice[];
  selectedVoice: string;
  onChange: (voice: string) => void;
  t: Translation;
  disabled?: boolean;
}

export function VoicePicker({ voices, selectedVoice, onChange, t, disabled }: VoicePickerProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (open && triggerRef.current && menuRef.current) {
        if (!triggerRef.current.contains(e.target as Node) && !menuRef.current.contains(e.target as Node)) {
          setOpen(false);
        }
      }
    };
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [open]);

  const currentVoice = voices.find(v => v.name === selectedVoice);

  return (
    <div className="voice-picker">
      <button
        type="button"
        className={`select-field voice-trigger ${open ? "open" : ""}`}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        ref={triggerRef}
      >
        {currentVoice?.name ?? t.chooseVoice}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <div className="voice-menu" ref={menuRef} hidden={!open}>
        {voices.length === 0 ? (
          <div className="voice-empty">{t.noVoices}</div>
        ) : (
          voices.map((voice) => (
            <button
              key={voice.name}
              type="button"
              className={`voice-option ${voice.name === selectedVoice ? "selected" : ""}`}
              onClick={() => {
                onChange(voice.name);
                setOpen(false);
              }}
              disabled={disabled}
            >
              <span className="option-icon">♪</span>
              {voice.name}
              {voice.name === selectedVoice && <i />}
            </button>
          ))
        )}
      </div>
    </div>
  );
}