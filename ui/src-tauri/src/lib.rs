use std::process::Command;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn list_games() -> String {
    let output = Command::new("python")
        .args(["engine/sidecar_api.py", "--list-games"])
        .current_dir("..")
        .output()
        .expect("Failed to execute Python sidecar");

    String::from_utf8_lossy(&output.stdout).to_string()
}

#[tauri::command]
fn start_game(game_id: String, monitor: u32) -> String {
    // Spawn detached — the Python process runs independently
    std::process::Command::new("python")
        .args([
            "run.py",
            "--game",
            &game_id,
            "--monitor",
            &monitor.to_string(),
        ])
        .current_dir("..")
        .spawn()
        .expect("Failed to start game pipeline");

    format!(
        "{{\"status\": \"started\", \"game\": \"{}\"}}",
        game_id
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            list_games,
            start_game,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
