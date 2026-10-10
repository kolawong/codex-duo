import SwiftUI
import AppKit

/// The menu bar item and its floating panel. The panel owns its shape (one radius for
/// the material, the clip, the hairline and the shadow), so content never shows square
/// corners or bands, whatever the system's own menu bar window looks like.
@MainActor
final class StatusPanelController: NSObject, NSWindowDelegate {
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let panel: FloatingPanel
    private let host: AutosizingHostingView<AnyView>
    private var topLeft: NSPoint?
    private var glyph: GlyphAnimator?

    init(store: SettingsStore) {
        host = AutosizingHostingView(rootView: AnyView(SettingsView(store: store)))
        panel = FloatingPanel(content: host)
        super.init()
        panel.delegate = self
        panel.onCancel = { [weak self] in self?.close() }
        host.onResize = { [weak self] in self?.fitToContent() }
        if let button = item.button {
            glyph = GlyphAnimator(button: button)
            button.setAccessibilityLabel("\(Brand.name) 设置")
            button.target = self
            button.action = #selector(clicked)
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
    }

    @objc private func clicked() {
        if NSApp.currentEvent?.type == .rightMouseUp || NSApp.currentEvent?.modifierFlags.contains(.control) == true {
            showContextMenu()
        } else {
            panel.isVisible ? close() : show()
        }
    }

    private func showContextMenu() {
        close()
        let menu = NSMenu()
        let open = NSMenuItem(title: "打开设置窗口", action: #selector(openWindow), keyEquivalent: "")
        open.target = self
        menu.addItem(open)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "退出 \(Brand.name)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)
        item.menu = menu
        item.button?.performClick(nil)
        item.menu = nil
    }

    @objc private func openWindow() { StartupDelegate.presentSettings() }

    func show() {
        guard let button = item.button, let buttonWindow = button.window else { return }
        let anchor = buttonWindow.convertToScreen(button.convert(button.bounds, to: nil))
        let size = host.fittingSize
        let visible = (buttonWindow.screen ?? NSScreen.main)?.visibleFrame ?? .zero
        let x = min(max(anchor.midX - size.width / 2, visible.minX + 8), visible.maxX - size.width - 8)
        topLeft = NSPoint(x: x, y: anchor.minY - 6)
        fitToContent()
        item.button?.highlight(true)
        glyph?.play(open: true)
        panel.makeKeyAndOrderFront(nil)
    }

    func close() {
        guard panel.isVisible else { return }
        panel.orderOut(nil)
        item.button?.highlight(false)
        glyph?.play(open: false)
    }

    private func fitToContent() {
        guard let topLeft else { return }
        let size = host.fittingSize
        panel.setFrame(NSRect(x: topLeft.x, y: topLeft.y - size.height, width: size.width, height: size.height),
                       display: true)
        panel.invalidateShadow()
    }

    func windowDidResignKey(_ notification: Notification) {
        // Let a sheet (the discard confirmation) attach before deciding the panel lost focus.
        DispatchQueue.main.async { [weak self] in
            guard let self, self.panel.attachedSheet == nil, !self.panel.isKeyWindow else { return }
            self.close()
        }
    }
}

final class FloatingPanel: NSPanel {
    init(content: NSView) {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 400, height: 500),
                   styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: true)
        isFloatingPanel = true
        level = .statusBar
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        isReleasedWhenClosed = false
        hidesOnDeactivate = false
        animationBehavior = .utilityWindow
        setAccessibilityIdentifier("tandem-status-panel")

        let material = NSVisualEffectView()
        material.material = .popover
        material.blendingMode = .behindWindow
        material.state = .active
        material.wantsLayer = true
        material.layer?.cornerRadius = Theme.panelRadius
        material.layer?.cornerCurve = .continuous
        material.layer?.masksToBounds = true
        material.maskImage = Self.mask(radius: Theme.panelRadius)
        content.translatesAutoresizingMaskIntoConstraints = false
        material.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: material.leadingAnchor),
            content.trailingAnchor.constraint(equalTo: material.trailingAnchor),
            content.topAnchor.constraint(equalTo: material.topAnchor),
            content.bottomAnchor.constraint(equalTo: material.bottomAnchor)
        ])
        contentView = material
    }

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    var onCancel: (() -> Void)?
    override func cancelOperation(_ sender: Any?) { onCancel?() ?? orderOut(nil) }

    /// A stretchable rounded mask, so the material keeps its corners at any size.
    private static func mask(radius: CGFloat) -> NSImage {
        let edge = radius * 2 + 1
        let image = NSImage(size: NSSize(width: edge, height: edge), flipped: false) { rect in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
            return true
        }
        image.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
        image.resizingMode = .stretch
        return image
    }
}

/// Reports SwiftUI size changes so the borderless panel can follow its content.
final class AutosizingHostingView<Content: View>: NSHostingView<Content> {
    var onResize: (() -> Void)?

    required init(rootView: Content) {
        super.init(rootView: rootView)
        sizingOptions = [.intrinsicContentSize]
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func invalidateIntrinsicContentSize() {
        super.invalidateIntrinsicContentSize()
        DispatchQueue.main.async { [weak self] in self?.onResize?() }
    }
}
