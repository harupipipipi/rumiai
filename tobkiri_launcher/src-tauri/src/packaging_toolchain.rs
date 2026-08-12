//! Formal, digest-bound tool inputs for production packaging.
//!
//! Release build code must never resolve Python or Git through PATH, nor
//! trust the ambient PYTHON variable. CI binds these values from a checked
//! toolchain-resolution step; every caller revalidates the absolute file and
//! its raw SHA-256 before spawning it.

use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Output, Stdio};

use sha2::{Digest, Sha256};

#[cfg(target_os = "macos")]
const SEC_CS_NO_NETWORK_ACCESS: u32 = 1 << 29;
#[cfg(target_os = "macos")]
const SEC_CS_STRICT_VALIDATE: u32 = 1 << 4;
#[cfg(target_os = "macos")]
const SEC_CS_CHECK_ALL_ARCHITECTURES: u32 = 1;
#[cfg(target_os = "macos")]
const SEC_CODE_SIGNATURE_ADHOC: i64 = 0x2;

#[cfg(target_os = "macos")]
fn accepted_macos_signature_flags(flags: i64) -> bool {
    flags & SEC_CODE_SIGNATURE_ADHOC == 0
}

pub const PYTHON_PATH_ENV: &str = "TOBKIRI_PACKAGING_PYTHON";
pub const PYTHON_SHA256_ENV: &str = "TOBKIRI_PACKAGING_PYTHON_SHA256";
pub const GIT_PATH_ENV: &str = "TOBKIRI_PACKAGING_GIT";
pub const GIT_SHA256_ENV: &str = "TOBKIRI_PACKAGING_GIT_SHA256";
#[cfg(target_os = "macos")]
pub const PYTHON_SNAPSHOT_ENV: &str = "TOBKIRI_PACKAGING_PYTHON_SNAPSHOT";
#[cfg(target_os = "macos")]
pub const PYTHON_INVENTORY_SHA256_ENV: &str = "TOBKIRI_PACKAGING_PYTHON_INVENTORY_SHA256";

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message.into())
}

fn valid_raw_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn file_identity(metadata: &fs::Metadata) -> (u64, u64, u64, u64, u64) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;

        return (
            metadata.dev(),
            metadata.ino(),
            metadata.len(),
            metadata.mtime_nsec() as u64,
            metadata.ctime_nsec() as u64,
        );
    }
    #[cfg(not(unix))]
    {
        let modified = metadata
            .modified()
            .ok()
            .and_then(|value| value.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |value| value.as_nanos() as u64);
        let created = metadata
            .created()
            .ok()
            .and_then(|value| value.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |value| value.as_nanos() as u64);
        (0, 0, metadata.len(), modified, created)
    }
}

fn validate_parent_path(path: &Path) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid("packaging tool has no parent directory"))?;
    let canonical = parent.canonicalize()?;
    if canonical != parent {
        return Err(invalid(format!(
            "packaging tool parent path is not canonical: {}",
            parent.display()
        )));
    }
    let metadata = fs::symlink_metadata(parent)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid("packaging tool parent is not a real directory"));
    }
    Ok(())
}

fn open_hashed_regular_executable(path: &Path) -> io::Result<(File, fs::Metadata, String)> {
    validate_parent_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(invalid(format!(
            "packaging tool is not a regular file: {}",
            path.display()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;

        let mode = before.permissions().mode();
        if mode & 0o111 == 0 {
            return Err(invalid(format!(
                "packaging tool is not executable: {}",
                path.display()
            )));
        }
        if mode & 0o022 != 0 {
            return Err(invalid(format!(
                "packaging tool is writable: {}",
                path.display()
            )));
        }
    }
    let canonical = path.canonicalize()?;
    if canonical != path {
        return Err(invalid(format!(
            "packaging tool path is not canonical: {}",
            path.display()
        )));
    }
    let mut digest = Sha256::new();
    let mut input = File::open(path)?;
    let opened = input.metadata()?;
    if file_identity(&opened) != file_identity(&before) {
        return Err(invalid(format!(
            "packaging tool changed while opened: {}",
            path.display()
        )));
    }
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    let after = fs::symlink_metadata(path)?;
    if after.file_type().is_symlink()
        || !after.is_file()
        || file_identity(&before) != file_identity(&after)
    {
        return Err(invalid(format!(
            "packaging tool changed while hashed: {}",
            path.display()
        )));
    }
    Ok((input, before, format!("{:x}", digest.finalize())))
}

#[allow(dead_code)]
pub struct VerifiedTool {
    kind: String,
    original_path: PathBuf,
    identity: (u64, u64, u64, u64, u64),
    #[cfg(unix)]
    execution_path: PathBuf,
    #[cfg(unix)]
    execution_owner: Option<PathBuf>,
    #[cfg(unix)]
    execution_identity: (u64, u64, u64, u64, u64),
    #[cfg(unix)]
    owns_execution_copy: bool,
    #[cfg(target_os = "macos")]
    macos_cdhash: Vec<u8>,
    #[cfg(target_os = "macos")]
    python_installation: Option<MacOSPythonInstallationLease>,
    lock: File,
}

#[cfg(target_os = "macos")]
struct MacOSPythonInstallationLease {
    root: PathBuf,
    identity: (u64, u64, u64, u64, u64),
    inventory: PathBuf,
    inventory_sha256: String,
    _root_handle: File,
}

#[cfg(target_os = "macos")]
impl MacOSPythonInstallationLease {
    fn verify_unchanged(&self) -> io::Result<()> {
        let current = fs::symlink_metadata(&self.root)?;
        if current.file_type().is_symlink()
            || !current.is_dir()
            || file_identity(&current) != self.identity
        {
            return Err(invalid("macOS Python installation root identity changed"));
        }
        let actual = format!("{:x}", Sha256::digest(fs::read(&self.inventory)?));
        if actual != self.inventory_sha256 {
            return Err(invalid("macOS Python installation inventory changed"));
        }
        Ok(())
    }
}

impl VerifiedTool {
    fn configure_command<'a>(&'a self, command: &mut VerifiedCommand<'a>) {
        if self.kind != "git" {
            return;
        }
        #[cfg(target_os = "macos")]
        command
            .env_clear()
            .args([
                "--no-optional-locks",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.attributesFile=/dev/null",
                "-c",
                "diff.external=",
                "-c",
                "filter.review.clean=",
                "-c",
                "filter.review.smudge=",
                "-c",
                "filter.review.process=",
                "-c",
                "filter.review.required=false",
                "-c",
                "core.sshCommand=false",
                "-c",
                "core.pager=cat",
                "-c",
                "pager.show=cat",
            ])
            .env("GIT_ATTR_NOSYSTEM", "1")
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_OPTIONAL_LOCKS", "0")
            .env("GIT_PAGER", "cat")
            .env("GIT_TERMINAL_PROMPT", "0")
            .env("LC_ALL", "C")
            .env("PATH", "/usr/bin:/bin")
            .env("PAGER", "cat")
            .env("GIT_CONFIG", "/dev/null")
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("GIT_CONFIG_SYSTEM", "/dev/null")
            .env("GIT_EXEC_PATH", "/private/var/empty")
            .env("HOME", "/private/var/empty")
            .env("XDG_CONFIG_HOME", "/private/var/empty");
    }

    pub fn command(&self) -> io::Result<VerifiedCommand<'_>> {
        #[cfg(not(unix))]
        {
            let current = fs::symlink_metadata(&self.original_path)?;
            if current.file_type().is_symlink()
                || !current.is_file()
                || file_identity(&current) != self.identity
            {
                return Err(invalid(format!(
                    "{} executable path changed before spawn",
                    self.kind
                )));
            }
        }
        #[cfg(unix)]
        {
            let execution = fs::symlink_metadata(&self.execution_path)?;
            if execution.file_type().is_symlink()
                || !execution.is_file()
                || file_identity(&execution) != self.execution_identity
            {
                return Err(invalid("sealed packaging tool copy was replaced"));
            }
            #[cfg(target_os = "macos")]
            {
                if let Some(installation) = &self.python_installation {
                    installation.verify_unchanged()?;
                }
                if macos_code_identity(&self.execution_path)? != self.macos_cdhash {
                    return Err(invalid("macOS packaging tool CDHash changed before spawn"));
                }
            }
            let mut command = VerifiedCommand::new(self);
            self.configure_command(&mut command);
            return Ok(command);
        }
        #[cfg(not(unix))]
        {
            let _ = &self.lock;
            let mut command = VerifiedCommand::new(self);
            self.configure_command(&mut command);
            Ok(command)
        }
    }

    #[cfg(test)]
    pub fn original_path(&self) -> &Path {
        &self.original_path
    }
}

