fn main() {
    // Re-run this build script if key files change.
    println!("cargo:rerun-if-changed=assets/icon.png");
    println!("cargo:rerun-if-changed=Packager.toml");
    println!("cargo:rerun-if-changed=build.rs");

    // Windows: embed application icon into the executable.
    // To enable, add `winres = "0.1"` to [build-dependencies] in Cargo.toml
    // and place a .ico file at assets/icon.ico.
    //
    // #[cfg(target_os = "windows")]
    // {
    //     let mut res = winres::WindowsResource::new();
    //     if std::path::Path::new("assets/icon.ico").exists() {
    //         res.set_icon("assets/icon.ico");
    //     }
    //     res.compile().expect("winres compile failed");
    // }
}
