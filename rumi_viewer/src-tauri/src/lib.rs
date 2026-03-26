//! Rumi Viewer — Tauri application library.
//!
//! V1: Skeleton with module declarations.
//! V2 will add setup hook, commands, tray menu, and on_navigation.

#![allow(unused)]

mod config;
mod health_check;
mod kernel_manager;
mod python_env;
mod updater;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
