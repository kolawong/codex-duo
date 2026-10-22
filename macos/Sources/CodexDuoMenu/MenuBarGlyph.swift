import AppKit

/// The menu bar mark, drawn in code so it stays crisp at 18pt on any display:
/// two thin overlapping rings. `spread` moves them apart (0 = rest); `fill` lights
/// the overlap, which marks the panel as open.
enum MenuBarGlyph {
    static let size = NSSize(width: 18, height: 18)
    private static let radius: CGFloat = 4.95
    private static let stroke: CGFloat = 1.5
    private static let restDistance: CGFloat = 5.6

    static func image(spread: CGFloat = 0, fill: CGFloat = 0) -> NSImage {
        let image = NSImage(size: size, flipped: false) { _ in
            guard let context = NSGraphicsContext.current?.cgContext else { return false }
            draw(in: context, distance: restDistance + spread, fill: min(max(fill, 0), 1))
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = "\(Brand.name)"
        return image
    }

    private static func draw(in context: CGContext, distance: CGFloat, fill: CGFloat) {
        let mid = size.width / 2
        // The lens runs to the middle of both strokes, so no seam shows where they meet.
        let left = CGPoint(x: mid - distance / 2, y: size.height / 2)
        let right = CGPoint(x: mid + distance / 2, y: size.height / 2)
        func circle(_ center: CGPoint, _ r: CGFloat) -> CGRect {
            CGRect(x: center.x - r, y: center.y - r, width: r * 2, height: r * 2)
        }
        context.setLineWidth(stroke)
        context.setStrokeColor(NSColor.black.cgColor)

        if fill > 0 {
            context.saveGState()
            context.addEllipse(in: circle(left, radius))
            context.clip()
            context.setFillColor(NSColor.black.withAlphaComponent(fill).cgColor)
            context.fillEllipse(in: circle(right, radius))
            context.restoreGState()
        }

        context.strokeEllipse(in: circle(left, radius))
        context.strokeEllipse(in: circle(right, radius))
    }
}

/// Plays the mark's open and close motion on the status item button.
@MainActor
final class GlyphAnimator {
    private weak var button: NSStatusBarButton?
    private var timer: Timer?
    private var start = Date()
    private var opening = true

    init(button: NSStatusBarButton) {
        self.button = button
        button.image = MenuBarGlyph.image()
    }

    /// Opening: the rings part, then snap together and the overlap lights.
    /// Closing: the light fades and the rings settle.
    func play(open: Bool) {
        opening = open
        start = Date()
        timer?.invalidate()
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            button?.image = MenuBarGlyph.image(fill: open ? 1 : 0)
            return
        }
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    private func tick() {
        let duration = opening ? 0.52 : 0.24
        let t = min(Date().timeIntervalSince(start) / duration, 1)
        let spread: CGFloat
        let fill: CGFloat
        if opening {
            // apart (to +1.2, the most the 18pt frame allows), snap in past rest (to -0.8), settle
            spread = t < 0.3 ? 1.2 * ease(t / 0.3)
                : t < 0.62 ? 1.2 - 2.0 * ease((t - 0.3) / 0.32)
                : -0.8 * (1 - ease((t - 0.62) / 0.38))
            fill = t < 0.45 ? 0 : ease((t - 0.45) / 0.55)
        } else {
            spread = -0.6 * sin(.pi * t)
            fill = 1 - ease(t)
        }
        button?.image = MenuBarGlyph.image(spread: spread, fill: fill)
        if t >= 1 {
            timer?.invalidate()
            timer = nil
            button?.image = MenuBarGlyph.image(fill: opening ? 1 : 0)
        }
    }

    private func ease(_ x: Double) -> CGFloat {
        let x = min(max(x, 0), 1)
        return CGFloat(1 - pow(1 - x, 3))
    }
}
