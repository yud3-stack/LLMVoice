use serde::{Deserialize, Serialize};
use std::fs;
use tauri::{AppHandle, Manager};

#[derive(Debug, Serialize, Deserialize)]
struct Project {
    name: String,
    created_at: String,
    updated_at: String,
    #[serde(default)]
    voice: Option<String>,
    #[serde(default = "default_language")]
    language: String,
    #[serde(default = "default_profile")]
    profile: String,
    #[serde(default = "default_speed")]
    speed: f32,
    #[serde(default = "default_output_format")]
    output_format: String,
}

fn default_language() -> String { "tr".into() }
fn default_profile() -> String { "balanced".into() }
fn default_speed() -> f32 { 1.0 }
fn default_output_format() -> String { "mp3".into() }

#[derive(Debug, Serialize)]
struct Voice {
    name: String,
}

fn projects_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let directory = data_root(app)?.join("projects");
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    Ok(directory)
}

fn data_root(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        return Ok(std::path::PathBuf::from(local_app_data).join("LLMVoice"));
    }
    app.path().app_data_dir().map_err(|error| error.to_string())
}

fn project_slug(name: &str) -> String {
    name.chars()
        .map(|character| if character.is_ascii_alphanumeric() || character == '-' || character == '_' { character } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_ascii_lowercase()
}

#[tauri::command]
fn list_projects(app: AppHandle) -> Result<Vec<Project>, String> {
    let directory = projects_dir(&app)?;
    let mut projects = Vec::new();
    for entry in fs::read_dir(directory).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let metadata_path = entry.path().join("project.json");
        if metadata_path.is_file() {
            let content = fs::read_to_string(metadata_path).map_err(|error| error.to_string())?;
            if let Ok(project) = serde_json::from_str::<Project>(&content) {
                projects.push(project);
            }
        }
    }
    projects.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
    Ok(projects)
}

#[tauri::command]
fn create_project(app: AppHandle, name: String) -> Result<Project, String> {
    let clean_name = name.trim();
    if clean_name.is_empty() || clean_name.len() > 80 {
        return Err("Project name must be between 1 and 80 characters.".into());
    }
    let slug = project_slug(clean_name);
    if slug.is_empty() {
        return Err("Project name must contain letters or numbers.".into());
    }
    let directory = projects_dir(&app)?.join(&slug);
    if directory.exists() {
        return Err("A project with this name already exists.".into());
    }
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let now = chrono_now();
    let project = Project { name: clean_name.to_owned(), created_at: now.clone(), updated_at: now, voice: None, language: default_language(), profile: default_profile(), speed: default_speed(), output_format: default_output_format() };
    let metadata = serde_json::to_string_pretty(&project).map_err(|error| error.to_string())?;
    fs::write(directory.join("project.json"), metadata).map_err(|error| error.to_string())?;
    fs::write(directory.join("script.txt"), "").map_err(|error| error.to_string())?;
    Ok(project)
}

#[tauri::command]
fn save_project_settings(app: AppHandle, project: Project) -> Result<(), String> {
    let path = projects_dir(&app)?.join(project_slug(&project.name)).join("project.json");
    if !path.is_file() {
        return Err("Project was not found.".into());
    }
    let metadata = serde_json::to_string_pretty(&project).map_err(|error| error.to_string())?;
    fs::write(path, metadata).map_err(|error| error.to_string())
}

#[tauri::command]
fn read_project_script(app: AppHandle, name: String) -> Result<String, String> {
    let path = projects_dir(&app)?.join(project_slug(&name)).join("script.txt");
    fs::read_to_string(path).map_err(|error| error.to_string())
}

#[tauri::command]
fn save_project_script(app: AppHandle, name: String, script: String) -> Result<(), String> {
    let path = projects_dir(&app)?.join(project_slug(&name));
    if !path.is_dir() {
        return Err("Project was not found.".into());
    }
    fs::write(path.join("script.txt"), script).map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
fn list_voices(app: AppHandle) -> Result<Vec<Voice>, String> {
    let directory = data_root(&app)?.join("voices");
    if !directory.is_dir() {
        return Ok(Vec::new());
    }
    let supported = ["wav", "mp3", "flac", "m4a", "aac", "ogg", "opus"];
    let mut voices = Vec::new();
    for entry in fs::read_dir(directory).map_err(|error| error.to_string())? {
        let path = entry.map_err(|error| error.to_string())?.path();
        let extension = path.extension().and_then(|value| value.to_str()).unwrap_or("").to_ascii_lowercase();
        if path.is_file() && supported.contains(&extension.as_str()) {
            if let Some(name) = path.file_stem().and_then(|value| value.to_str()) {
                voices.push(Voice { name: name.to_owned() });
            }
        }
    }
    voices.sort_by_key(|voice| voice.name.to_ascii_lowercase());
    Ok(voices)
}

fn chrono_now() -> String {
    // A sortable UTC timestamp without adding a runtime dependency.
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs().to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![list_projects, create_project, read_project_script, save_project_script, save_project_settings, list_voices])
        .run(tauri::generate_context!())
        .expect("error while running LLMVoice Studio");
}