impl Drop for VerifiedTool {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            if self.owns_execution_copy {
                if let Ok(metadata) = fs::symlink_metadata(&self.execution_path) {
                    if metadata.is_file()
                        && !metadata.file_type().is_symlink()
                        && file_identity(&metadata) == self.execution_identity
                    {
                        if let Some(owner) = &self.execution_owner {
                            use std::os::unix::fs::PermissionsExt;
                            let _ = fs::set_permissions(owner, fs::Permissions::from_mode(0o700));
                        }
                        let _ = fs::remove_file(&self.execution_path);
                        if let Some(owner) = &self.execution_owner {
                            let _ = fs::remove_dir(owner);
                        }
                    }
                }
            }
        }
    }
}

/// Command builder whose Unix child replaces itself from the verified open
/// executable descriptor.  No packaging tool pathname is reopened on Linux.
pub struct VerifiedCommand<'a> {
    tool: &'a VerifiedTool,
    args: Vec<std::ffi::OsString>,
    environment: std::collections::BTreeMap<std::ffi::OsString, std::ffi::OsString>,
    clear_environment: bool,
    current_dir: Option<PathBuf>,
    #[cfg(unix)]
    current_dir_handle: Option<File>,
}

pub enum VerifiedChild {
    Standard(Child),
    #[cfg(target_os = "macos")]
    Darwin(DarwinChild),
}

pub enum VerifiedSpawnOutcome {
    NoChild(io::Error),
    ReapedFailure(io::Error),
    Running(VerifiedChild),
    Uncontained(io::Error),
}

impl VerifiedChild {
    pub fn wait(&mut self) -> io::Result<ExitStatus> {
        match self {
            Self::Standard(child) => child.wait(),
            #[cfg(target_os = "macos")]
            Self::Darwin(child) => child.wait(),
        }
    }

    pub fn kill(&mut self) -> io::Result<()> {
        match self {
            Self::Standard(child) => child.kill(),
            #[cfg(target_os = "macos")]
            Self::Darwin(child) => child.kill(),
        }
    }

    pub fn wait_until(&mut self, deadline: std::time::Instant) -> io::Result<Option<ExitStatus>> {
        loop {
            let status = match self {
                Self::Standard(child) => child.try_wait()?,
                #[cfg(target_os = "macos")]
                Self::Darwin(child) => child.wait_nonblocking_until(deadline)?,
            };
            if status.is_some() || std::time::Instant::now() >= deadline {
                return Ok(status);
            }
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
    }
}

impl<'a> VerifiedCommand<'a> {
    fn new(tool: &'a VerifiedTool) -> Self {
        Self {
            tool,
            args: Vec::new(),
            environment: std::collections::BTreeMap::new(),
            clear_environment: false,
            current_dir: None,
            #[cfg(unix)]
            current_dir_handle: None,
        }
    }

    pub fn arg<S: AsRef<std::ffi::OsStr>>(&mut self, arg: S) -> &mut Self {
        self.args.push(arg.as_ref().to_owned());
        self
    }

    pub fn args<I, S>(&mut self, args: I) -> &mut Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<std::ffi::OsStr>,
    {
        self.args
            .extend(args.into_iter().map(|arg| arg.as_ref().to_owned()));
        self
    }

    pub fn env<K, V>(&mut self, key: K, value: V) -> &mut Self
    where
        K: AsRef<std::ffi::OsStr>,
        V: AsRef<std::ffi::OsStr>,
    {
        assert!(
            !key.as_ref().as_encoded_bytes().contains(&b'='),
            "environment key must not contain '='"
        );
        self.environment
            .insert(key.as_ref().to_owned(), value.as_ref().to_owned());
        self
    }

    pub fn env_clear(&mut self) -> &mut Self {
        self.clear_environment = true;
        self.environment.clear();
        self
    }

    pub fn current_dir<P: AsRef<Path>>(&mut self, path: P) -> io::Result<&mut Self> {
        self.current_dir = Some(path.as_ref().to_owned());
        #[cfg(target_os = "macos")]
        if self.tool.kind == "git" {
            self.environment.insert(
                std::ffi::OsString::from("GIT_CEILING_DIRECTORIES"),
                path.as_ref().as_os_str().to_owned(),
            );
        }
        #[cfg(unix)]
        {
            use std::ffi::CString;
            use std::os::fd::FromRawFd;
            use std::os::unix::ffi::OsStrExt;
            let encoded = CString::new(path.as_ref().as_os_str().as_bytes())
                .map_err(|_| invalid("verified command cwd contains NUL"))?;
            let fd = unsafe {
                libc::open(
                    encoded.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
                )
            };
            if fd == -1 {
                return Err(io::Error::last_os_error());
            }
            self.current_dir_handle = Some(unsafe { File::from_raw_fd(fd) });
        }
        Ok(self)
    }

    #[cfg(unix)]
    pub fn current_dir_handle(&mut self, directory: &File) -> io::Result<&mut Self> {
        self.current_dir = None;
        self.current_dir_handle = Some(directory.try_clone()?);
        Ok(self)
    }

    fn environment(&self) -> std::collections::BTreeMap<std::ffi::OsString, std::ffi::OsString> {
        let mut values = if self.clear_environment {
            std::collections::BTreeMap::new()
        } else {
            std::env::vars_os().collect()
        };
        values.extend(self.environment.clone());
        values
    }

    #[cfg(unix)]
    fn command_with_stdio(&self, capture: bool) -> io::Result<Command> {
        use std::ffi::CString;
        use std::os::fd::AsRawFd;
        use std::os::unix::ffi::OsStrExt;
        use std::os::unix::process::CommandExt;

        let executable = self.tool.execution_path.clone();
        let executable_c = CString::new(executable.as_os_str().as_bytes())
            .map_err(|_| invalid("sealed executable path contains NUL"))?;
        #[cfg(any(target_os = "linux", target_os = "android"))]
        let executable_fd = self.tool.lock.try_clone()?;
        let current_dir_fd = self
            .current_dir_handle
            .as_ref()
            .map(File::try_clone)
            .transpose()?;
        let argv = std::iter::once(self.tool.original_path.as_os_str())
            .chain(self.args.iter().map(std::ffi::OsString::as_os_str))
            .map(|value| {
                CString::new(value.as_bytes()).map_err(|_| invalid("tool argument contains NUL"))
            })
            .collect::<io::Result<Vec<_>>>()?;
        let environment = self
            .environment()
            .into_iter()
            .map(|(key, value)| {
                let mut pair = key.as_bytes().to_vec();
                pair.push(b'=');
                pair.extend_from_slice(value.as_bytes());
                CString::new(pair).map_err(|_| invalid("tool environment contains NUL"))
            })
            .collect::<io::Result<Vec<_>>>()?;
        let argv_ptrs = argv
            .iter()
            .map(|value| value.as_ptr())
            .chain(std::iter::once(std::ptr::null()))
            .map(|value| value as usize)
            .collect::<Vec<_>>();
        let environment_ptrs = environment
            .iter()
            .map(|value| value.as_ptr())
            .chain(std::iter::once(std::ptr::null()))
            .map(|value| value as usize)
            .collect::<Vec<_>>();
        let mut command = Command::new("/usr/bin/false");
        command.env_clear();
        if let Some(directory) = &self.current_dir {
            command.current_dir(directory);
        }
        if capture {
            command.stdout(Stdio::piped()).stderr(Stdio::piped());
        }
        unsafe {
            command.pre_exec(move || {
                let _argv_storage = &argv;
                let _environment_storage = &environment;
                let argv_raw = argv_ptrs.as_ptr().cast::<*const libc::c_char>();
                let environment_raw = environment_ptrs.as_ptr().cast::<*const libc::c_char>();
                if let Some(directory) = &current_dir_fd {
                    if libc::fchdir(directory.as_raw_fd()) == -1 {
                        return Err(io::Error::last_os_error());
                    }
                }
                #[cfg(any(target_os = "linux", target_os = "android"))]
                {
                    let fd = executable_fd.as_raw_fd();
                    if libc::fcntl(fd, libc::F_SETFD, 0) == -1 {
                        return Err(io::Error::last_os_error());
                    }
                    libc::fexecve(fd, argv_raw, environment_raw);
                }
                #[cfg(not(any(target_os = "linux", target_os = "android")))]
                {
                    libc::execve(executable_c.as_ptr(), argv_raw, environment_raw);
                }
                Err(io::Error::last_os_error())
            });
        }
        Ok(command)
    }

