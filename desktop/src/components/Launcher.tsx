import { useRef, useEffect } from "react";
import { Search, Mic2, Settings2, Laptop, AudioLines, Plus } from "lucide-react";
import { ProjectCard } from "./ProjectCard";
import type { Project } from "../hooks/useTauriCommands";
import type { Translation } from "../i18n";

interface LauncherProps {
  query: string;
  onQueryChange: (query: string) => void;
  projects: Project[];
  onNew: () => void;
  onOpen: (project: Project) => void;
  onRename: (oldName: string, newName: string) => void;
  onDelete: (name: string) => void;
  onSettings: () => void;
  t: Translation;
}

export function Launcher({
  query,
  onQueryChange,
  projects,
  onNew,
  onOpen,
  onRename,
  onDelete,
  onSettings,
  t,
}: LauncherProps) {
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const visible = projects.filter((item) =>
    item.name.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <main className="launcher-content">
      <button className="login-button">{t.localWorkspace}</button>
      <div className="hero-brand">
        <div className="hero-wave"><AudioLines size={29} /></div>
        <h1>LLMVoice</h1>
        <span>{t.localVoiceWorkspace}</span>
      </div>
      <div className="search-box">
        <Search size={18} />
        <input
          ref={searchRef}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t.findProject}
        />
        <kbd>Ctrl K</kbd>
      </div>
      <div className="project-grid">
        <button className="project-card fresh" onClick={onNew}>
          <div className="card-icon"><Plus size={27} strokeWidth={1.5} /></div>
          <div className="card-copy">
            <strong>{t.newVoiceover}</strong>
            <span>{t.freshNarration}</span>
          </div>
        </button>
        {visible.map((project) => (
          <ProjectCard
            key={project.name}
            project={project}
            onOpen={onOpen}
            onRename={onRename}
            onDelete={onDelete}
            t={t}
          />
        ))}
        {visible.length === 0 && projects.length > 0 && (
          <div className="no-projects"><Mic2 size={18} />{t.noProjects}</div>
        )}
      </div>
      <div className="launcher-footer">
        <span><span className="online-dot" />{t.engineReady}</span>
        <span>{t.turkishEnabled}</span>
        <button onClick={onSettings}><Settings2 size={14} />{t.settings}</button>
        <Laptop size={14} />
      </div>
    </main>
  );
}