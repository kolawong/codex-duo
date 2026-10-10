import AppKit

enum Brand {
    static let name = "Codex Duo"
    static let tagline = "一个规划，一个执行"

    static let appIcon: NSImage? = image("AppIcon")

    // Packaged builds copy Brand/ into Contents/Resources; `swift run` and tests use the SwiftPM bundle.
    private static func image(_ name: String) -> NSImage? {
        let packaged = Bundle.main.resourceURL?.appendingPathComponent("Brand/\(name).svg")
        let url = packaged.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
            ?? Bundle.module.url(forResource: name, withExtension: "svg", subdirectory: "Brand")
        return url.flatMap(NSImage.init(contentsOf:))
    }
}