    #[cfg(windows)]
    fn command_with_stdio(&self, capture: bool) -> io::Result<Command> {
        let mut command = Command::new(&self.tool.original_path);
        if self.clear_environment {
            command.env_clear();
        }
        command.args(&self.args).envs(&self.environment);
        if let Some(directory) = &self.current_dir {
            command.current_dir(directory);
        }
        if capture {
            command.stdout(Stdio::piped()).stderr(Stdio::piped());
        }
        Ok(command)
    }

    #[cfg(target_os = "macos")]
    fn spawn_darwin(&self, capture: bool) -> VerifiedSpawnOutcome {
        let identity = match macos_code_identity(&self.tool.original_path) {
            Ok(identity) => identity,
            Err(error) => return VerifiedSpawnOutcome::NoChild(error),
        };
        if identity != self.tool.macos_cdhash {
            return VerifiedSpawnOutcome::NoChild(invalid(
                "macOS packaging tool identity changed before spawn",
            ));
        }
        if self.current_dir.is_some() && self.current_dir_handle.is_none() {
            return VerifiedSpawnOutcome::NoChild(invalid(
                "Darwin verified command cwd could not be anchored",
            ));
        }
        let mut child = match spawn_suspended_darwin(
            &self.tool.original_path,
            &self.args,
            &self.environment(),
            self.current_dir_handle.as_ref(),
            capture,
        ) {
            Ok(child) => child,
            Err(error) => return VerifiedSpawnOutcome::NoChild(error),
        };
        let capture_fds = [
            child.stdout.as_ref().map(std::os::fd::AsRawFd::as_raw_fd),
            child.stderr.as_ref().map(std::os::fd::AsRawFd::as_raw_fd),
        ];
        for fd in capture_fds.into_iter().flatten() {
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
            if flags == -1
                || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } == -1
            {
                let primary = io::Error::last_os_error();
                let containment = child.kill().and_then(|()| {
                    child
                        .wait_nonblocking_until(
                            std::time::Instant::now() + std::time::Duration::from_secs(2),
                        )?
                        .ok_or_else(|| invalid("timed out reaping Darwin child after pipe failure"))
                        .map(|_| ())
                });
                return match containment {
                    Ok(()) => VerifiedSpawnOutcome::ReapedFailure(primary),
                    Err(containment) => VerifiedSpawnOutcome::Uncontained(invalid(format!(
                        "{primary}; Darwin child containment also failed: {containment}"
                    ))),
                };
            }
        }
        let pid = child.pid;
        let result = (|| {
            if macos_guest_code_identity(pid)? != self.tool.macos_cdhash {
                return Err(invalid("suspended macOS child identity mismatch"));
            }
            if unsafe { libc::kill(pid, libc::SIGCONT) } == -1 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })();
        if let Err(error) = result {
            let mut child = child;
            let containment = child.kill().and_then(|()| {
                child
                    .wait_nonblocking_until(
                        std::time::Instant::now() + std::time::Duration::from_secs(2),
                    )?
                    .ok_or_else(|| invalid("timed out reaping rejected Darwin child"))
                    .map(|_| ())
            });
            return match containment {
                Ok(()) => VerifiedSpawnOutcome::ReapedFailure(error),
                Err(containment) => VerifiedSpawnOutcome::Uncontained(invalid(format!(
                    "{error}; rejected Darwin child containment also failed: {containment}"
                ))),
            };
        }
        VerifiedSpawnOutcome::Running(VerifiedChild::Darwin(child))
    }

    pub fn spawn_outcome(&mut self) -> VerifiedSpawnOutcome {
        #[cfg(target_os = "macos")]
        {
            return self.spawn_darwin(false);
        }
        #[cfg(not(target_os = "macos"))]
        {
            match self
                .command_with_stdio(false)
                .and_then(|mut command| command.spawn())
            {
                Ok(child) => VerifiedSpawnOutcome::Running(VerifiedChild::Standard(child)),
                Err(error) => VerifiedSpawnOutcome::NoChild(error),
            }
        }
    }

    pub fn spawn(&mut self) -> io::Result<VerifiedChild> {
        match self.spawn_outcome() {
            VerifiedSpawnOutcome::Running(child) => Ok(child),
            VerifiedSpawnOutcome::NoChild(error)
            | VerifiedSpawnOutcome::ReapedFailure(error)
            | VerifiedSpawnOutcome::Uncontained(error) => Err(error),
        }
    }

    pub fn status(&mut self) -> io::Result<ExitStatus> {
        self.spawn()?.wait()
    }

    pub fn output(&mut self) -> io::Result<Output> {
        #[cfg(target_os = "macos")]
        {
            return match self.spawn_darwin(true) {
                VerifiedSpawnOutcome::Running(VerifiedChild::Darwin(child)) => {
                    child.wait_with_output()
                }
                VerifiedSpawnOutcome::NoChild(error)
                | VerifiedSpawnOutcome::ReapedFailure(error)
                | VerifiedSpawnOutcome::Uncontained(error) => Err(error),
                VerifiedSpawnOutcome::Running(VerifiedChild::Standard(_)) => unreachable!(),
            };
        }
        #[cfg(not(target_os = "macos"))]
        {
            let mut command = self.command_with_stdio(true)?;
            command.stdin(Stdio::null());
            command.spawn()?.wait_with_output()
        }
    }
}

