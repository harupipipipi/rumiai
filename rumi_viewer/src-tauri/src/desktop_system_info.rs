use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DesktopPermissionStatus {
    pub id: String,
    pub label: String,
    pub status: String,
    pub granted: Option<bool>,
    pub detail: String,
    pub settings_hint: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DesktopSystemInfo {
    pub app_name: String,
    pub display_version: String,
    pub viewer_version: String,
    pub build_channel: String,
    pub platform: String,
    pub platform_release: String,
    pub permissions: Vec<DesktopPermissionStatus>,
}

#[tauri::command]
pub fn get_desktop_system_info() -> DesktopSystemInfo {
    collect_desktop_system_info()
}

pub fn collect_desktop_system_info() -> DesktopSystemInfo {
    let viewer_version = env!("CARGO_PKG_VERSION").to_string();
    DesktopSystemInfo {
        app_name: "Rumi AI".to_string(),
        display_version: display_version_from_package_version(&viewer_version),
        viewer_version,
        build_channel: "beta".to_string(),
        platform: std::env::consts::OS.to_string(),
        platform_release: platform_release(),
        permissions: collect_permissions(),
    }
}

fn display_version_from_package_version(version: &str) -> String {
    if let Some((base, pre_release)) = version.split_once('-') {
        if let Some(label) = pre_release.split('.').next().filter(|value| !value.is_empty()) {
            return format!("{label} {base}");
        }
    }
    version.to_string()
}

fn platform_release() -> String {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("sw_vers")
            .arg("-productVersion")
            .output()
            .ok()
            .and_then(|output| String::from_utf8(output.stdout).ok())
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "unknown".to_string())
    }

    #[cfg(not(target_os = "macos"))]
    {
        std::env::consts::ARCH.to_string()
    }
}

fn collect_permissions() -> Vec<DesktopPermissionStatus> {
    #[cfg(target_os = "macos")]
    {
        macos_permissions()
    }

    #[cfg(not(target_os = "macos"))]
    {
        vec![DesktopPermissionStatus {
            id: "macos_privacy".to_string(),
            label: "macOS Privacy".to_string(),
            status: "unsupported".to_string(),
            granted: None,
            detail: "macOS permission checks are only available on macOS.".to_string(),
            settings_hint: String::new(),
        }]
    }
}

#[cfg(target_os = "macos")]
fn macos_permissions() -> Vec<DesktopPermissionStatus> {
    vec![
        permission_row(
            "accessibility",
            "Accessibility",
            Some(macos::accessibility_granted()),
            "Allows Rumi to inspect UI elements and send clicks/keyboard actions for Computer Use.",
            "System Settings > Privacy & Security > Accessibility",
        ),
        permission_row(
            "screen_recording",
            "Screen Recording",
            Some(macos::screen_recording_granted()),
            "Allows Rumi to capture the screen for Computer Use vision.",
            "System Settings > Privacy & Security > Screen Recording",
        ),
        DesktopPermissionStatus {
            id: "input_monitoring".to_string(),
            label: "Input Monitoring".to_string(),
            status: "not_checked".to_string(),
            granted: None,
            detail: "macOS does not provide a stable non-prompting preflight API for this permission. If key input fails, verify it manually.".to_string(),
            settings_hint: "System Settings > Privacy & Security > Input Monitoring".to_string(),
        },
    ]
}

#[cfg(target_os = "macos")]
fn permission_row(
    id: &str,
    label: &str,
    granted: Option<bool>,
    detail: &str,
    settings_hint: &str,
) -> DesktopPermissionStatus {
    let status = match granted {
        Some(true) => "granted",
        Some(false) => "missing",
        None => "not_checked",
    };
    DesktopPermissionStatus {
        id: id.to_string(),
        label: label.to_string(),
        status: status.to_string(),
        granted,
        detail: detail.to_string(),
        settings_hint: settings_hint.to_string(),
    }
}

#[cfg(target_os = "macos")]
mod macos {
    use std::os::raw::c_uchar;

    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXIsProcessTrusted() -> c_uchar;
    }

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGPreflightScreenCaptureAccess() -> bool;
    }

    pub fn accessibility_granted() -> bool {
        unsafe { AXIsProcessTrusted() != 0 }
    }

    pub fn screen_recording_granted() -> bool {
        unsafe { CGPreflightScreenCaptureAccess() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reports_beta_display_version() {
        let info = collect_desktop_system_info();
        assert_eq!(info.display_version, display_version_from_package_version(&info.viewer_version));
        assert_eq!(display_version_from_package_version("1.2.3-beta.4"), "beta 1.2.3");
        assert!(!info.viewer_version.is_empty());
    }

    #[test]
    fn permission_rows_have_stable_ids() {
        let info = collect_desktop_system_info();
        let ids: Vec<&str> = info.permissions.iter().map(|row| row.id.as_str()).collect();
        #[cfg(target_os = "macos")]
        {
            assert!(ids.contains(&"accessibility"));
            assert!(ids.contains(&"screen_recording"));
        }
        #[cfg(not(target_os = "macos"))]
        {
            assert_eq!(ids, vec!["macos_privacy"]);
        }
    }
}
