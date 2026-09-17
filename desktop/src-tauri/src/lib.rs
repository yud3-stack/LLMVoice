use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::thread;
use tauri::{AppHandle, Emitter, Manager};

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

fn validate_project(project: &Project) -> Result<(), String> {
    if project.name.trim().is_empty() || project.name.len() > 80 || project_slug(&project.name).is_empty() {
        return Err("Project name must be between 1 and 80 characters.".into());
    }
    if let Some(voice) = &project.voice {
        if voice.is_empty() || voice.len() > 64 || !voice.chars().all(|character| character.is_ascii_alphanumeric() || character == '-' || character == '_') {
            return Err("Voice name is invalid.".into());
        }
    }
    if !project.speed.is_finite() || !(0.5..=2.0).contains(&project.speed) {
        return Err("Speed must be between 0.5 and 2.0.".into());
    }
    if !matches!(project.profile.as_str(), "natural" | "balanced" | "stable" | "expressive") {
        return Err("Quality profile is invalid.".into());
    }
    if !matches!(
        project.language.as_str(),
        "ar" | "cs" | "de" | "en" | "es" | "fr" | "hi" | "hu" | "it" | "ja"
            | "ko" | "nl" | "pl" | "pt" | "ru" | "tr" | "zh-cn"
    ) {
        return Err("Unsupported language for the desktop studio.".into());
    }
    if !matches!(project.output_format.as_str(), "mp3" | "wav") {
        return Err("Output format must be mp3 or wav.".into());
    }
    Ok(())
}

#[derive(Debug, Serialize)]
struct Voice {
    name: String,
}

#[derive(Debug, Serialize)]
struct OutputFile { name: String, path: String }

#[derive(Debug, Deserialize)]
struct InstallState {
    #[serde(rename = "runtimePath")]
    runtime_path: String,
}

fn discover_python(root: &Path) -> Result<PathBuf, String> {
    if let Ok(override_path) = std::env::var("LLMVOICE_PYTHON") {
        let path = PathBuf::from(override_path);
        if path.is_file() {
            return Ok(path);
        }
        return Err(format!(
            "LLMVOICE_PYTHON does not point to a valid Python executable: {}",
            path.display()
        ));
    }

    let state_path = root.join("runtime").join("install-state.json");
    if state_path.is_file() {
        let state: InstallState = serde_json::from_str(
            &fs::read_to_string(&state_path).map_err(|error| {
                format!("Could not read LLMVoice runtime state: {error}")
            })?,
        )
        .map_err(|error| format!("LLMVoice runtime state is invalid: {error}"))?;
        let runtime_root = root.join("runtime").join("versions").canonicalize().map_err(|error| {
            format!("Could not locate installed LLMVoice runtimes: {error}")
        })?;
        let runtime_path = PathBuf::from(state.runtime_path).canonicalize().map_err(|error| {
            format!("The installed LLMVoice runtime path is invalid: {error}")
        })?;
        if !runtime_path.starts_with(&runtime_root) {
            return Err("The installed LLMVoice runtime points outside the managed runtime directory.".into());
        }
        let python = runtime_path.join("Scripts").join("python.exe");
        if python.is_file() {
            return Ok(python);
        }
        return Err(format!(
            "The installed LLMVoice Python runtime was not found: {}",
            python.display()
        ));
    }

    if cfg!(debug_assertions) {
        // Keep source-tree development usable without weakening installed-runtime selection.
        return Ok(PathBuf::from("python"));
    }

    Err(
        "LLMVoice runtime is not installed. Run the LLMVoice installer before rendering."
            .into(),
    )
}


fn projects_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let directory = data_root(app)?.join("projects");
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    Ok(directory)
}

fn absolute_path(path: PathBuf) -> Result<PathBuf, String> {
    if path.is_absolute() {
        return Ok(path);
    }
    std::env::current_dir()
        .map(|directory| directory.join(path))
        .map_err(|error| error.to_string())
}