#[cfg(target_os = "macos")]
fn spawn_suspended_darwin(
    executable: &Path,
    arguments: &[std::ffi::OsString],
    environment: &std::collections::BTreeMap<std::ffi::OsString, std::ffi::OsString>,
    directory: Option<&File>,
    capture: bool,
) -> io::Result<DarwinChild> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::ffi::OsStrExt;

    unsafe extern "C" {
        fn posix_spawn(
            pid: *mut i32,
            path: *const libc::c_char,
            actions: *const *mut std::ffi::c_void,
            attributes: *const *mut std::ffi::c_void,
            argv: *const *mut libc::c_char,
            envp: *const *mut libc::c_char,
        ) -> i32;
        fn posix_spawnattr_init(attributes: *mut *mut std::ffi::c_void) -> i32;
        fn posix_spawnattr_setflags(attributes: *mut *mut std::ffi::c_void, flags: i16) -> i32;
        fn posix_spawnattr_destroy(attributes: *mut *mut std::ffi::c_void) -> i32;
        fn posix_spawn_file_actions_init(actions: *mut *mut std::ffi::c_void) -> i32;
        fn posix_spawn_file_actions_addfchdir_np(
            actions: *mut *mut std::ffi::c_void,
            fd: i32,
        ) -> i32;
        fn posix_spawn_file_actions_adddup2(
            actions: *mut *mut std::ffi::c_void,
            fd: i32,
            newfd: i32,
        ) -> i32;
        fn posix_spawn_file_actions_addclose(actions: *mut *mut std::ffi::c_void, fd: i32) -> i32;
        fn posix_spawn_file_actions_destroy(actions: *mut *mut std::ffi::c_void) -> i32;
    }
    fn pipe() -> io::Result<(File, File)> {
        let mut fds = [-1; 2];
        if unsafe { libc::pipe(fds.as_mut_ptr()) } == -1 {
            return Err(io::Error::last_os_error());
        }
        for fd in fds {
            if unsafe { libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) } == -1 {
                unsafe {
                    libc::close(fds[0]);
                    libc::close(fds[1]);
                }
                return Err(io::Error::last_os_error());
            }
        }
        Ok(unsafe { (File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])) })
    }
    let path = CString::new(executable.as_os_str().as_bytes())
        .map_err(|_| invalid("Darwin executable path contains NUL"))?;
    let argv = std::iter::once(executable.as_os_str())
        .chain(arguments.iter().map(std::ffi::OsString::as_os_str))
        .map(|value| {
            CString::new(value.as_bytes()).map_err(|_| invalid("Darwin argument contains NUL"))
        })
        .collect::<io::Result<Vec<_>>>()?;
    let env = environment
        .iter()
        .map(|(key, value)| {
            let mut pair = key.as_bytes().to_vec();
            pair.push(b'=');
            pair.extend_from_slice(value.as_bytes());
            CString::new(pair).map_err(|_| invalid("Darwin environment contains NUL"))
        })
        .collect::<io::Result<Vec<_>>>()?;
    let mut argv_ptrs = argv
        .iter()
        .map(|v| v.as_ptr() as *mut _)
        .chain(std::iter::once(std::ptr::null_mut()))
        .collect::<Vec<_>>();
    let mut env_ptrs = env
        .iter()
        .map(|v| v.as_ptr() as *mut _)
        .chain(std::iter::once(std::ptr::null_mut()))
        .collect::<Vec<_>>();
    let (stdout_read, stdout_write) = if capture {
        let (r, w) = pipe()?;
        (Some(r), Some(w))
    } else {
        (None, None)
    };
    let (stderr_read, stderr_write) = if capture {
        let (r, w) = pipe()?;
        (Some(r), Some(w))
    } else {
        (None, None)
    };
    let null_input = if capture {
        Some(File::open("/dev/null")?)
    } else {
        None
    };
    let mut attributes = std::ptr::null_mut();
    let mut actions = std::ptr::null_mut();
    let mut pid = 0_i32;
    let result = unsafe {
        let mut code = posix_spawnattr_init(&mut attributes);
        if code == 0 {
            code =
                posix_spawnattr_setflags(&mut attributes, libc::POSIX_SPAWN_START_SUSPENDED as i16);
        }
        if code == 0 {
            code = posix_spawn_file_actions_init(&mut actions);
        }
        if code == 0 {
            if let Some(directory) = directory {
                code = posix_spawn_file_actions_addfchdir_np(&mut actions, directory.as_raw_fd());
            }
        }
        if code == 0 {
            if let Some(file) = &null_input {
                code = posix_spawn_file_actions_adddup2(
                    &mut actions,
                    file.as_raw_fd(),
                    libc::STDIN_FILENO,
                );
            }
        }
        if code == 0 {
            if let Some(file) = &stdout_write {
                code = posix_spawn_file_actions_adddup2(
                    &mut actions,
                    file.as_raw_fd(),
                    libc::STDOUT_FILENO,
                );
            }
        }
        if code == 0 {
            if let Some(file) = &stderr_write {
                code = posix_spawn_file_actions_adddup2(
                    &mut actions,
                    file.as_raw_fd(),
                    libc::STDERR_FILENO,
                );
            }
        }
        if code == 0 {
            if let Some(file) = &stdout_read {
                code = posix_spawn_file_actions_addclose(&mut actions, file.as_raw_fd());
            }
        }
        if code == 0 {
            if let Some(file) = &stderr_read {
                code = posix_spawn_file_actions_addclose(&mut actions, file.as_raw_fd());
            }
        }
        for file in [&null_input, &stdout_write, &stderr_write]
            .into_iter()
            .flatten()
        {
            if code == 0
                && ![libc::STDIN_FILENO, libc::STDOUT_FILENO, libc::STDERR_FILENO]
                    .contains(&file.as_raw_fd())
            {
                code = posix_spawn_file_actions_addclose(&mut actions, file.as_raw_fd());
            }
        }
        if code == 0 {
            code = posix_spawn(
                &mut pid,
                path.as_ptr(),
                &actions,
                &attributes,
                argv_ptrs.as_mut_ptr(),
                env_ptrs.as_mut_ptr(),
            );
        }
        if !actions.is_null() {
            posix_spawn_file_actions_destroy(&mut actions);
        }
        if !attributes.is_null() {
            posix_spawnattr_destroy(&mut attributes);
        }
        code
    };
    drop(stdout_write);
    drop(stderr_write);
    if result != 0 {
        return Err(io::Error::from_raw_os_error(result));
    }
    let child = DarwinChild {
        pid,
        stdout: stdout_read,
        stderr: stderr_read,
        status: None,
        state: DarwinChildState::Running,
    };
    Ok(child)
}

#[cfg(target_os = "macos")]
fn macos_guest_code_identity(pid: i32) -> io::Result<Vec<u8>> {
    type CFTypeRef = *const std::ffi::c_void;
    type CFDictionaryRef = *const std::ffi::c_void;
    type SecCodeRef = *const std::ffi::c_void;
    #[link(name = "CoreFoundation", kind = "framework")]
    unsafe extern "C" {
        fn CFNumberCreate(
            allocator: CFTypeRef,
            kind: i32,
            value: *const std::ffi::c_void,
        ) -> CFTypeRef;
        fn CFDictionaryCreate(
            allocator: CFTypeRef,
            keys: *const CFTypeRef,
            values: *const CFTypeRef,
            count: isize,
            key_callbacks: *const std::ffi::c_void,
            value_callbacks: *const std::ffi::c_void,
        ) -> CFDictionaryRef;
        fn CFDictionaryGetValue(dictionary: CFDictionaryRef, key: CFTypeRef) -> CFTypeRef;
        fn CFDataGetLength(data: CFTypeRef) -> isize;
        fn CFDataGetBytePtr(data: CFTypeRef) -> *const u8;
        fn CFRelease(value: CFTypeRef);
    }
    #[link(name = "Security", kind = "framework")]
    unsafe extern "C" {
        static kSecGuestAttributePid: CFTypeRef;
        static kSecCodeInfoUnique: CFTypeRef;
        fn SecCodeCopyGuestWithAttributes(
            host: SecCodeRef,
            attributes: CFDictionaryRef,
            flags: u32,
            guest: *mut SecCodeRef,
        ) -> i32;
        fn SecCodeCopySigningInformation(
            code: SecCodeRef,
            flags: u32,
            information: *mut CFDictionaryRef,
        ) -> i32;
    }
    let number = unsafe {
        CFNumberCreate(
            std::ptr::null(),
            9,
            (&pid as *const i32).cast::<std::ffi::c_void>(),
        )
    };
    if number.is_null() {
        return Err(invalid("could not encode suspended macOS child PID"));
    }
    let attributes = unsafe {
        CFDictionaryCreate(
            std::ptr::null(),
            &kSecGuestAttributePid,
            &number,
            1,
            std::ptr::null(),
            std::ptr::null(),
        )
    };
    if attributes.is_null() {
        unsafe { CFRelease(number) };
        return Err(invalid("could not create suspended macOS child attributes"));
    }
    let mut guest = std::ptr::null();
    let copied =
        unsafe { SecCodeCopyGuestWithAttributes(std::ptr::null(), attributes, 0, &mut guest) };
    unsafe { CFRelease(attributes) };
    unsafe { CFRelease(number) };
    if copied != 0 || guest.is_null() {
        return Err(invalid(
            "could not resolve suspended macOS child code object",
        ));
    }
    let mut information = std::ptr::null();
    let signed = unsafe { SecCodeCopySigningInformation(guest, 1 << 1, &mut information) };
    unsafe { CFRelease(guest) };
    if signed != 0 || information.is_null() {
        return Err(invalid("could not read suspended macOS child signature"));
    }
    let unique = unsafe { CFDictionaryGetValue(information, kSecCodeInfoUnique) };
    let length = if unique.is_null() {
        0
    } else {
        unsafe { CFDataGetLength(unique) }
    };
    if length <= 0 || length > 64 {
        unsafe { CFRelease(information) };
        return Err(invalid("suspended macOS child CDHash is unavailable"));
    }
    let digest =
        unsafe { std::slice::from_raw_parts(CFDataGetBytePtr(unique), length as usize) }.to_vec();
    unsafe { CFRelease(information) };
    Ok(digest)
}

