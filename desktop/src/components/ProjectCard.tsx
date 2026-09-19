import { MoreVertical, FolderOpen } from "lucide-react";
import { useRef, useEffect } from "react";
import type { Project } from "../hooks/useTauriCommands";
import type { Translation } from "../i18n";

interface ProjectCardProps {
  project: Project;
  onOpen: (project: Project) => void;
  onRename: (oldName: string, newName: string) => void;
  onDelete: (name: string) => void;
  t: Translation;
}

export function ProjectCard({ project, onOpen, onRename, onDelete, t }: ProjectCardProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const isOpen = useRef(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (isOpen.current && menuRef.current && popupRef.current) {
        if (!menuRef.current.contains(e.target as Node) && !popupRef.current.contains(e.target as Node)) {
          if (popupRef.current) popupRef.current.hidden = true;
          isOpen.current = false;
        }
      }
    };
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  const handleMenuClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (popupRef.current) {
      popupRef.current.hidden = !popupRef.current.hidden;
      isOpen.current = !isOpen.current;
    }
  };

  const handleRename = () => {
    const nextName = prompt(t.renameProject + ":", project.name);
    if (nextName?.trim() && nextName.trim() !== project.name) {
      onRename(project.name, nextName.trim());
    }
    if (popupRef.current) popupRef.current.hidden = true;
    isOpen.current = false;
  };

  const handleDelete = () => {
    if (confirm(`${t.deleteProject} "${project.name}"?`)) {
      onDelete(project.name);
    }
    if (popupRef.current) popupRef.current.hidden = true;
    isOpen.current = false;
  };

  return (
    <button className="project-card" onClick={() => onOpen(project)}>
      <div className="card-icon">
        <FolderOpen size={22} strokeWidth={1.5} />
      </div>
      <div className="card-menu" ref={menuRef} onClick={handleMenuClick}>
        <MoreVertical size={17} />
      </div>
      <div className="project-actions-menu" ref={popupRef} hidden>
        <button type="button" onClick={handleRename}>
          <span className="action-icon">✎</span>{t.renameProject}
        </button>
        <button type="button" onClick={handleDelete}>
          <span className="action-icon">⌫</span>{t.deleteProject}
        </button>
      </div>
      <div className="card-copy">
        <strong>{project.name}</strong>
        <span>{t.localProject}</span>
      </div>
    </button>
  );
}