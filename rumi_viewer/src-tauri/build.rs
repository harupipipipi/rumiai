fn main() {
    println!("cargo:rerun-if-changed=splash/index.html");
    println!("cargo:rerun-if-changed=src/lib.rs");
    tauri_build::build()
}