#[cfg(target_os = "macos")]
pub struct DarwinChild {
    pid: i32,
    stdout: Option<File>,
    stderr: Option<File>,
    status: Option<ExitStatus>,
    state: DarwinChildState,
}

#[cfg(target_os = "macos")]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum DarwinChildState {
    Running,
    KillSent,
    Reaped,
    ExternalReaped,
    Lost,
}

#[cfg(target_os = "macos")]
impl DarwinChild {
    fn wait_nonblocking_until(
        &mut self,
        deadline: std::time::Instant,
    ) -> io::Result<Option<ExitStatus>> {
        if let Some(status) = self.status {
            self.state = DarwinChildState::Reaped;
            return Ok(Some(status));
        }
        loop {
            let mut raw = 0;
            let result = unsafe { libc::waitpid(self.pid, &mut raw, libc::WNOHANG) };
            if result == self.pid {
                use std::os::unix::process::ExitStatusExt;
                let status = ExitStatus::from_raw(raw);
                self.status = Some(status);
                self.state = DarwinChildState::Reaped;
                return Ok(Some(status));
            }
            if result == -1 {
                let error = io::Error::last_os_error();
                if matches!(error.raw_os_error(), Some(libc::ECHILD)) {
                    self.state = DarwinChildState::ExternalReaped;
                    return Err(invalid("Darwin child was already reaped externally"));
                }
                if error.raw_os_error() != Some(libc::EINTR) {
                    self.state = DarwinChildState::Lost;
                    return Err(error);
                }
            }
            if std::time::Instant::now() >= deadline {
                return Ok(None);
            }
            std::thread::yield_now();
        }
    }

    fn wait(&mut self) -> io::Result<ExitStatus> {
        if let Some(status) = self.status {
            self.state = DarwinChildState::Reaped;
            return Ok(status);
        }
        if self.state == DarwinChildState::Lost {
            return Err(invalid("refusing to wait on a lost Darwin child PID"));
        }
        if self.state == DarwinChildState::ExternalReaped {
            return Err(invalid("Darwin child was already reaped externally"));
        }
        let mut raw = 0;
        loop {
            if unsafe { libc::waitpid(self.pid, &mut raw, 0) } != -1 {
                break;
            }
            let error = io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::ECHILD) {
                self.state = DarwinChildState::ExternalReaped;
                return Err(invalid("Darwin child was already reaped externally"));
            }
            if error.raw_os_error() != Some(libc::EINTR) {
                self.state = DarwinChildState::Lost;
                return Err(error);
            }
        }
        use std::os::unix::process::ExitStatusExt;
        let status = ExitStatus::from_raw(raw);
        self.status = Some(status);
        self.state = DarwinChildState::Reaped;
        Ok(status)
    }

    fn kill(&mut self) -> io::Result<()> {
        if self.status.is_some() {
            self.state = DarwinChildState::Reaped;
            return Ok(());
        }
        if self.state == DarwinChildState::Lost {
            return Err(invalid("refusing to signal a lost Darwin child PID"));
        }
        if self.state == DarwinChildState::ExternalReaped {
            return Err(invalid("Darwin child was already reaped externally"));
        }
        if unsafe { libc::kill(self.pid, libc::SIGKILL) } == -1 {
            let error = io::Error::last_os_error();
            if matches!(error.raw_os_error(), Some(libc::ESRCH) | Some(libc::ECHILD)) {
                if error.raw_os_error() == Some(libc::ECHILD) {
                    self.state = DarwinChildState::ExternalReaped;
                    return Err(invalid("Darwin child was already reaped externally"));
                }
                match self.wait_nonblocking_until(
                    std::time::Instant::now() + std::time::Duration::from_secs(2),
                )? {
                    Some(_) => Ok(()),
                    None => {
                        self.state = DarwinChildState::Lost;
                        Err(invalid("Darwin child was lost before reap"))
                    }
                }
            } else {
                self.state = DarwinChildState::Lost;
                Err(error)
            }
        } else {
            self.state = DarwinChildState::KillSent;
            Ok(())
        }
    }

    fn wait_with_output(mut self) -> io::Result<Output> {
        use std::sync::{atomic::AtomicUsize, Arc};
        const MAX_CAPTURE_BYTES: usize = 64 * 1024 * 1024;
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);
        let budget = Arc::new(AtomicUsize::new(MAX_CAPTURE_BYTES));
        let stdout_budget = Arc::clone(&budget);
        let stdout = self.stdout.take().map(|mut file| {
            std::thread::spawn(move || {
                let mut bytes = Vec::new();
                read_nonblocking_to_end(&mut file, &mut bytes, deadline, &stdout_budget)
                    .map(|()| bytes)
            })
        });
        let stderr_budget = Arc::clone(&budget);
        let stderr = self.stderr.take().map(|mut file| {
            std::thread::spawn(move || {
                let mut bytes = Vec::new();
                read_nonblocking_to_end(&mut file, &mut bytes, deadline, &stderr_budget)
                    .map(|()| bytes)
            })
        });
        let status_result = match self.wait_nonblocking_until(deadline) {
            Ok(Some(status)) => Ok(status),
            Ok(None) => {
                let primary = invalid("timed out waiting for Darwin child");
                match self.kill().and_then(|()| {
                    self.wait_nonblocking_until(
                        std::time::Instant::now() + std::time::Duration::from_secs(2),
                    )?
                    .ok_or_else(|| invalid("timed out reaping Darwin child"))
                }) {
                    Ok(_) => Err(primary),
                    Err(cleanup) => Err(invalid(format!(
                        "{primary}; Darwin child containment also failed: {cleanup}"
                    ))),
                }
            }
            Err(primary) if self.state == DarwinChildState::ExternalReaped => Err(primary),
            Err(primary) => Err(invalid(format!(
                "{primary}; Darwin child identity is lost, so PID containment was stopped to avoid signaling a reused PID"
            ))),
        };
        let stdout_result = join_reader(stdout, "stdout");
        let stderr_result = join_reader(stderr, "stderr");
        let (status, stdout, stderr) = match (status_result, stdout_result, stderr_result) {
            (Ok(status), Ok(stdout), Ok(stderr)) => (status, stdout, stderr),
            (status, stdout, stderr) => {
                let errors = [status.err(), stdout.err(), stderr.err()]
                    .into_iter()
                    .flatten()
                    .map(|error| error.to_string())
                    .collect::<Vec<_>>()
                    .join("; ");
                return Err(invalid(format!(
                    "Darwin child output collection failed: {errors}"
                )));
            }
        };
        Ok(Output {
            status,
            stdout,
            stderr,
        })
    }
}

