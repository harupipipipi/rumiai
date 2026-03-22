fn main() {
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
