import { useRef, useEffect } from "react";
import type { Translation } from "../i18n";

interface ProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string) => void;
  t: Translation;
}

export function ProjectModal({ isOpen, onClose, onSubmit, t }: ProjectModalProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const name = inputRef.current?.value.trim();
    if (name) {
      onSubmit(name);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <form className="project-modal" onSubmit={handleSubmit} onMouseDown={(e) => e.stopPropagation()} ref={formRef}>
        <button type="button" className="modal-close" onClick={onClose}>×</button>
        <span className="modal-kicker">{t.newSession}</span>
        <h2>{t.createVoiceover}</h2>
        <p>{t.sessionDescription}</p>
        <input
          ref={inputRef}
          autoFocus
          placeholder={t.projectName}
        />
        <button className="modal-submit" type="submit">{t.createProject}</button>
      </form>
    </div>
  );
}