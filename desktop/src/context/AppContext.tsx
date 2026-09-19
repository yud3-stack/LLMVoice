import { createContext, useContext, useReducer, ReactNode, Dispatch } from "react";
import type { Project, Voice, OutputFile } from "../hooks/useTauriCommands";
import { getUiLanguage, type UiLanguage } from "../i18n";

export type AppState = {
  projects: Project[];
  voices: Voice[];
  selectedVoice: string;
  profile: string;
  language: string;
  speed: number;
  outputFormat: string;
  activeProject: Project | null;
  newProjectOpen: boolean;
  settingsOpen: boolean;
  newProjectName: string;
  script: string;
  saved: boolean;
  rendering: boolean;
  lastOutput: string;
  uiLanguage: UiLanguage;
  query: string;
  outputs: OutputFile[];
  showOutputs: boolean;
  showFeedback: boolean;
  showPlayer: boolean;
  currentAudio: string;
};

export type AppAction =
  | { type: "SET_PROJECTS"; payload: Project[] }
  | { type: "ADD_PROJECT"; payload: Project }
  | { type: "UPDATE_PROJECT"; payload: Project }
  | { type: "REMOVE_PROJECT"; payload: string }
  | { type: "SET_VOICES"; payload: Voice[] }
  | { type: "ADD_VOICE"; payload: Voice }
  | { type: "SET_SELECTED_VOICE"; payload: string }
  | { type: "SET_PROFILE"; payload: string }
  | { type: "SET_LANGUAGE"; payload: string }
  | { type: "SET_SPEED"; payload: number }
  | { type: "SET_OUTPUT_FORMAT"; payload: string }
  | { type: "SET_ACTIVE_PROJECT"; payload: Project | null }
  | { type: "SET_NEW_PROJECT_OPEN"; payload: boolean }
  | { type: "SET_SETTINGS_OPEN"; payload: boolean }
  | { type: "SET_NEW_PROJECT_NAME"; payload: string }
  | { type: "SET_SCRIPT"; payload: string }
  | { type: "SET_SAVED"; payload: boolean }
  | { type: "SET_RENDERING"; payload: boolean }
  | { type: "SET_LAST_OUTPUT"; payload: string }
  | { type: "SET_UI_LANGUAGE"; payload: UiLanguage }
  | { type: "SET_QUERY"; payload: string }
  | { type: "SET_OUTPUTS"; payload: OutputFile[] }
  | { type: "SET_SHOW_OUTPUTS"; payload: boolean }
  | { type: "SET_SHOW_FEEDBACK"; payload: boolean }
  | { type: "SET_SHOW_PLAYER"; payload: boolean }
  | { type: "SET_CURRENT_AUDIO"; payload: string }
  | { type: "RESET_EDITOR" };

export const initialState: AppState = {
  projects: [],
  voices: [],
  selectedVoice: "",
  profile: "balanced",
  language: "tr",
  speed: 1,
  outputFormat: "mp3",
  activeProject: null,
  newProjectOpen: false,
  settingsOpen: false,
  newProjectName: "",
  script: "",
  saved: true,
  rendering: false,
  lastOutput: "",
  uiLanguage: getUiLanguage(),
  query: "",
  outputs: [],
  showOutputs: false,
  showFeedback: false,
  showPlayer: false,
  currentAudio: "",
};

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_PROJECTS":
      return { ...state, projects: action.payload };
    case "ADD_PROJECT":
      return { ...state, projects: [action.payload, ...state.projects] };
    case "UPDATE_PROJECT":
      return {
        ...state,
        projects: state.projects.map((project) =>
          project.name === action.payload.name ? action.payload : project,
        ),
        activeProject: state.activeProject?.name === action.payload.name
          ? action.payload
          : state.activeProject,
      };
    case "REMOVE_PROJECT":
      return {
        ...state,
        projects: state.projects.filter(p => p.name !== action.payload),
        activeProject: state.activeProject?.name === action.payload ? null : state.activeProject,
      };
    case "SET_VOICES":
      return { ...state, voices: action.payload, selectedVoice: action.payload[0]?.name ?? state.selectedVoice };
    case "ADD_VOICE":
      return { ...state, voices: [...state.voices, action.payload], selectedVoice: action.payload.name };
    case "SET_SELECTED_VOICE":
      return { ...state, selectedVoice: action.payload, saved: false };
    case "SET_PROFILE":
      return { ...state, profile: action.payload, saved: false };
    case "SET_LANGUAGE":
      return { ...state, language: action.payload, saved: false };
    case "SET_SPEED":
      return { ...state, speed: action.payload, saved: false };
    case "SET_OUTPUT_FORMAT":
      return { ...state, outputFormat: action.payload, saved: false };
    case "SET_ACTIVE_PROJECT":
      return { ...state, activeProject: action.payload };
    case "SET_NEW_PROJECT_OPEN":
      return { ...state, newProjectOpen: action.payload };
    case "SET_SETTINGS_OPEN":
      return { ...state, settingsOpen: action.payload };
    case "SET_NEW_PROJECT_NAME":
      return { ...state, newProjectName: action.payload };
    case "SET_SCRIPT":
      return { ...state, script: action.payload, saved: false };
    case "SET_SAVED":
      return { ...state, saved: action.payload };
    case "SET_RENDERING":
      return { ...state, rendering: action.payload };
    case "SET_LAST_OUTPUT":
      return { ...state, lastOutput: action.payload };
    case "SET_UI_LANGUAGE":
      return { ...state, uiLanguage: action.payload };
    case "SET_QUERY":
      return { ...state, query: action.payload };
    case "SET_OUTPUTS":
      return { ...state, outputs: action.payload };
    case "SET_SHOW_OUTPUTS":
      return { ...state, showOutputs: action.payload };
    case "SET_SHOW_FEEDBACK":
      return { ...state, showFeedback: action.payload };
    case "SET_SHOW_PLAYER":
      return { ...state, showPlayer: action.payload };
    case "SET_CURRENT_AUDIO":
      return { ...state, currentAudio: action.payload };
    case "RESET_EDITOR":
      return {
        ...state,
        script: "",
        saved: true,
        selectedVoice: state.voices[0]?.name ?? "",
        profile: "balanced",
        language: "tr",
        speed: 1,
        outputFormat: "mp3",
      };
    default:
      return state;
  }
}

export type AppDispatch = Dispatch<AppAction>;

interface AppContextType {
  state: AppState;
  dispatch: AppDispatch;
}

export const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used within AppProvider");
  return context;
}
