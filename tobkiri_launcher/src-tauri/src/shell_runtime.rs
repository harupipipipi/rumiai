//! Presentation-only runtime for a verified Profile-selected Shell artifact.
//!
//! This process deliberately does not start the Launcher Host Broker, Kernel,
//! Application guardian, tray, or any Host command surface. It only consumes a
//! one-shot authenticated runtime-profile handoff and presents that loopback
//! origin in its WebView.

use std::ffi::OsString;
use std::path::Path;
use std::sync::{Arc, Mutex};

use anyhow::{anyhow, Context, Result};
use log::{error, warn};
use tauri::{AppHandle, Manager};

use crate::navigation_is_allowed;
use crate::shell_handoff::{
    consume_shell_handoff, handoff_path_from_os_args, handoff_path_from_strings,
};

#[derive(Debug, Clone, PartialEq, Eq)]
struct ShellRuntimeBinding {
    runtime_port: u16,
    identity: crate::host_contract::ExecutionProfileIdentity,
    catalog_revision: String,
    artifact: crate::shell_handoff::ShellArtifactIdentity,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct ShellRuntimeState {
    binding: Option<ShellRuntimeBinding>,
    allowed_runtime_ports: Vec<u16>,
}

impl ShellRuntimeState {
    fn accept_handoff(
        &mut self,
        handoff: &crate::shell_handoff::ValidatedShellHandoff,
    ) -> Result<()> {
        let proposed = ShellRuntimeBinding {
            runtime_port: handoff.runtime_port,
            identity: handoff.identity.clone(),
            catalog_revision: handoff.catalog_revision.clone(),
            artifact: handoff.artifact.clone(),
        };
        if let Some(current) = self.binding.as_ref() {
            if current != &proposed {
                return Err(anyhow!(
                    "Shell runtime identity binding changed during handoff"
                ));
            }
            return Ok(());
        }

        self.allowed_runtime_ports = vec![handoff.runtime_port];
        self.binding = Some(proposed);
        Ok(())
    }
}

fn apply_handoff(
    app: &AppHandle,
    path: &Path,
    runtime_state: &Arc<Mutex<ShellRuntimeState>>,
) -> Result<()> {
    let handoff = consume_shell_handoff(path)?;
    {
        let mut state = runtime_state
            .lock()
            .map_err(|error| anyhow!("Shell runtime state lock is poisoned: {error}"))?;
        state.accept_handoff(&handoff)?;
    }

    let window = app
        .get_webview_window("main")
        .context("Tobkiri Shell main window is unavailable")?;
    window
        .navigate(handoff.runtime_url)
        .context("Tobkiri Shell failed to navigate to the authenticated runtime")?;
    let _ = window.unminimize();
    window
        .show()
        .context("Tobkiri Shell failed to show its main window")?;
    window
        .set_focus()
        .context("Tobkiri Shell failed to focus its main window")?;
    Ok(())
}

fn reject_initial_handoff(app: &AppHandle, error: &anyhow::Error) {
    // Do not propagate a setup-hook error. Tauri 2.10.x executes setup during
    // applicationDidFinishLaunching on macOS; unwinding through that Objective-C
    // callback aborts the process instead of producing a controlled failure.
    // The error is structural only; the authenticated URL is never logged.
    error!("Tobkiri Shell handoff rejected: {error:#}");
    app.exit(1);
}

pub(crate) fn run(context: tauri::Context<tauri::Wry>) {
    let runtime_state = Arc::new(Mutex::new(ShellRuntimeState::default()));
    let state_for_navigation = Arc::clone(&runtime_state);
    let state_for_forwarded_handoff = Arc::clone(&runtime_state);
    let initial_args = std::env::args_os().collect::<Vec<OsString>>();

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(
            move |app, args, _cwd| {
                let result = handoff_path_from_strings(&args)
                    .and_then(|path| apply_handoff(app, &path, &state_for_forwarded_handoff));
                if let Err(error) = result {
                    warn!("Forwarded Tobkiri Shell handoff rejected: {error:#}");
                }
            },
        ))
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("shell-nav-guard")
                .on_navigation(move |_webview, url| {
                    let allowed_ports = state_for_navigation
                        .lock()
                        .map(|state| state.allowed_runtime_ports.clone())
                        .unwrap_or_default();
                    navigation_is_allowed(
                        url.scheme(),
                        url.host_str().unwrap_or(""),
                        url.port_or_known_default(),
                        &allowed_ports,
                    )
                })
                .build(),
        )
        .setup(move |app| {
            match handoff_path_from_os_args(initial_args.clone())
                .and_then(|path| apply_handoff(app.handle(), &path, &runtime_state))
            {
                Ok(()) => {}
                Err(error) => reject_initial_handoff(app.handle(), &error),
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                // The Shell owns no background work. Exit instead of leaving a
                // hidden process that could retain a stale authenticated URL.
                window.app_handle().exit(0);
            }
        });

    let app = match builder.build(context) {
        Ok(app) => app,
        Err(error) => {
            error!("Tobkiri Shell construction failed: {error:#}");
            std::process::exit(1);
        }
    };

    app.run(|app_handle, event| {
        #[cfg(target_os = "macos")]
        if let tauri::RunEvent::Reopen {
            has_visible_windows: false,
            ..
        } = event
        {
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }
        #[cfg(not(target_os = "macos"))]
        let _ = (app_handle, event);
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shell_handoff::{ShellArtifactIdentity, ValidatedShellHandoff};
    use tauri::Url;

    fn handoff() -> ValidatedShellHandoff {
        ValidatedShellHandoff {
            runtime_url: Url::parse("http://127.0.0.1:8766/?code=fixture").unwrap(),
            runtime_port: 8766,
            identity: crate::host_contract::ExecutionProfileIdentity::new(
                "profile-a",
                format!("sha256:{}", "a".repeat(64)),
                "activation:profile-a-2026",
                format!("sha256:{}", "b".repeat(64)),
            )
            .unwrap(),
            catalog_revision: format!("sha256:{}", "c".repeat(64)),
            artifact: ShellArtifactIdentity {
                provider_id: "fixture.shell".into(),
                artifact_id: "fixture.shell.macos-arm64".into(),
                artifact_digest: format!("sha256:{}", "d".repeat(64)),
                entrypoint_digest: format!("sha256:{}", "e".repeat(64)),
            },
        }
    }

    fn assert_mismatch_preserves_state(mutate: impl FnOnce(&mut ValidatedShellHandoff)) {
        let initial = handoff();
        let mut state = ShellRuntimeState::default();
        state.accept_handoff(&initial).unwrap();
        let before = state.clone();
        let mut forwarded = handoff();
        mutate(&mut forwarded);

        assert!(state.accept_handoff(&forwarded).is_err());
        assert_eq!(state, before);
    }

    #[test]
    fn identical_forwarded_handoff_preserves_binding_and_ports() {
        let handoff = handoff();
        let mut state = ShellRuntimeState::default();
        state.accept_handoff(&handoff).unwrap();
        let before = state.clone();

        state.accept_handoff(&handoff).unwrap();

        assert_eq!(state, before);
    }

    #[test]
    fn forwarded_activation_mismatch_preserves_binding_and_ports() {
        assert_mismatch_preserves_state(|handoff| {
            handoff.identity.activation_id = "activation:profile-a-2027".into();
        });
    }

    #[test]
    fn forwarded_catalog_mismatch_preserves_binding_and_ports() {
        assert_mismatch_preserves_state(|handoff| {
            handoff.catalog_revision = format!("sha256:{}", "f".repeat(64));
        });
    }

    #[test]
    fn forwarded_artifact_digest_mismatch_preserves_binding_and_ports() {
        assert_mismatch_preserves_state(|handoff| {
            handoff.artifact.artifact_digest = format!("sha256:{}", "f".repeat(64));
        });
    }

    #[test]
    fn forwarded_port_mismatch_preserves_binding_and_ports() {
        assert_mismatch_preserves_state(|handoff| {
            handoff.runtime_port = 9876;
        });
    }
}
