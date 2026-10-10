import SwiftUI
import AppKit

@main
struct FusionMenuApp: App {
    @NSApplicationDelegateAdaptor(StartupDelegate.self) private var startupDelegate
    @State private var store: SettingsStore

    init() {
        let arguments = CommandLine.arguments
        let explicitRoot: String? = arguments.firstIndex(of: "--project-root").flatMap { index in
            arguments.indices.contains(index + 1) ? arguments[index + 1] : "（缺少项目绝对路径）"
        }
        let configuredRoot = Bundle.main.object(forInfoDictionaryKey: "FusionProjectRoot") as? String
        // swift run is explicitly scoped to the source checkout, never the shell's cwd.
        let sourceRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path
        let root = explicitRoot ?? ProjectHistory().paths.first ?? configuredRoot ?? sourceRoot
        let canonicalRoot = root.hasPrefix("/") ? URL(fileURLWithPath: root).resolvingSymlinksInPath().path : root
        let sharedStore = SettingsStore(projectRoot: canonicalRoot)
        _store = State(initialValue: sharedStore)
        // Configure launch before SwiftUI installs its delegate adaptor. Do not mutate
        // the adaptor's wrapped instance while the App is still being initialized.
        StartupDelegate.store = sharedStore
        StartupDelegate.showSettings = arguments.contains("--show-settings")
        NSApplication.shared.setActivationPolicy(.accessory)
    }

    var body: some Scene {
        // The menu bar item and its panel are AppKit (StatusPanelController); an App
        // still needs one scene, and a Settings scene shows nothing on its own.
        Settings { EmptyView() }
    }
}

@MainActor
final class StartupDelegate: NSObject, NSApplicationDelegate {
    static var store: SettingsStore?
    static var showSettings = false
    private static var window: NSWindow?
    private static var statusPanel: StatusPanelController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let store = Self.store { Self.statusPanel = StatusPanelController(store: store) }
        guard Self.showSettings else { return }
        // Defer until SwiftUI and AppKit finish installing their launch state.
        DispatchQueue.main.async { Self.presentSettings() }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        Self.presentSettings()
        return true
    }

    static func presentSettings() {
        if let window {
            window.makeKeyAndOrderFront(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
            return
        }
        guard let store else { return }
        // macOS 14 SceneBuilder cannot conditionally add a scene at runtime.
        // This optional automation window hosts the same SwiftUI view and shared draft.
        let controller = NSHostingController(rootView: SettingsView(store: store, isWindow: true))
        controller.sizingOptions = .preferredContentSize
        // The header shares the title bar row with the traffic lights, so the title
        // bar must not inset the content or add to the window's height.
        controller.safeAreaRegions = []
        let window = NSWindow(contentViewController: controller)
        window.styleMask = [.titled, .closable, .fullSizeContentView]
        // An empty unified toolbar gives a 52pt title bar, so the traffic lights sit
        // level with the header instead of above it.
        window.toolbar = NSToolbar()
        window.toolbarStyle = .unified
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.title = "\(Brand.name) 设置"
        window.setAccessibilityIdentifier("fusion-settings-window")
        window.isReleasedWhenClosed = false
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        Self.window = window
    }
}
