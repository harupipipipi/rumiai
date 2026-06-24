import AVFoundation
import Flutter
import Security
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let secureStorage = RumiKeychainStorage()
  private var pendingQrScanResult: FlutterResult?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    registerSecureStorageChannel()
    registerPreferencesChannel()
    registerUrlLauncherChannel()
    registerQrScannerChannel()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func registerSecureStorageChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "ai.rumi.remote/secure_storage",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { [secureStorage] call, result in
      guard let args = call.arguments as? [String: Any],
            let key = args["key"] as? String,
            !key.isEmpty else {
        result(FlutterError(code: "invalid_args", message: "Missing key", details: nil))
        return
      }

      switch call.method {
      case "read":
        do {
          result(try secureStorage.read(key: key))
        } catch {
          result(FlutterError(code: "read_failed", message: error.localizedDescription, details: nil))
        }
      case "write":
        guard let value = args["value"] as? String else {
          result(FlutterError(code: "invalid_args", message: "Missing value", details: nil))
          return
        }
        do {
          try secureStorage.write(key: key, value: value)
          result(nil)
        } catch {
          result(FlutterError(code: "write_failed", message: error.localizedDescription, details: nil))
        }
      case "delete":
        do {
          try secureStorage.delete(key: key)
          result(nil)
        } catch {
          result(FlutterError(code: "delete_failed", message: error.localizedDescription, details: nil))
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func registerPreferencesChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "ai.rumi.remote/preferences",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard let args = call.arguments as? [String: Any],
            let key = args["key"] as? String,
            !key.isEmpty else {
        result(FlutterError(code: "invalid_args", message: "Missing key", details: nil))
        return
      }

      switch call.method {
      case "read":
        result(UserDefaults.standard.string(forKey: key))
      case "write":
        guard let value = args["value"] as? String else {
          result(FlutterError(code: "invalid_args", message: "Missing value", details: nil))
          return
        }
        UserDefaults.standard.set(value, forKey: key)
        result(nil)
      case "delete":
        UserDefaults.standard.removeObject(forKey: key)
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func registerUrlLauncherChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "ai.rumi.remote/url_launcher",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "open" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let args = call.arguments as? [String: Any],
            let raw = args["url"] as? String,
            let url = URL(string: raw) else {
        result(false)
        return
      }
      UIApplication.shared.open(url, options: [:]) { ok in
        result(ok)
      }
    }
  }

  private func registerQrScannerChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "ai.rumi.remote/qr_scanner",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(false)
        return
      }
      guard call.method == "scan" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard pendingQrScanResult == nil else {
        result(FlutterError(code: "scan_in_progress", message: "QR scanner is already open", details: nil))
        return
      }
      pendingQrScanResult = result
      let scanner = RumiQrScannerViewController { [weak self] value in
        guard let self else { return }
        let pending = pendingQrScanResult
        pendingQrScanResult = nil
        pending?(value)
      }
      scanner.modalPresentationStyle = .fullScreen
      controller.present(scanner, animated: true)
    }
  }
}

private final class RumiKeychainStorage {
  private let service = "ai.rumi.remote.secure_storage"

  func read(key: String) throws -> String? {
    try readValue(query: baseQuery(key: key)) ?? readValue(query: legacyQuery(key: key))
  }

  private func readValue(query base: [CFString: Any]) throws -> String? {
    var query = base
    query[kSecReturnData] = true
    query[kSecMatchLimit] = kSecMatchLimitOne

    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    if status == errSecItemNotFound {
      return nil
    }
    guard status == errSecSuccess else {
      throw keychainError(status)
    }
    guard let data = item as? Data else {
      return nil
    }
    return String(data: data, encoding: .utf8)
  }

  func write(key: String, value: String) throws {
    let data = Data(value.utf8)
    let query = baseQuery(key: key)
    let update: [CFString: Any] = [
      kSecValueData: data,
    ]
    let updateStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
    if updateStatus == errSecSuccess {
      return
    }
    guard updateStatus == errSecItemNotFound else {
      throw keychainError(updateStatus)
    }

    var addQuery = query
    addQuery[kSecValueData] = data
    addQuery[kSecAttrAccessible] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
    guard addStatus == errSecSuccess else {
      throw keychainError(addStatus)
    }
  }

