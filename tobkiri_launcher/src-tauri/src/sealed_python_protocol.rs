//! Canonical cross-language wire contract for the sealed Python bootstrap.
//!
//! This module intentionally has no crate dependencies so `build.rs` and the
//! runtime use the same role identifiers, option names, and template audit.

use std::ffi::{OsStr, OsString};

pub const PROTOCOL_SCHEMA: &str = "io.tobkiri.sealed-python-launch.v1";
pub const ATTESTATION_SCHEMA: &str = "io.tobkiri.sealed-python-attestation.v1";
pub const BOOTSTRAP_MODULE: &str = "tobkiri_sealed.bootstrap";
pub const ROLE_TYPED: &str = "typed";
pub const ROLE_DEFAULTSPACK: &str = "defaultspack";
pub const ROLE_HOST_HELPER: &str = "host_helper";
pub const ARG_ROLE: &str = "--role";
pub const ARG_NONCE: &str = "--nonce";
pub const ARG_ATTESTATION: &str = "--attestation";
pub const ARG_MANIFEST: &str = "--manifest";
pub const ARG_ENVIRONMENT_ROOT: &str = "--environment-root";
pub const ARG_SEPARATOR: &str = "--";

pub const REQUIRED_TEMPLATE_FRAGMENTS: &[&str] = &[
    PROTOCOL_SCHEMA,
    ATTESTATION_SCHEMA,
    ROLE_TYPED,
    ROLE_DEFAULTSPACK,
    ROLE_HOST_HELPER,
    ARG_NONCE,
    ARG_ATTESTATION,
    ARG_MANIFEST,
    ARG_ENVIRONMENT_ROOT,
    "os.replace",
    "fsync",
    "chmod",
];

/// The sole accepted argument ordering for the bootstrap v1 boundary.
pub fn launch_arguments(
    role: &str,
    nonce: &str,
    attestation: &OsStr,
    manifest: &OsStr,
    environment_root: &OsStr,
) -> Vec<OsString> {
    [
        OsString::from("-m"),
        OsString::from(BOOTSTRAP_MODULE),
        OsString::from(ARG_ROLE),
        OsString::from(role),
        OsString::from(ARG_NONCE),
        OsString::from(nonce),
        OsString::from(ARG_ATTESTATION),
        attestation.to_os_string(),
        OsString::from(ARG_MANIFEST),
        manifest.to_os_string(),
        OsString::from(ARG_ENVIRONMENT_ROOT),
        environment_root.to_os_string(),
    ]
    .into()
}

/// Reject a packaging bootstrap that does not implement the complete v1 wire.
pub fn validate_bootstrap_template(template: &str) -> Result<(), String> {
    let missing = REQUIRED_TEMPLATE_FRAGMENTS
        .iter()
        .copied()
        .filter(|fragment| !template.contains(fragment))
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!(
            "sealed bootstrap does not implement {PROTOCOL_SCHEMA}; missing {}",
            missing.join(", ")
        ));
    }
    if !template.contains("parse_known_args") && !template.contains("role_args") {
        return Err(format!(
            "sealed bootstrap does not preserve role arguments after {ARG_SEPARATOR}"
        ));
    }
    if template.contains("secrets.token_hex") {
        return Err(
            "sealed bootstrap generates its own nonce instead of echoing Launcher nonce".into(),
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repository_bootstrap_is_audited_against_the_canonical_wire() {
        let template = include_str!(
            "../../../.github/scripts/sealed_python_sources/tobkiri_sealed/bootstrap.py"
        );
        let result = validate_bootstrap_template(template);
        if template.contains(PROTOCOL_SCHEMA) {
            result.expect("template declaring launch v1 must implement its complete wire");
        } else {
            let error = result.expect_err("legacy template must be rejected before packaging");
            assert!(error.contains(PROTOCOL_SCHEMA));
            assert!(error.contains(ARG_NONCE));
        }
    }

    #[test]
    fn launch_wire_has_one_typed_order_before_role_separator() {
        let arguments = launch_arguments(
            "defaultspack",
            "nonce",
            OsStr::new("attest"),
            OsStr::new("manifest"),
            OsStr::new("root"),
        );
        let strings = arguments
            .iter()
            .map(|value| value.to_string_lossy().into_owned())
            .collect::<Vec<_>>();
        assert_eq!(
            strings,
            [
                "-m",
                BOOTSTRAP_MODULE,
                ARG_ROLE,
                ROLE_DEFAULTSPACK,
                ARG_NONCE,
                "nonce",
                ARG_ATTESTATION,
                "attest",
                ARG_MANIFEST,
                "manifest",
                ARG_ENVIRONMENT_ROOT,
                "root"
            ]
        );
    }
}