#[cfg(target_os = "macos")]
fn read_nonblocking_to_end(
    file: &mut File,
    bytes: &mut Vec<u8>,
    deadline: std::time::Instant,
    budget: &std::sync::atomic::AtomicUsize,
) -> io::Result<()> {
    use std::sync::atomic::Ordering;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        if std::time::Instant::now() >= deadline {
            return Err(invalid("timed out draining Darwin child output"));
        }
        match file.read(&mut buffer) {
            Ok(0) => return Ok(()),
            Ok(count) => {
                if budget
                    .fetch_update(Ordering::AcqRel, Ordering::Acquire, |remaining| {
                        remaining.checked_sub(count)
                    })
                    .is_err()
                {
                    return Err(invalid("Darwin child output exceeded capture limit"));
                }
                bytes.extend_from_slice(&buffer[..count]);
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                if std::time::Instant::now() >= deadline {
                    return Err(invalid("timed out draining Darwin child output"));
                }
                std::thread::sleep(std::time::Duration::from_millis(2));
            }
            Err(error) => return Err(error),
        }
    }
}

#[cfg(target_os = "macos")]
fn join_reader(
    reader: Option<std::thread::JoinHandle<io::Result<Vec<u8>>>>,
    stream: &str,
) -> io::Result<Vec<u8>> {
    reader
        .map(|thread| {
            thread
                .join()
                .map_err(|_| invalid(format!("{stream} reader panicked")))?
        })
        .transpose()
        .map(|value| value.unwrap_or_default())
}

#[cfg(target_os = "macos")]
impl Drop for DarwinChild {
    fn drop(&mut self) {
        if self.status.is_none()
            && !matches!(
                self.state,
                DarwinChildState::ExternalReaped | DarwinChildState::Lost
            )
        {
            let _ = self.kill();
            let _ = self.wait_nonblocking_until(
                std::time::Instant::now() + std::time::Duration::from_secs(2),
            );
        }
    }
}

#[cfg(unix)]
fn sealed_executable_copy(
    source: &mut File,
    _original: &Path,
    expected: &str,
) -> io::Result<(PathBuf, Option<PathBuf>, fs::Metadata, bool)> {
    use std::os::unix::fs::PermissionsExt;
    use std::time::{SystemTime, UNIX_EPOCH};

    let base = env::temp_dir().canonicalize()?;
    for attempt in 0..128_u32 {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let owner = base.join(format!(
            "tobkiri-verified-tool-{}-{nonce}-{attempt}",
            std::process::id()
        ));
        match fs::create_dir(&owner) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
        fs::set_permissions(&owner, fs::Permissions::from_mode(0o700))?;
        let target = owner.join("executable");
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
        {
            Ok(mut output) => {
                source.seek(SeekFrom::Start(0))?;
                io::copy(source, &mut output)?;
                output.sync_all()?;
                fs::set_permissions(&target, fs::Permissions::from_mode(0o500))?;
                let metadata = fs::symlink_metadata(&target)?;
                let copied = fs::read(&target)?;
                if format!("{:x}", Sha256::digest(&copied)) != expected {
                    let _ = fs::remove_file(&target);
                    return Err(invalid("sealed packaging tool copy digest mismatch"));
                }
                fs::set_permissions(&owner, fs::Permissions::from_mode(0o500))?;
                return Ok((target, Some(owner), metadata, true));
            }
            Err(error) => {
                let _ = fs::remove_dir(&owner);
                return Err(error);
            }
        }
    }
    Err(invalid("could not create sealed packaging tool copy"))
}

#[cfg(target_os = "macos")]
fn macos_code_identity(path: &Path) -> io::Result<Vec<u8>> {
    use std::os::unix::ffi::OsStrExt;
    use std::ptr;

    type CFTypeRef = *const std::ffi::c_void;
    type CFURLRef = *const std::ffi::c_void;
    type CFDictionaryRef = *const std::ffi::c_void;
    type SecStaticCodeRef = *const std::ffi::c_void;
    #[link(name = "CoreFoundation", kind = "framework")]
    unsafe extern "C" {
        fn CFURLCreateFromFileSystemRepresentation(
            allocator: CFTypeRef,
            bytes: *const u8,
            length: isize,
            is_directory: u8,
        ) -> CFURLRef;
        fn CFDictionaryGetValue(dictionary: CFDictionaryRef, key: CFTypeRef) -> CFTypeRef;
        fn CFNumberGetValue(number: CFTypeRef, kind: i32, value: *mut std::ffi::c_void) -> u8;
        fn CFDataGetLength(data: CFTypeRef) -> isize;
        fn CFDataGetBytePtr(data: CFTypeRef) -> *const u8;
        fn CFRelease(value: CFTypeRef);
    }
    #[link(name = "Security", kind = "framework")]
    unsafe extern "C" {
        static kSecCodeInfoFlags: CFTypeRef;
        static kSecCodeInfoUnique: CFTypeRef;
        fn SecStaticCodeCreateWithPath(
            path: CFURLRef,
            flags: u32,
            code: *mut SecStaticCodeRef,
        ) -> i32;
        fn SecStaticCodeCheckValidity(
            code: SecStaticCodeRef,
            flags: u32,
            requirement: CFTypeRef,
        ) -> i32;
        fn SecCodeCopySigningInformation(
            code: SecStaticCodeRef,
            flags: u32,
            information: *mut CFDictionaryRef,
        ) -> i32;
    }
    let bytes = path.as_os_str().as_bytes();
    let url = unsafe {
        CFURLCreateFromFileSystemRepresentation(
            ptr::null(),
            bytes.as_ptr(),
            bytes.len() as isize,
            0,
        )
    };
    if url.is_null() {
        return Err(invalid("could not create macOS packaging tool URL"));
    }
    let mut code = ptr::null();
    let create = unsafe { SecStaticCodeCreateWithPath(url, 0, &mut code) };
    unsafe { CFRelease(url) };
    if create != 0 || code.is_null() {
        return Err(invalid("macOS packaging tool is unsigned"));
    }
    const STRICT_VALIDITY: u32 =
        SEC_CS_NO_NETWORK_ACCESS | SEC_CS_STRICT_VALIDATE | SEC_CS_CHECK_ALL_ARCHITECTURES;
    let validity = unsafe { SecStaticCodeCheckValidity(code, STRICT_VALIDITY, ptr::null()) };
    let mut information = ptr::null();
    let copied = unsafe { SecCodeCopySigningInformation(code, 1 << 1, &mut information) };
    unsafe { CFRelease(code) };
    if validity != 0 || copied != 0 || information.is_null() {
        return Err(invalid("macOS packaging tool signature is invalid"));
    }
    let flags_value = unsafe { CFDictionaryGetValue(information, kSecCodeInfoFlags) };
    let mut flags = 0_i64;
    let flags_ok = !flags_value.is_null()
        && unsafe {
            CFNumberGetValue(
                flags_value,
                4,
                (&mut flags as *mut i64).cast::<std::ffi::c_void>(),
            )
        } != 0;
    if !flags_ok || !accepted_macos_signature_flags(flags) {
        unsafe { CFRelease(information) };
        return Err(invalid(
            "macOS packaging tool is ad-hoc or has unavailable signature flags",
        ));
    }
    let unique = unsafe { CFDictionaryGetValue(information, kSecCodeInfoUnique) };
    let length = if unique.is_null() {
        0
    } else {
        unsafe { CFDataGetLength(unique) }
    };
    if length <= 0 || length > 64 {
        unsafe { CFRelease(information) };
        return Err(invalid("macOS packaging tool CDHash is unavailable"));
    }
    let digest =
        unsafe { std::slice::from_raw_parts(CFDataGetBytePtr(unique), length as usize) }.to_vec();
    unsafe { CFRelease(information) };
    Ok(digest)
}

