import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { LogicalSize } from "@tauri-apps/api/dpi";
import { useEffect, useRef, useCallback } from "react";

export type Project = { name: string; created_at: string; updated_at: string; voice?: string | null; language: string; profile: string; speed: number; output_format: string };
export type Voice = { name: string };
export type OutputFile = { name: string; path: string };
export type EnvironmentStatus = {
  runtime: boolean;
  runtime_version?: string;
  ffmpeg: boolean;
  ffprobe: boolean;
  model: boolean;
};

export function useProjects() {
  const loadProjects = useCallback(async () => {
    return await invoke<Project[]>("list_projects");
  }, []);

  const createProject = useCallback(async (name: string) => {
    return await invoke<Project>("create_project", { name });
  }, []);

  const renameProject = useCallback(async (oldName: string, newName: string) => {
    return await invoke<Project>("rename_project", { oldName, newName });
  }, []);

  const deleteProject = useCallback(async (name: string) => {
    return await invoke("delete_project", { name });
  }, []);

  const saveProject = useCallback(async (project: Project, script: string) => {
    return await invoke("save_project", { project, script });
  }, []);

  const readProjectScript = useCallback(async (name: string) => {
    return await invoke<string>("read_project_script", { name });
  }, []);

  const renderProject = useCallback(async (project: Project) => {
    return await invoke<string>("render_project", { project });
  }, []);

  return { loadProjects, createProject, renameProject, deleteProject, saveProject, readProjectScript, renderProject };
}

export function useVoices() {
  const loadVoices = useCallback(async () => {
    return await invoke<Voice[]>("list_voices");
  }, []);

  const addVoice = useCallback(async (name: string, source: string) => {
    return await invoke<Voice>("add_voice", { name, source });
  }, []);

  return { loadVoices, addVoice };
}

export function useOutputs() {
  const listOutputs = useCallback(async () => {
    return await invoke<OutputFile[]>("list_outputs");
  }, []);

  const revealOutput = useCallback(async (path: string) => {
    return await invoke("reveal_output", { path });
  }, []);

  return { listOutputs, revealOutput };
}

export function useUpdater() {
  const checkForUpdate = useCallback(async () => {
    try {
      const update = await check();
      return update;
    } catch {
      return null;
    }
  }, []);

  const downloadAndInstall = useCallback(async (update: any) => {
    await update.downloadAndInstall();
    await relaunch();
  }, []);

  return { checkForUpdate, downloadAndInstall };
}

export function useSetup() {
  const checkEnvironment = useCallback(async () => {
    return await invoke<EnvironmentStatus>("check_environment");
  }, []);

  const installRuntime = useCallback(async () => {
    return await invoke("install_runtime");
  }, []);

  const downloadModel = useCallback(async () => {
    return await invoke("download_model");
  }, []);

  return { checkEnvironment, installRuntime, downloadModel };
}

export function useSetupLog(onLog: (message: string) => void) {
  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;
    void listen<string>("setup-log", (event) => onLog(event.payload)).then((unlisten) => {
      if (cancelled) unlisten();
      else cleanup = unlisten;
    });
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [onLog]);
}

export function useWindowSize() {
  const windowRef = useRef<ReturnType<typeof getCurrentWindow> | null>(null);
  if (!windowRef.current) {
    windowRef.current = getCurrentWindow();
  }
  const window = windowRef.current;
  const checkSize = useCallback(async () => {
    const size = await window.outerSize();
    if (size.height < 560) {
      await window.setSize(new LogicalSize(1440, 920));
    }
  }, [window]);

  return { checkSize };
}

export type RenderProgressEvent = { phase: string; progress: number; indeterminate?: boolean };

export function useRenderProgress(onProgress: (event: RenderProgressEvent) => void) {
  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;

    void listen<RenderProgressEvent>("render-progress", (event) => {
      onProgress(event.payload);
    }).then((unlisten) => {
      if (cancelled) {
        unlisten();
      } else {
        cleanup = unlisten;
      }
    });

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [onProgress]);
}

export function useRenderLog(uiLanguage: string, onLog: (message: string) => void) {
  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;

    void listen<string>("render-log", (event) => {
      const translations: Record<string, Record<string, string>> = {
        tr: {
          "Preparing project and voice reference...": "Proje ve ses referansı hazırlanıyor...",
          "Python voice worker started.": "Python ses işçisi başlatıldı.",
          "Audio file written successfully.": "Ses dosyası başarıyla yazıldı.",
          "Voice worker exited with an error.": "Ses işçisi hata ile sonlandı.",
          "Preparing voice...": "Ses referansı hazırlanıyor...",
          "Voice ready.": "Ses referansı hazır.",
          "Loading voice model...": "Ses modeli yükleniyor...",
          "Voice model ready.": "Ses modeli hazır.",
          "Merging audio...": "Ses parçaları birleştiriliyor...",
          "Audio merged.": "Ses parçaları birleştirildi.",
          "Encoding output...": "Çıktı kodlanıyor...",
          "Output encoded.": "Çıktı kodlandı.",
        },
        en: {}
      };
      const message = translations[uiLanguage]?.[event.payload] ?? event.payload;
      onLog(message);
    }).then((unlisten) => {
      if (cancelled) {
        unlisten();
      } else {
        cleanup = unlisten;
      }
    });

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [uiLanguage, onLog]);
}

export function useAudioPlayer() {
  const playAudio = useCallback((path: string) => {
    const player = document.querySelector<HTMLAudioElement>("#studio-audio");
    if (!player) return;
    player.src = convertFileSrc(path);
    player.play();
    document.documentElement.classList.add("player-visible");
  }, []);

  const stopAudio = useCallback(() => {
    const player = document.querySelector<HTMLAudioElement>("#studio-audio");
    player?.pause();
    document.documentElement.classList.remove("player-visible");
  }, []);

  return { playAudio, stopAudio };
}
