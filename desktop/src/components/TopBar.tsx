import { Menu, Bell, MessageSquarePlus, Download, AudioLines, ChevronDown } from "lucide-react";
import type { Translation } from "../i18n";

interface TopBarProps {
  onMenu: () => void;
  onFeedback: () => void;
  onOutputs: () => void;
  t: Translation;
}

export function TopBar({ onMenu, onFeedback, onOutputs, t }: TopBarProps) {
  return (
    <header className="launcher-bar">
      <button className="chrome-button" onClick={onMenu}>
        <Menu size={17} />
      </button>
      <div className="instance-select">
        <span className="mini-logo"><AudioLines size={12} /></span>
        <strong>LLMVoice</strong>
        <span className="bar-context">{t.personalWorkspace}</span>
        <ChevronDown size={13} />
      </div>
      <div className="chrome-actions">
        <button className="chrome-button"><Bell size={16} /></button>
        <button className="chrome-button" onClick={onFeedback}><MessageSquarePlus size={16} /></button>
        <button className="chrome-button" onClick={onOutputs} title={t.recentVoiceovers}><Download size={16} /></button>
      </div>
    </header>
  );
}