fn replace_file(source: &Path, destination: &Path) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        let source: Vec<u16> = source.as_os_str().encode_wide().chain([0]).collect();
        let destination: Vec<u16> = destination.as_os_str().encode_wide().chain([0]).collect();
        let result = unsafe {
            windows_sys::Win32::Storage::FileSystem::MoveFileExW(
                source.as_ptr(),
                destination.as_ptr(),
                windows_sys::Win32::Storage::FileSystem::MOVEFILE_REPLACE_EXISTING
                    | windows_sys::Win32::Storage::FileSystem::MOVEFILE_WRITE_THROUGH,
            )
        };
        if result == 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        fs::rename(source, destination).map_err(|error| error.to_string())
    }
}

fn atomic_write(path: &Path, contents: &str) -> Result<(), String> {
    let parent = path.parent().ok_or_else(|| "Invalid file path.".to_owned())?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent).map_err(|error| error.to_string())?;
    temporary
        .write_all(contents.as_bytes())
        .and_then(|_| temporary.as_file().sync_all())
        .map_err(|error| error.to_string())?;
    let temporary_path = temporary.into_temp_path();
    replace_file(&temporary_path, path)?;
    temporary_path.close().map_err(|error| error.to_string())
}

fn data_root(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    if let Ok(override_path) = std::env::var("LLMVOICE_DATA_DIR") {
        if !override_path.trim().is_empty() {
            return absolute_path(PathBuf::from(override_path));
        }
    }
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        return absolute_path(std::path::PathBuf::from(local_app_data).join("LLMVoice"));
    }
    app.path()
        .app_data_dir()
        .map_err(|error| error.to_string())
        .and_then(absolute_path)
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
    atomic_write(&directory.join("project.json"), &metadata)?;
    atomic_write(&directory.join("script.txt"), "")?;
    Ok(project)
}

#[tauri::command]
fn rename_project(app: AppHandle, old_name: String, new_name: String) -> Result<Project, String> {
    let clean_name = new_name.trim();
    let source = projects_dir(&app)?.join(project_slug(&old_name));
    let target = projects_dir(&app)?.join(project_slug(clean_name));
    if clean_name.is_empty() || clean_name.len() > 80 || project_slug(clean_name).is_empty() { return Err("Project name must be between 1 and 80 characters.".into()); }
    if !source.is_dir() { return Err("Project was not found.".into()); }
    if source != target && target.exists() { return Err("A project with this name already exists.".into()); }
    let metadata_path = source.join("project.json");
    let mut project: Project = serde_json::from_str(&fs::read_to_string(&metadata_path).map_err(|error| error.to_string())?).map_err(|error| error.to_string())?;
    project.name = clean_name.to_owned();
    project.updated_at = chrono_now();
    if source != target { fs::rename(&source, &target).map_err(|error| error.to_string())?; }
    atomic_write(
        &target.join("project.json"),
        &serde_json::to_string_pretty(&project).map_err(|error| error.to_string())?,
    )?;
    Ok(project)
}

#[tauri::command]
fn delete_project(app: AppHandle, name: String) -> Result<(), String> {
    let directory = projects_dir(&app)?.join(project_slug(&name));
    if !directory.is_dir() { return Err("Project was not found.".into()); }
    fs::remove_dir_all(directory).map_err(|error| error.to_string())
}

#[tauri::command]
fn save_project_settings(app: AppHandle, project: Project) -> Result<(), String> {
    validate_project(&project)?;
    let path = projects_dir(&app)?.join(project_slug(&project.name)).join("project.json");
    if !path.is_file() {
        return Err("Project was not found.".into());
    }
    let metadata = serde_json::to_string_pretty(&project).map_err(|error| error.to_string())?;
    atomic_write(&path, &metadata)
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
    atomic_write(&path.join("script.txt"), &script)?;
    Ok(())
}

#[tauri::command]
fn save_project(app: AppHandle, project: Project, script: String) -> Result<(), String> {
    validate_project(&project)?;
    let directory = projects_dir(&app)?.join(project_slug(&project.name));
    if !directory.is_dir() {
        return Err("Project was not found.".into());
    }
    let metadata_path = directory.join("project.json");
    let script_path = directory.join("script.txt");
    let metadata = serde_json::to_string_pretty(&project).map_err(|error| error.to_string())?;
    let previous_metadata = fs::read_to_string(&metadata_path).map_err(|error| error.to_string())?;
    atomic_write(&metadata_path, &metadata)?;
    if let Err(error) = atomic_write(&script_path, &script) {
        let _ = atomic_write(&metadata_path, &previous_metadata);
        return Err(error);
    }
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
    for entry in fs::read_dir(&directory).map_err(|error| error.to_string())? {
        let path = entry.map_err(|error| error.to_string())?.path();
        let extension = path.extension().and_then(|value| value.to_str()).unwrap_or("").to_ascii_lowercase();
        if path.is_file()
            && supported.contains(&extension.as_str())
            && !is_additional_voice_reference(&directory, &path, &supported)
        {
            if let Some(name) = path.file_stem().and_then(|value| value.to_str()) {
                voices.push(Voice { name: name.to_owned() });
            }
        }
    }
    voices.sort_by_key(|voice| voice.name.to_ascii_lowercase());
    Ok(voices)
}

