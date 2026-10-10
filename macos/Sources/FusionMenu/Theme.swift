import SwiftUI
import AppKit

/// "Ink & Ember": warm paper and graphite neutrals, ink for the primary action,
/// and one ember accent used sparingly. Every token resolves per appearance.
enum Theme {
    static let bg = dynamic(0xF3F1ED, 0x1A1917)
    static let card = dynamic(0xFFFFFF, 0x24231F)
    static let card2 = dynamic(0xFAF8F5, 0x201F1C)
    static let line = dynamic(NSColor(hex: 0x3A2E1F).withAlphaComponent(0.08), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.07))
    static let line2 = dynamic(NSColor(hex: 0x3A2E1F).withAlphaComponent(0.06), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.06))
    static let pill = dynamic(0xFFFFFF, 0x2D2B27)
    static let pillHover = dynamic(0xF7F5F1, 0x363430)
    static let pillLine = dynamic(NSColor(hex: 0x3A2E1F).withAlphaComponent(0.13), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.11))
    static let segTrack = dynamic(NSColor(hex: 0xEAE7E1), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.05))
    static let segThumb = dynamic(NSColor(hex: 0xFFFFFF), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.14))
    static let hover = dynamic(NSColor(hex: 0x3A2E1F).withAlphaComponent(0.05), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.07))
    static let fg = dynamic(0x1F1D1A, 0xF2EFE9)
    static let fg2 = dynamic(0x4A4640, 0xBDB8AF)
    static let muted = dynamic(0x8A847A, 0x9A948A)
    static let faint = dynamic(0xA8A297, 0x726D65)
    static let accent = dynamic(0xC2552B, 0xEE8B55)
    static let accentSoft = dynamic(0xF7E9E1, 0x3A2720)
    static let ink = dynamic(0x1F1D1A, 0xF2EFE9)
    static let inkFg = dynamic(0xFAF8F5, 0x1A1917)
    static let green = dynamic(0x3D7A57, 0x8CC9A0)
    static let greenSoft = dynamic(0xE7F0E9, 0x1F2D24)
    static let red = dynamic(0xB4413A, 0xEE8F86)
    static let redSoft = dynamic(0xF8E7E4, 0x3D2321)
    static let amber = dynamic(0x9C6A12, 0xE2B45E)
    static let amberSoft = dynamic(0xF6EEDC, 0x37301E)

    /// One radius family: the panel, the cards inside it, and the controls inside those.
    static let panelRadius: CGFloat = 16
    static let cardRadius: CGFloat = 12
    static let segmentRadius: CGFloat = 9
    static let controlRadius: CGFloat = 8
    static let panelEdge = dynamic(NSColor.black.withAlphaComponent(0.1), NSColor(hex: 0xFFF6E8).withAlphaComponent(0.12))

    static let ease = Animation.timingCurve(0.22, 1, 0.36, 1, duration: 0.32)

    private static func dynamic(_ light: UInt32, _ dark: UInt32) -> Color {
        dynamic(NSColor(hex: light), NSColor(hex: dark))
    }

    private static func dynamic(_ light: NSColor, _ dark: NSColor) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
        })
    }
}

extension NSColor {
    convenience init(hex: UInt32) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}
