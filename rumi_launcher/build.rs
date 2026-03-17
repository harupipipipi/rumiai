fn main() {
    // Windows: embed application icon into the executable via winres
    #[cfg(target_os = "windows")]
    {
        let mut res = winres::WindowsResource::new();
        // Icon path relative to the Cargo project root
        // Place a .ico file at assets/icon.ico to embed it
        let icon_path = "assets/icon.ico";
        if std::path::Path::new(icon_path).exists() {
            res.set_icon(icon_path);
        }
        if let Err(e) = res.compile() {
            eprintln!("cargo:warning=winres compile failed: {e}");
        }
    }
}