fn is_additional_voice_reference(directory: &Path, path: &Path, supported: &[&str]) -> bool {
    let Some(stem) = path.file_stem().and_then(|value| value.to_str()) else {
        return false;
    };
    let Some((base, suffix)) = stem.rsplit_once('-') else {
        return false;
    };
    if base.is_empty() || suffix.is_empty() || !suffix.chars().all(|character| character.is_ascii_digit()) {
        return false;
    }
    supported.iter().any(|extension| directory.join(format!("{base}.{extension}")).is_file())
}

#[tauri::command]
fn add_voice(app: AppHandle, name: String, source: String) -> Result<Voice, String> {
    let clean_name = name.trim();
    if clean_name.is_empty() || !clean_name.chars().all(|character| character.is_ascii_alphanumeric() || character == '-' || character == '_') { return Err("Voice name may contain only letters, numbers, '-' and '_'.".into()); }
    let root = data_root(&app)?;
    let python = discover_python(&root)?;
    let result = std::process::Command::new(python)
        .args(["-m", "llmvoice", "voice", "add", clean_name])
        .arg(&source)
        .output()
        .map_err(|error| format!("Could not start Python voice validator: {error}"))?;
    if !result.status.success() {
        let detail = String::from_utf8_lossy(&result.stderr);
        let detail = detail.trim();
        return Err(if detail.is_empty() {
            "Voice validation failed. Check the audio file and try again.".into()
        } else {
            detail.to_owned()
        });
    }
    Ok(Voice { name: clean_name.to_owned() })
}

#[tauri::command]
fn list_outputs(app: AppHandle) -> Result<Vec<OutputFile>, String> {
    let directory = projects_dir(&app)?;
    let mut outputs = Vec::new();
    for project in fs::read_dir(directory).map_err(|error| error.to_string())? {
        let project_path = project.map_err(|error| error.to_string())?.path();
        if !project_path.is_dir() { continue; }
        for entry in fs::read_dir(&project_path).map_err(|error| error.to_string())? {
            let path = entry.map_err(|error| error.to_string())?.path();
            let extension = path.extension().and_then(|value| value.to_str()).unwrap_or("").to_ascii_lowercase();
            if path.is_file() && (extension == "mp3" || extension == "wav") {
                outputs.push(OutputFile { name: format!("{} · {}", project_path.file_name().and_then(|value| value.to_str()).unwrap_or("project"), extension.to_uppercase()), path: path.to_string_lossy().into_owned() });
            }
        }
    }
    outputs.sort_by(|left, right| right.path.cmp(&left.path));
    Ok(outputs)
}

#[tauri::command]
async fn render_project(app: AppHandle, project: Project) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || render_project_sync(app, project))
        .await
        .map_err(|error| format!("Render worker could not be joined: {error}"))?
}