  func delete(key: String) throws {
    let status = SecItemDelete(baseQuery(key: key) as CFDictionary)
    if status == errSecSuccess || status == errSecItemNotFound {
      return
    }
    throw keychainError(status)
  }

  private func baseQuery(key: String) -> [CFString: Any] {
    [
      kSecClass: kSecClassGenericPassword,
      kSecAttrService: service,
      kSecAttrAccount: key,
    ]
  }

  private func legacyQuery(key: String) -> [CFString: Any] {
    [
      kSecClass: kSecClassGenericPassword,
      kSecAttrAccount: key,
    ]
  }

  private func keychainError(_ status: OSStatus) -> NSError {
    let message = SecCopyErrorMessageString(status, nil) as String? ?? "Keychain error \(status)"
    return NSError(
      domain: "ai.rumi.remote.keychain",
      code: Int(status),
      userInfo: [NSLocalizedDescriptionKey: message]
    )
  }
}

private final class RumiQrScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
  private let queue = DispatchQueue(label: "ai.rumi.remote.qr_scanner")
  private let completion: (String?) -> Void
  private var session: AVCaptureSession?
  private var previewLayer: AVCaptureVideoPreviewLayer?
  private var position: AVCaptureDevice.Position = .back
  private var lastValue: String?
  private var finished = false

  init(completion: @escaping (String?) -> Void) {
    self.completion = completion
    super.init(nibName: nil, bundle: nil)
  }

  required init?(coder: NSCoder) {
    fatalError("init(coder:) has not been implemented")
  }

  override func viewDidLoad() {
    super.viewDidLoad()
    view.backgroundColor = .black
    buildOverlay()
    start()
  }

  override func viewDidLayoutSubviews() {
    super.viewDidLayoutSubviews()
    previewLayer?.frame = view.bounds
  }

  override func viewWillDisappear(_ animated: Bool) {
    super.viewWillDisappear(animated)
    stop()
  }

  deinit {
    stop()
    if !finished {
      completion(nil)
    }
  }

  private func start() {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
      configureAndStart()
    case .notDetermined:
      AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
        if granted {
          self?.configureAndStart()
        } else {
          DispatchQueue.main.async {
            self?.finish(nil)
          }
        }
      }
    default:
      finish(nil)
    }
  }

  private func stop() {
    let currentSession = session
    session = nil
    queue.async {
      currentSession?.stopRunning()
    }
  }

  @objc private func switchCamera() {
    position = position == .back ? .front : .back
    stop()
    configureAndStart()
  }

  @objc private func toggleTorch() {
    guard let device = currentVideoDevice(), device.hasTorch else {
      return
    }
    do {
      try device.lockForConfiguration()
      device.torchMode = device.torchMode == .on ? .off : .on
      device.unlockForConfiguration()
    } catch {
    }
  }

  @objc private func cancel() {
    finish(nil)
  }

  private func configureAndStart() {
    queue.async { [weak self] in
      guard let self else { return }
      let nextSession = AVCaptureSession()
      nextSession.beginConfiguration()
      nextSession.sessionPreset = .high

      guard let device = camera(position: position),
            let input = try? AVCaptureDeviceInput(device: device),
            nextSession.canAddInput(input) else {
        nextSession.commitConfiguration()
        return
      }
      nextSession.addInput(input)

      let output = AVCaptureMetadataOutput()
      guard nextSession.canAddOutput(output) else {
        nextSession.commitConfiguration()
        return
      }
      nextSession.addOutput(output)
      output.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)
      output.metadataObjectTypes = [.qr]
      nextSession.commitConfiguration()

      session = nextSession
      DispatchQueue.main.async { [weak self] in
        guard let self else { return }
        let previewLayer = AVCaptureVideoPreviewLayer(session: nextSession)
        previewLayer.videoGravity = .resizeAspectFill
        previewLayer.frame = view.bounds
        self.previewLayer?.removeFromSuperlayer()
        self.previewLayer = previewLayer
        view.layer.insertSublayer(previewLayer, at: 0)
      }
      nextSession.startRunning()
    }
  }

  private func currentVideoDevice() -> AVCaptureDevice? {
    session?.inputs
      .compactMap { $0 as? AVCaptureDeviceInput }
      .first { $0.device.hasMediaType(.video) }?
      .device
  }

  private func camera(position: AVCaptureDevice.Position) -> AVCaptureDevice? {
    AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position)
      ?? AVCaptureDevice.default(for: .video)
  }

  func metadataOutput(
    _ output: AVCaptureMetadataOutput,
    didOutput metadataObjects: [AVMetadataObject],
    from connection: AVCaptureConnection
  ) {
    guard let value = metadataObjects
      .compactMap({ $0 as? AVMetadataMachineReadableCodeObject })
      .first(where: { $0.type == .qr })?
      .stringValue?
      .trimmingCharacters(in: .whitespacesAndNewlines),
      !value.isEmpty,
      value != lastValue else {
      return
    }
    lastValue = value
    finish(value)
  }

  private func finish(_ value: String?) {
    if finished {
      return
    }
    finished = true
    stop()
    dismiss(animated: true) { [completion] in
      completion(value)
    }
  }

  private func buildOverlay() {
    let close = UIButton(type: .system)
    close.translatesAutoresizingMaskIntoConstraints = false
    close.setTitle("閉じる", for: .normal)
    close.tintColor = .white
    close.backgroundColor = UIColor.black.withAlphaComponent(0.45)
    close.layer.cornerRadius = 18
    close.contentEdgeInsets = UIEdgeInsets(top: 8, left: 14, bottom: 8, right: 14)
    close.addTarget(self, action: #selector(cancel), for: .touchUpInside)
    view.addSubview(close)

    let guide = UIView()
    guide.translatesAutoresizingMaskIntoConstraints = false
    guide.layer.borderColor = UIColor.white.cgColor
    guide.layer.borderWidth = 3
    guide.layer.cornerRadius = 18
    view.addSubview(guide)

    let hint = UILabel()
    hint.translatesAutoresizingMaskIntoConstraints = false
    hint.text = "QRを枠の中に入れてください"
    hint.textColor = .white
    hint.font = .systemFont(ofSize: 15, weight: .semibold)
    hint.textAlignment = .center
    hint.backgroundColor = UIColor.black.withAlphaComponent(0.45)
    hint.layer.cornerRadius = 16
    hint.clipsToBounds = true
    view.addSubview(hint)

    let torch = UIButton(type: .system)
    torch.translatesAutoresizingMaskIntoConstraints = false
    torch.setTitle("ライト", for: .normal)
    torch.tintColor = .white
    torch.backgroundColor = UIColor.black.withAlphaComponent(0.45)
    torch.layer.cornerRadius = 18
    torch.contentEdgeInsets = UIEdgeInsets(top: 8, left: 14, bottom: 8, right: 14)
    torch.addTarget(self, action: #selector(toggleTorch), for: .touchUpInside)
    view.addSubview(torch)

    let camera = UIButton(type: .system)
    camera.translatesAutoresizingMaskIntoConstraints = false
    camera.setTitle("切替", for: .normal)
    camera.tintColor = .white
    camera.backgroundColor = UIColor.black.withAlphaComponent(0.45)
    camera.layer.cornerRadius = 18
    camera.contentEdgeInsets = UIEdgeInsets(top: 8, left: 14, bottom: 8, right: 14)
    camera.addTarget(self, action: #selector(switchCamera), for: .touchUpInside)
    view.addSubview(camera)

    NSLayoutConstraint.activate([
      close.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 16),
      close.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),

      guide.centerXAnchor.constraint(equalTo: view.centerXAnchor),
      guide.centerYAnchor.constraint(equalTo: view.centerYAnchor),
      guide.widthAnchor.constraint(equalToConstant: 250),
      guide.heightAnchor.constraint(equalTo: guide.widthAnchor),

      hint.centerXAnchor.constraint(equalTo: view.centerXAnchor),
      hint.topAnchor.constraint(equalTo: guide.bottomAnchor, constant: 22),
      hint.widthAnchor.constraint(lessThanOrEqualTo: view.widthAnchor, constant: -48),
      hint.heightAnchor.constraint(greaterThanOrEqualToConstant: 40),

      torch.trailingAnchor.constraint(equalTo: view.centerXAnchor, constant: -8),
      torch.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -24),

      camera.leadingAnchor.constraint(equalTo: view.centerXAnchor, constant: 8),
      camera.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -24),
    ])
  }
}