#[cfg(target_os = "macos")]
fn macos_python_installation_lease(path: &Path) -> io::Result<MacOSPythonInstallationLease> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let raw_root = env::var_os(PYTHON_SNAPSHOT_ENV)
        .ok_or_else(|| invalid(format!("{PYTHON_SNAPSHOT_ENV} is required for Python")))?;
    let root = PathBuf::from(raw_root);
    if !root.is_absolute() || root.canonicalize()? != root {
        return Err(invalid("macOS Python installation root is not canonical"));
    }
    let expected_root = Path::new("/Library/Frameworks/Python.framework/Versions/3.13");
    if root != expected_root {
        return Err(invalid(
            "macOS Python installation root is not the fixed authority",
        ));
    }
    for component in std::iter::once(root.as_path()).chain(root.ancestors().skip(1)) {
        let metadata = fs::symlink_metadata(component)?;
        if metadata.file_type().is_symlink()
            || !metadata.is_dir()
            || metadata.uid() != 0
            || metadata.permissions().mode() & 0o022 != 0
        {
            return Err(invalid(format!(
                "macOS Python installation has writable/non-root ancestor: {}",
                component.display()
            )));
        }
    }
    let before = fs::symlink_metadata(&root)?;
    if !path.starts_with(&root) || path.canonicalize()? != path {
        return Err(invalid("macOS Python executable escapes its installation"));
    }
    let inventory = root.join(".tobkiri-packaging-python.v1.json");
    let inventory_metadata = fs::symlink_metadata(&inventory)?;
    if inventory_metadata.file_type().is_symlink()
        || !inventory_metadata.is_file()
        || inventory_metadata.uid() != 0
        || inventory_metadata.permissions().mode() & 0o022 != 0
        || inventory_metadata.nlink() != 1
    {
        return Err(invalid("macOS Python inventory is not immutable"));
    }
    let inventory_sha256 = env::var(PYTHON_INVENTORY_SHA256_ENV).map_err(|_| {
        invalid(format!(
            "{PYTHON_INVENTORY_SHA256_ENV} is required for Python"
        ))
    })?;
    if !valid_raw_sha256(&inventory_sha256) {
        return Err(invalid(format!(
            "{PYTHON_INVENTORY_SHA256_ENV} must be lowercase raw SHA-256"
        )));
    }
    let root_handle = File::open(&root)?;
    if file_identity(&root_handle.metadata()?) != file_identity(&before) {
        return Err(invalid("macOS Python installation changed while leased"));
    }
    let lease = MacOSPythonInstallationLease {
        root,
        identity: file_identity(&before),
        inventory,
        inventory_sha256,
        _root_handle: root_handle,
    };
    lease.verify_unchanged()?;
    Ok(lease)
}