fn render_project_sync(app: AppHandle, project: Project) -> Result<String, String> {
    validate_project(&project)?;
    let root = data_root(&app)?;
    let project_dir = projects_dir(&app)?.join(project_slug(&project.name));
    let script = project_dir.join("script.txt");
    if !script.is_file() {
        return Err("Project script was not found.".into());
    }
    let voice_name = project.voice.ok_or_else(|| "Select a voice before rendering.".to_owned())?;
    let output = project_dir.join(format!("output.{}", project.output_format));
    let speed = project.speed.to_string();
    let _ = app.emit("render-log", "Preparing project and voice reference...");
    let _ = app.emit("render-progress", serde_json::json!({ "phase": "starting", "progress": 5 }));
    let python = discover_python(&root)?;
    let mut child = std::process::Command::new(python)
        .args(["-m", "llmvoice", "start"])
        .arg(&script).args(["--voice", voice_name.as_str()])
        .args(["--language", project.language.as_str(), "--quality", project.profile.as_str(), "--speed", speed.as_str(), "--output"])
        .arg(&output).arg("--force")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn().map_err(|error| format!("Could not start Python worker: {error}"))?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let stdout_app = app.clone();
    let stdout_thread = thread::spawn(move || {
        if let Some(stream) = stdout {
            for line in BufReader::new(stream).lines().map_while(Result::ok) {
                let _ = stdout_app.emit("render-log", line.trim_end().to_owned());
            }
        }
    });
    let stderr_app = app.clone();
    let stderr_thread = thread::spawn(move || {
        if let Some(stream) = stderr {
            for line in BufReader::new(stream).lines().map_while(Result::ok) {
                let _ = stderr_app.emit("render-log", line.trim_end().to_owned());
            }
        }
    });
    let _ = app.emit("render-log", "Python voice worker started.");
    let _ = app.emit("render-progress", serde_json::json!({ "phase": "rendering", "progress": 45 }));
    let status = child.wait().map_err(|error| format!("Python worker failed: {error}"))?;
    let _ = stdout_thread.join();
    let _ = stderr_thread.join();
    if !status.success() {
        let _ = app.emit("render-log", "Voice worker exited with an error.");
        let _ = app.emit("render-progress", serde_json::json!({ "phase": "failed", "progress": 0 }));
        return Err("Voiceover rendering failed. Check the terminal log for details.".into());
    }
    let _ = app.emit("render-log", "Audio file written successfully.");
    let _ = app.emit("render-progress", serde_json::json!({ "phase": "complete", "progress": 100 }));
    Ok(output.to_string_lossy().into_owned())
}

#[tauri::command]
fn approved_output_path(app: &AppHandle, path: &str) -> Result<PathBuf, String> {
    let projects = projects_dir(app)?
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let output = PathBuf::from(path)
        .canonicalize()
        .map_err(|_| "Output file was not found.".to_owned())?;
    if !output.starts_with(&projects)
        || !matches!(output.extension().and_then(|value| value.to_str()), Some("mp3" | "wav"))
        || !output.is_file()
    {
        return Err("Only generated MP3 or WAV files can be opened.".into());
    }
    Ok(output)
}

#[tauri::command]
fn reveal_output(app: AppHandle, path: String) -> Result<(), String> {
    let output = approved_output_path(&app, &path)?;
    let selection = format!("/select,{}", output.display());
    std::process::Command::new("explorer")
        .arg(selection)
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Could not open output location: {error}"))
}

#[tauri::command]
fn open_output(app: AppHandle, path: String) -> Result<(), String> {
    let output = approved_output_path(&app, &path)?;
    std::process::Command::new("explorer")
        .arg(output)
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Could not open audio output: {error}"))
}

fn chrono_now() -> String {
    // A sortable UTC timestamp without adding a runtime dependency.
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs().to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![list_projects, create_project, rename_project, delete_project, read_project_script, save_project_script, save_project_settings, save_project, list_voices, add_voice, list_outputs, render_project, reveal_output, open_output])
        .run(tauri::generate_context!())
        .expect("error while running LLMVoice Studio");
}

#[cfg(test)]
mod tests {
    use super::discover_python;
    use std::fs;

    #[test]
    fn discovers_python_from_installer_state() {
        let root = std::env::temp_dir().join(format!(
            "llmvoice-runtime-test-{}",
            std::process::id()
        ));
        let runtime = root.join("runtime").join("versions").join("test").join("venv");
        let python = runtime.join("Scripts").join("python.exe");
        fs::create_dir_all(python.parent().expect("python parent")).expect("runtime directory");
        fs::write(&python, b"test").expect("python placeholder");
        let state = root.join("runtime").join("install-state.json");
        let runtime_path = runtime.to_string_lossy().replace('\\', "\\\\");
        fs::write(
            &state,
            format!(r#"{{"runtimePath":"{runtime_path}"}}"#),
        )
        .expect("install state");

        assert_eq!(
            discover_python(&root).expect("python path"),
            python.canonicalize().expect("canonical python path")
        );
        fs::remove_dir_all(root).expect("temporary runtime cleanup");
    }
}
