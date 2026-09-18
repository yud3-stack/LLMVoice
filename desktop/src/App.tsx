import { useEffect, useCallback, useRef, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { AudioLines } from "lucide-react";

import { AppProvider, useApp } from "./context/AppContext";
import { useProjects, useVoices, useOutputs, useUpdater, useWindowSize, useRenderProgress, useRenderLog } from "./hooks/useTauriCommands";
import { TopBar } from "./components/TopBar";
import { Launcher } from "./components/Launcher";
import { Editor } from "./components/Editor";
import { SettingsPanel } from "./components/SettingsPanel";
import { ProjectModal } from "./components/ProjectModal";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { SetupWizard } from "./components/SetupWizard";
import { getUiLanguage, translations, type UiLanguage } from "./i18n";
import type { Project, RenderProgressEvent } from "./hooks/useTauriCommands";
import "./styles.css";

function AppContent() {
  const { state, dispatch } = useApp();
  const { loadProjects, createProject, renameProject, deleteProject, saveProject, readProjectScript, renderProject } = useProjects();
  const { loadVoices, addVoice } = useVoices();
  const { listOutputs, revealOutput } = useOutputs();
  const { checkForUpdate, downloadAndInstall } = useUpdater();
  const { checkSize } = useWindowSize();
  const [renderProgress, setRenderProgress] = useState<RenderProgressEvent>({ phase: "starting", progress: 0 });
  const [renderLogs, setRenderLogs] = useState<string[]>([]);
  const [renderUiVisible, setRenderUiVisible] = useState(false);
  const [consoleCollapsed, setConsoleCollapsed] = useState(false);
  const [showSetup, setShowSetup] = useState(true);
  const renderHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const consoleLines = useRef<HTMLDivElement | null>(null);

  const t = translations[state.uiLanguage];

  useEffect(() => {
    document.documentElement.lang = state.uiLanguage;
  }, [state.uiLanguage]);

  useEffect(() => {
    if (showSetup) return;
    void loadProjects()
      .then((projects) => dispatch({ type: "SET_PROJECTS", payload: projects }))
      .catch((error) => alert(String(error)));
    void loadVoices()
      .then((voices) => dispatch({ type: "SET_VOICES", payload: voices }))
      .catch((error) => alert(String(error)));
    void checkSize().catch((error) => console.error("Window resize failed", error));
  }, [loadProjects, loadVoices, checkSize, dispatch, showSetup]);

  useEffect(() => {
    const refreshVoices = () => {
      void loadVoices()
        .then((voices) => dispatch({ type: "SET_VOICES", payload: voices }))
        .catch((error) => console.error("Voice refresh failed", error));
    };
    window.addEventListener("focus", refreshVoices);
    return () => window.removeEventListener("focus", refreshVoices);
  }, [loadVoices, dispatch]);

  useEffect(() => {
    let cancelled = false;
    checkForUpdate().then((update) => {
      if (!update || cancelled) return;
      const isTurkish = getUiLanguage() === "tr";
      const accepted = confirm(
        isTurkish
          ? `Yeni sürüm ${update.version} bulundu. Şimdi indirip yüklemek ister misiniz?`
          : `Version ${update.version} is available. Download and install it now?`
      );
      if (!accepted) return;
      downloadAndInstall(update);
    });
    return () => { cancelled = true; };
  }, [checkForUpdate, downloadAndInstall]);

  const handleRenderProgress = useCallback((event: RenderProgressEvent) => {
    const progress = Math.max(0, Math.min(100, Math.round(event.progress)));
    setRenderProgress({ phase: event.phase, progress, indeterminate: event.indeterminate });
    setRenderUiVisible(true);
    if (event.phase === "complete" || event.phase === "failed") {
      if (renderHideTimer.current) clearTimeout(renderHideTimer.current);
      renderHideTimer.current = setTimeout(() => setRenderUiVisible(false), 2200);
    }
  }, []);

  const handleRenderLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setRenderLogs((current) => [...current.slice(-99), `[${timestamp}] ${message}`]);
  }, []);

  useRenderProgress(handleRenderProgress);
  useRenderLog(state.uiLanguage, handleRenderLog);

  useEffect(() => {
    const element = consoleLines.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [renderLogs]);

  useEffect(() => () => {
    if (renderHideTimer.current) clearTimeout(renderHideTimer.current);
  }, []);

  useEffect(() => {
    void listOutputs()
      .then((outputs) => dispatch({ type: "SET_OUTPUTS", payload: outputs }))
      .catch((error) => console.error("Output refresh failed", error));
  }, [state.lastOutput, listOutputs, dispatch]);

  const handleNewProject = useCallback(() => dispatch({ type: "SET_NEW_PROJECT_OPEN", payload: true }), [dispatch]);
  const handleOpenProject = useCallback((project: Project) => dispatch({ type: "SET_ACTIVE_PROJECT", payload: project }), [dispatch]);
  const handleBack = useCallback(() => dispatch({ type: "SET_ACTIVE_PROJECT", payload: null }), [dispatch]);
  const handleSettings = useCallback(() => dispatch({ type: "SET_SETTINGS_OPEN", payload: true }), [dispatch]);
  const handleCloseSettings = useCallback(() => dispatch({ type: "SET_SETTINGS_OPEN", payload: false }), [dispatch]);
  const handleCloseNewProject = useCallback(() => dispatch({ type: "SET_NEW_PROJECT_OPEN", payload: false }), [dispatch]);
  const handleQueryChange = useCallback((query: string) => dispatch({ type: "SET_QUERY", payload: query }), [dispatch]);
  const handleLanguageChange = useCallback((lang: UiLanguage) => {
    localStorage.setItem("llmvoice.ui-language", lang);
    dispatch({ type: "SET_UI_LANGUAGE", payload: lang });
  }, [dispatch]);

  const handleCreateProject = useCallback(async (name: string) => {
    try {
      const project = await createProject(name);
      dispatch({ type: "ADD_PROJECT", payload: project });
      dispatch({ type: "SET_NEW_PROJECT_OPEN", payload: false });
      dispatch({ type: "SET_ACTIVE_PROJECT", payload: project });
      dispatch({ type: "SET_SCRIPT", payload: "" });
      dispatch({ type: "SET_SAVED", payload: true });
    } catch (error) {
      alert(String(error));
    }
  }, [createProject, dispatch]);

  const handleAddVoice = useCallback(async () => {
    const source = await open({
      multiple: false,
      filters: [{ name: "Audio", extensions: ["wav", "mp3", "flac", "m4a", "aac", "ogg", "opus"] }],
    });
    if (typeof source !== "string") return;
    const base = source.split(/[\\/]/).pop()?.split(".")[0] ?? "voice";
    const name = prompt(t.voiceName, base);
    if (!name) return;
    try {
      const voice = await addVoice(name, source);
      dispatch({ type: "ADD_VOICE", payload: voice });
    } catch (error) {
      alert(String(error));
    }
  }, [addVoice, t, dispatch]);

  const handleSaveProject = useCallback(async (): Promise<boolean> => {
    if (!state.activeProject) return false;
    const updated = {
      ...state.activeProject,
      voice: state.selectedVoice || null,
      profile: state.profile,
      language: state.language,
      speed: state.speed,
      output_format: state.outputFormat,
    };
    try {
      await saveProject(updated, state.script);
      dispatch({ type: "UPDATE_PROJECT", payload: updated });
      dispatch({ type: "SET_SAVED", payload: true });
      return true;
    } catch (error) {
      alert(String(error));
      return false;
    }
  }, [state, saveProject, dispatch]);

  const handleRenderProject = useCallback(async () => {
    if (!state.activeProject || state.rendering) return;
    try {
      const didSave = await handleSaveProject();
      if (!didSave) return;
      if (renderHideTimer.current) clearTimeout(renderHideTimer.current);
      setRenderLogs([]);
      setRenderProgress({ phase: "starting", progress: 0 });
      setConsoleCollapsed(false);
      setRenderUiVisible(true);
      dispatch({ type: "SET_RENDERING", payload: true });
      const projectToRender = {
        ...state.activeProject,
        voice: state.selectedVoice || null,
        profile: state.profile,
        language: state.language,
        speed: state.speed,
        output_format: state.outputFormat,
      };
      const output = await renderProject(projectToRender);
      dispatch({ type: "SET_LAST_OUTPUT", payload: output });
      alert(t.renderedSuccess);
    } catch (error) {
      const message = String(error);
      setRenderProgress({ phase: "failed", progress: 0 });
      setRenderLogs((current) => [...current.slice(-99), `[${new Date().toLocaleTimeString()}] ${message}`]);
      if (renderHideTimer.current) clearTimeout(renderHideTimer.current);
      renderHideTimer.current = setTimeout(() => setRenderUiVisible(false), 3500);
      alert(message);
    } finally {
      dispatch({ type: "SET_RENDERING", payload: false });
    }
  }, [state, handleSaveProject, renderProject, t, dispatch]);

  const renderProgressLabel = renderProgress.phase === "rendering"
    ? t.generating
    : renderProgress.phase === "complete"
      ? t.renderComplete
      : renderProgress.phase === "failed"
        ? t.renderFailed
        : t.preparing;

  const handleScriptChange = useCallback((script: string) => {
    dispatch({ type: "SET_SCRIPT", payload: script });
  }, [dispatch]);

  const handleVoiceChange = useCallback((voice: string) => {
    dispatch({ type: "SET_SELECTED_VOICE", payload: voice });
  }, [dispatch]);

  const handleProfileChange = useCallback((profile: string) => {
    dispatch({ type: "SET_PROFILE", payload: profile });
  }, [dispatch]);

  const handleLanguageChange2 = useCallback((language: string) => {
    dispatch({ type: "SET_LANGUAGE", payload: language });
  }, [dispatch]);

  const handleSpeedChange = useCallback((speed: number) => {
    dispatch({ type: "SET_SPEED", payload: speed });
  }, [dispatch]);

  const handleOutputFormatChange = useCallback((format: string) => {
    dispatch({ type: "SET_OUTPUT_FORMAT", payload: format });
  }, [dispatch]);

  const handleRename = useCallback(async (oldName: string, newName: string) => {
    try {
      const updated = await renameProject(oldName, newName);
      dispatch({ type: "UPDATE_PROJECT", payload: updated });
      if (state.activeProject?.name === oldName) {
        dispatch({ type: "SET_ACTIVE_PROJECT", payload: updated });
      }
    } catch (error) {
      alert(String(error));
    }
  }, [renameProject, state.activeProject, dispatch]);

  const handleDelete = useCallback(async (name: string) => {
    if (!confirm(`${t.deleteProject} "${name}"?`)) return;
    try {
      await deleteProject(name);
      dispatch({ type: "REMOVE_PROJECT", payload: name });
    } catch (error) {
      alert(String(error));
    }
  }, [deleteProject, t, dispatch]);

  const handleOutputPlay = useCallback((path: string) => {
    dispatch({ type: "SET_CURRENT_AUDIO", payload: convertFileSrc(path) });
    dispatch({ type: "SET_SHOW_PLAYER", payload: true });
  }, [dispatch]);

  const handleOutputReveal = useCallback((path: string) => {
    void revealOutput(path);
  }, [revealOutput]);

  const handleOutputs = useCallback(() => {
    dispatch({ type: "SET_SHOW_OUTPUTS", payload: !state.showOutputs });
  }, [dispatch, state.showOutputs]);

  useEffect(() => {
    if (!state.activeProject) return;
    dispatch({ type: "SET_SELECTED_VOICE", payload: state.activeProject.voice ?? state.voices[0]?.name ?? "" });
    dispatch({ type: "SET_PROFILE", payload: state.activeProject.profile });
    dispatch({ type: "SET_LANGUAGE", payload: state.activeProject.language });
    dispatch({ type: "SET_SPEED", payload: state.activeProject.speed });
    dispatch({ type: "SET_OUTPUT_FORMAT", payload: state.activeProject.output_format });
    void readProjectScript(state.activeProject.name)
      .then((script) => {
        dispatch({ type: "SET_SCRIPT", payload: script });
        dispatch({ type: "SET_SAVED", payload: true });
      })
      .catch((error) => alert(String(error)));
  }, [state.activeProject, state.voices, readProjectScript, dispatch]);

  const handleOpenFeedback = useCallback(() => dispatch({ type: "SET_SHOW_FEEDBACK", payload: true }), [dispatch]);

  const handleFeedbackSubmit = useCallback((message: string) => {
    if (!message.trim()) return;
    const url = `https://github.com/yud3-stack/LLMVoice/issues/new?title=${encodeURIComponent("LLMVoice feedback")}&body=${encodeURIComponent(message.trim())}`;
    globalThis.open(url, "_blank");
  }, []);

  return (
    <div className={`launcher${renderUiVisible ? " render-ui-visible" : ""}`}>
      {showSetup && <SetupWizard t={t} onReady={() => setShowSetup(false)} />}
      <TopBar onMenu={handleNewProject} onFeedback={handleOpenFeedback} onOutputs={handleOutputs} t={t} />
      {state.activeProject ? (
        <Editor
          project={state.activeProject}
          script={state.script}
          voices={state.voices}
          selectedVoice={state.selectedVoice}
          onVoiceChange={handleVoiceChange}
          profile={state.profile}
          onProfileChange={handleProfileChange}
          language={state.language}
          onLanguageChange={handleLanguageChange2}
          speed={state.speed}
          onSpeedChange={handleSpeedChange}
          outputFormat={state.outputFormat}
          onOutputFormatChange={handleOutputFormatChange}
          saved={state.saved}
          rendering={state.rendering}
          onScriptChange={handleScriptChange}
          onBack={handleBack}
          onSave={handleSaveProject}
          onRender={handleRenderProject}
          t={t}
        />
      ) : (
        <Launcher
          query={state.query}
          onQueryChange={handleQueryChange}
          projects={state.projects}
          onNew={handleNewProject}
          onOpen={handleOpenProject}
          onRename={handleRename}
          onDelete={handleDelete}
          onSettings={handleSettings}
          t={t}
        />
      )}
      {state.settingsOpen && (
        <SettingsPanel
          voices={state.voices}
          language={state.uiLanguage}
          onLanguage={handleLanguageChange}
          onAdd={handleAddVoice}
          onClose={handleCloseSettings}
          t={t}
        />
      )}
      {state.newProjectOpen && (
        <ProjectModal
          isOpen={state.newProjectOpen}
          onClose={handleCloseNewProject}
          onSubmit={handleCreateProject}
          t={t}
        />
      )}
      <div id="render-console" className={consoleCollapsed ? "collapsed" : ""} aria-live="polite">
        <div className="render-console-head">
          <AudioLines size={13} />
          <strong>{t.renderActivity}</strong>
          <span>{renderProgressLabel}</span>
          <button id="render-console-close" aria-label={t.hideRenderActivity} onClick={() => setConsoleCollapsed(true)}>×</button>
        </div>
        <div className="render-console-lines" ref={consoleLines}>
          {renderLogs.length === 0
            ? <div className="render-console-empty">{t.waitingForRender}</div>
            : renderLogs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>)}
        </div>
      </div>
      <button id="render-console-toggle" className={consoleCollapsed ? "visible" : ""} aria-label={t.showRenderActivity} onClick={() => setConsoleCollapsed(false)}>
        <AudioLines size={14} />
      </button>
      <div id="render-progress" role="status" aria-live="polite">
        <div className="render-progress-top">
          <span className="render-progress-label">{renderProgressLabel}</span>
          <span className="render-progress-value">
            {renderProgress.indeterminate ? t.inProgress : `${renderProgress.progress}%`}
          </span>
        </div>
        <div className={`render-progress-track${state.rendering ? " active" : ""}${renderProgress.indeterminate ? " indeterminate" : ""}`} aria-hidden="true">
          <i style={{ width: renderProgress.indeterminate ? "35%" : `${renderProgress.progress}%` }} />
        </div>
      </div>
      <div id="outputs-popover" className={state.showOutputs ? "visible" : ""}>
        <strong>{t.recentVoiceovers}</strong>
        {state.outputs.slice(0, 8).map((item) => (
          <div key={item.path} className="output-entry">
            <span className="output-name" title={item.path}>{item.name}</span>
            <span className="output-actions">
              <button className="output-action folder-action" title={t.showFolder} onClick={() => handleOutputReveal(item.path)}>📁</button>
              <button className="output-action play-action" title={t.playAudio} onClick={() => handleOutputPlay(item.path)}>▶</button>
            </span>
          </div>
        ))}
        {state.outputs.length === 0 && <span className="outputs-empty">{t.noRendered}</span>}
      </div>
      <div id="feedback-panel" className={state.showFeedback ? "visible" : ""}>
        <form id="feedback-form" onSubmit={(e) => { e.preventDefault(); const msg = (e.target as HTMLFormElement).elements.namedItem("message") as HTMLTextAreaElement; handleFeedbackSubmit(msg.value); msg.value = ""; dispatch({ type: "SET_SHOW_FEEDBACK", payload: false }); }}>
          <button type="button" className="feedback-close" onClick={() => dispatch({ type: "SET_SHOW_FEEDBACK", payload: false })}>×</button>
          <span className="modal-kicker">{t.feedbackKicker}</span>
          <h2>{t.feedbackTitle}</h2>
          <p>{t.feedbackDescription}</p>
          <textarea name="message" id="feedback-message" placeholder={t.feedbackPlaceholder} />
          <button type="submit">{t.feedbackSubmit}</button>
        </form>
      </div>
      <div id="studio-player" className={state.showPlayer ? "player-visible" : ""}>
        <span className="player-kicker">{t.nowPlaying}</span>
        <audio id="studio-audio" controls src={state.currentAudio} onEnded={() => dispatch({ type: "SET_SHOW_PLAYER", payload: false })} />
        <button id="player-close" onClick={() => {
          document.querySelector<HTMLAudioElement>("#studio-audio")?.pause();
          dispatch({ type: "SET_SHOW_PLAYER", payload: false });
        }}>×</button>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <ErrorBoundary>
        <AppContent />
      </ErrorBoundary>
    </AppProvider>
  );
}