#[cfg(windows)]
fn locked_windows_executable(path: &Path, expected: &str) -> io::Result<File> {
    use std::mem::{size_of, MaybeUninit};
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::{GENERIC_READ, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FileAttributeTagInfo, FileStandardInfo, GetFileInformationByHandleEx,
        FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_NORMAL, FILE_ATTRIBUTE_REPARSE_POINT,
        FILE_ATTRIBUTE_TAG_INFO, FILE_FLAG_OPEN_REPARSE_POINT, FILE_SHARE_READ, FILE_STANDARD_INFO,
        OPEN_EXISTING,
    };

    let wide = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            GENERIC_READ,
            FILE_SHARE_READ,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    let mut file = unsafe { File::from_raw_handle(handle) };
    let mut attributes = MaybeUninit::<FILE_ATTRIBUTE_TAG_INFO>::zeroed();
    if unsafe {
        GetFileInformationByHandleEx(
            handle,
            FileAttributeTagInfo,
            attributes.as_mut_ptr().cast(),
            size_of::<FILE_ATTRIBUTE_TAG_INFO>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    let attributes = unsafe { attributes.assume_init() };
    if attributes.FileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY) != 0 {
        return Err(invalid(
            "Windows packaging tool is a reparse point or directory",
        ));
    }
    let mut standard = MaybeUninit::<FILE_STANDARD_INFO>::zeroed();
    if unsafe {
        GetFileInformationByHandleEx(
            handle,
            FileStandardInfo,
            standard.as_mut_ptr().cast(),
            size_of::<FILE_STANDARD_INFO>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    if unsafe { standard.assume_init() }.NumberOfLinks != 1 {
        return Err(invalid("Windows packaging tool is hardlinked"));
    }
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    file.seek(SeekFrom::Start(0))?;
    if format!("{:x}", digest.finalize()) != expected {
        return Err(invalid(
            "packaging tool changed before Windows lock acquisition",
        ));
    }
    Ok(file)
}

fn binding(kind: &str) -> (&'static str, &'static str) {
    match kind {
        "python" => (PYTHON_PATH_ENV, PYTHON_SHA256_ENV),
        "git" => (GIT_PATH_ENV, GIT_SHA256_ENV),
        _ => ("", ""),
    }
}

/// Resolve and verify one formally bound packaging executable.
pub fn verified_tool(kind: &str) -> io::Result<VerifiedTool> {
    let (path_key, digest_key) = binding(kind);
    if path_key.is_empty() {
        return Err(invalid(format!("unknown packaging tool: {kind}")));
    }
    let raw_path = env::var_os(path_key)
        .ok_or_else(|| invalid(format!("{path_key} is required; PATH lookup is forbidden")))?;
    let path = PathBuf::from(raw_path);
    if !path.is_absolute() {
        return Err(invalid(format!("{path_key} must be an absolute path")));
    }
    let expected = env::var(digest_key)
        .map_err(|_| invalid(format!("{digest_key} is required for {path_key}")))?;
    if !valid_raw_sha256(&expected) {
        return Err(invalid(format!(
            "{digest_key} must be lowercase raw SHA-256"
        )));
    }
    verify_tool_binding_guard(kind, &path, &expected)
}

#[cfg(test)]
pub fn verified_tool_executable(kind: &str) -> io::Result<PathBuf> {
    Ok(verified_tool(kind)?.original_path().to_path_buf())
}

#[cfg(test)]
fn verify_tool_binding(kind: &str, path: &Path, expected: &str) -> io::Result<PathBuf> {
    Ok(verify_tool_binding_guard(kind, path, expected)?
        .original_path()
        .to_path_buf())
}

fn verify_tool_binding_guard(kind: &str, path: &Path, expected: &str) -> io::Result<VerifiedTool> {
    let (_, digest_key) = binding(kind);
    if digest_key.is_empty() {
        return Err(invalid(format!("unknown packaging tool: {kind}")));
    }
    if !path.is_absolute() {
        return Err(invalid(format!("{kind} executable path must be absolute")));
    }
    if !valid_raw_sha256(expected) {
        return Err(invalid(format!(
            "{digest_key} must be lowercase raw SHA-256"
        )));
    }
    #[cfg(target_os = "macos")]
    if kind == "git" {
        verify_macos_git_path_authority(path)?;
    }
    #[allow(unused_mut)]
    let (mut file, metadata, actual) = open_hashed_regular_executable(path)?;
    if actual != expected {
        return Err(invalid(format!(
            "{kind} executable digest mismatch: expected {expected}, got {actual}"
        )));
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    let (execution_path, execution_owner, execution_metadata, owns_execution_copy) =
        sealed_executable_copy(&mut file, path, expected)?;
    #[cfg(target_os = "macos")]
    let (
        execution_path,
        execution_owner,
        execution_metadata,
        owns_execution_copy,
        macos_cdhash,
        python_installation,
    ) = {
        let cdhash = macos_code_identity(path)?;
        let installation = if kind == "python" {
            Some(macos_python_installation_lease(path)?)
        } else {
            None
        };
        (
            path.to_path_buf(),
            None,
            metadata.clone(),
            false,
            cdhash,
            installation,
        )
    };
    #[cfg(windows)]
    let locked_file = {
        drop(file);
        locked_windows_executable(path, expected)?
    };
    #[cfg(all(not(unix), not(windows)))]
    let locked_file = file;
    Ok(VerifiedTool {
        kind: kind.to_owned(),
        original_path: path.to_path_buf(),
        identity: file_identity(&metadata),
        #[cfg(unix)]
        execution_path,
        #[cfg(unix)]
        execution_owner,
        #[cfg(unix)]
        execution_identity: file_identity(&execution_metadata),
        #[cfg(unix)]
        owns_execution_copy,
        #[cfg(target_os = "macos")]
        macos_cdhash,
        #[cfg(target_os = "macos")]
        python_installation,
        lock: {
            #[cfg(all(unix, not(target_os = "macos")))]
            {
                File::open(&execution_path)?
            }
            #[cfg(target_os = "macos")]
            {
                file
            }
            #[cfg(not(unix))]
            {
                locked_file
            }
        },
    })
}

#[cfg(target_os = "macos")]
fn verify_macos_git_path_authority(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    const FORMAL_GIT: &str = "/Library/Developer/CommandLineTools/usr/bin/git";
    if path != Path::new(FORMAL_GIT) || path.canonicalize()? != path {
        return Err(invalid(format!(
            "formal macOS Git must be the fixed Command Line Tools executable: {FORMAL_GIT}"
        )));
    }
    for component in path.ancestors() {
        let metadata = fs::symlink_metadata(component)?;
        if metadata.file_type().is_symlink()
            || metadata.uid() != 0
            || metadata.permissions().mode() & 0o022 != 0
        {
            return Err(invalid(format!(
                "formal macOS Git contains writable/non-root authority: {}",
                component.display()
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(target_os = "macos")]
    #[test]
    fn darwin_security_constants_and_adhoc_policy_are_fixed() {
        assert_eq!(SEC_CS_NO_NETWORK_ACCESS, 1 << 29);
        assert_eq!(SEC_CS_STRICT_VALIDATE, 1 << 4);
        assert_eq!(SEC_CS_CHECK_ALL_ARCHITECTURES, 1);
        assert_eq!(SEC_CODE_SIGNATURE_ADHOC, 0x2);
        assert!(!accepted_macos_signature_flags(SEC_CODE_SIGNATURE_ADHOC));
        assert!(accepted_macos_signature_flags(0));
    }
    use std::time::{SystemTime, UNIX_EPOCH};

    struct TestFile {
        path: PathBuf,
    }

    impl TestFile {
        fn new(label: &str, payload: &[u8]) -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock should be valid")
                .as_nanos();
            let root = env::temp_dir()
                .canonicalize()
                .expect("system temporary directory should canonicalize")
                .join(format!(
                    "tobkiri-packaging-tool-{label}-{}-{nonce}",
                    std::process::id()
                ));
            fs::create_dir_all(&root).expect("tool fixture root should be creatable");
            let path = root.join("tool");
            fs::write(&path, payload).expect("tool fixture should be writable");
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;

                fs::set_permissions(&path, fs::Permissions::from_mode(0o555))
                    .expect("tool fixture should be executable");
            }
            Self { path }
        }

        fn digest(&self) -> String {
            format!(
                "{:x}",
                Sha256::digest(fs::read(&self.path).expect("tool fixture should be readable"))
            )
        }
    }

    impl Drop for TestFile {
        fn drop(&mut self) {
            if let Some(root) = self.path.parent() {
                let _ = fs::remove_dir_all(root);
            }
        }
    }

    #[test]
    fn missing_and_nonabsolute_bindings_fail_before_any_spawn() {
        let missing = verify_tool_binding("python", Path::new("/missing"), "")
            .expect_err("missing digest input must fail");
        assert!(missing.to_string().contains(PYTHON_SHA256_ENV));

        let relative = verify_tool_binding("python", Path::new("python"), &"0".repeat(64))
            .expect_err("relative input must fail");
        assert!(relative.to_string().contains("absolute"));
    }

    #[test]
    fn fake_path_tools_are_never_selected_or_executed() {
        let fake = TestFile::new(
            "fake-path",
            b"#!/bin/sh\nprintf executed > \"$TOBKIRI_FAKE_MARKER\"\n",
        );
        let marker = fake.path.with_file_name("marker");
        let error = verify_tool_binding("python", &fake.path, &"0".repeat(64))
            .expect_err("fake tool digest must fail");
        assert!(error.to_string().contains("digest mismatch"));
        assert!(!marker.exists(), "untrusted PATH executable was spawned");
    }

    #[test]
    fn mismatch_and_tamper_fail_closed_after_exact_binding() {
        let tool = TestFile::new("tamper", b"trusted fixture executable");
        let mismatch = verify_tool_binding("python", &tool.path, &"0".repeat(64))
            .expect_err("digest mismatch must fail");
        assert!(mismatch.to_string().contains("digest mismatch"));

        let expected = tool.digest();
        assert_eq!(
            verify_tool_binding("python", &tool.path, &expected)
                .expect("exact tool identity should pass"),
            tool.path
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o755))
                .expect("fixture should become writable");
        }
        fs::write(&tool.path, b"tampered fixture executable")
            .expect("fixture tamper should be writable");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o555))
                .expect("fixture should become immutable again");
        }
        let tampered =
            verify_tool_binding("python", &tool.path, &expected).expect_err("tamper must fail");
        assert!(tampered.to_string().contains("digest mismatch"));
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    #[test]
    fn replaced_python_and_git_paths_never_execute_replacement() {
        use std::os::unix::fs::PermissionsExt;

        for kind in ["python", "git"] {
            let tool = TestFile::new(
                &format!("{kind}-replace"),
                b"#!/bin/sh\nprintf trusted > \"$TOBKIRI_TRUSTED_MARKER\"\n",
            );
            let trusted_marker = tool.path.with_file_name(format!("{kind}-trusted"));
            let evil_marker = tool.path.with_file_name(format!("{kind}-evil"));
            let guard = verify_tool_binding_guard(kind, &tool.path, &tool.digest()).unwrap();
            fs::remove_file(&tool.path).unwrap();
            fs::write(
                &tool.path,
                b"#!/bin/sh\nprintf evil > \"$TOBKIRI_EVIL_MARKER\"\n",
            )
            .unwrap();
            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o555)).unwrap();
            let status = guard
                .command()
                .unwrap()
                .env("TOBKIRI_TRUSTED_MARKER", &trusted_marker)
                .env("TOBKIRI_EVIL_MARKER", &evil_marker)
                .status()
                .unwrap();
            assert!(status.success());
            assert!(trusted_marker.exists(), "trusted {kind} bytes must execute");
            assert!(
                !evil_marker.exists(),
                "replacement {kind} must never execute"
            );
        }
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    #[test]
    fn in_place_overwrite_after_binding_never_executes_modified_original() {
        use std::os::unix::fs::PermissionsExt;
        let tool = TestFile::new(
            "in-place",
            b"#!/bin/sh\nprintf trusted > \"$TOBKIRI_TRUSTED_MARKER\"\n",
        );
        let trusted = tool.path.with_file_name("in-place-trusted");
        let evil = tool.path.with_file_name("in-place-evil");
        let guard = verify_tool_binding_guard("python", &tool.path, &tool.digest()).unwrap();
        fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o755)).unwrap();
        fs::write(
            &tool.path,
            b"#!/bin/sh\nprintf evil > \"$TOBKIRI_EVIL_MARKER\"\n",
        )
        .unwrap();
        let status = guard
            .command()
            .unwrap()
            .env("TOBKIRI_TRUSTED_MARKER", &trusted)
            .env("TOBKIRI_EVIL_MARKER", &evil)
            .status()
            .unwrap();
        assert!(status.success());
        assert!(trusted.exists());
        assert!(!evil.exists());
    }

    #[test]
    fn bound_real_python_and_git_remain_executable() {
        for (kind, argument) in [("python", "--version"), ("git", "--version")] {
            let tool = verified_tool(kind).unwrap();
            let output = tool.command().unwrap().arg(argument).output().unwrap();
            assert!(
                output.status.success(),
                "sealed {kind} must remain compatible"
            );
        }
    }
}
