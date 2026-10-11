import XCTest
import SwiftUI
import AppKit
@testable import CodexDuoMenu

final class HeaderLayoutTests: XCTestCase {
    @MainActor private func render(_ view: SettingsHeader, width: CGFloat,
                                  name: String? = nil) throws -> (NSHostingView<AnyView>, NSBitmapImageRep) {
        let host = NSHostingView(rootView: AnyView(view.frame(width: width).background(Theme.bg)
            .environment(\.colorScheme, .dark)))
        host.appearance = NSAppearance(named: .darkAqua)
        host.frame = NSRect(x: 0, y: 0, width: width, height: host.fittingSize.height)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        let bitmap = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        if let name, let output = ProcessInfo.processInfo.environment["CODEX_DUO_HEADER_RENDER_DIR"] {
            try bitmap.representation(using: .png, properties: [:])?.write(to:
                URL(fileURLWithPath: output).appendingPathComponent(name + ".png"))
        }
        return (host, bitmap)
    }

    private func paintedPixels(_ bitmap: NSBitmapImageRep, width: CGFloat, from: CGFloat, to: CGFloat) -> Int {
        let scale = CGFloat(bitmap.pixelsWide) / width
        var count = 0
        for x in Int((from * scale).rounded())..<Int((to * scale).rounded()) {
            for y in 0..<bitmap.pixelsHigh {
                guard let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
                if max(abs(c.redComponent - 26/255), abs(c.greenComponent - 25/255),
                       abs(c.blueComponent - 23/255)) > 0.16 { count += 1 }
            }
        }
        return count
    }

    @MainActor func testNarrowWideAndLongStatusRenderTwoSeparateActions() throws {
        for width: CGFloat in [320, 400, 520] {
            for text in ["已保存", "读取失败：配置已在外部更新，请重新读取并确认当前项目设置"] {
                let (host, bitmap) = try render(SettingsHeader(statusText: text, tone: .green, refresh: {}, openWindow: {}),
                    width: width, name: "after-\(Int(width))-\(text == "已保存" ? "saved" : "long")")
                let refresh = paintedPixels(bitmap, width: width, from: width - 71, to: width - 45)
                let gap = paintedPixels(bitmap, width: width, from: width - 45, to: width - 36)
                let open = paintedPixels(bitmap, width: width, from: width - 36, to: width - 10)
                print("OFFSCREEN_HEADER", width, text, "height", host.frame.height,
                      "refresh pixels", refresh, "gap pixels", gap, "open pixels", open)
                XCTAssertGreaterThan(refresh, 20); XCTAssertGreaterThan(open, 20)
                XCTAssertEqual(gap, 0, "title, status and glyphs cannot paint over the action gap")
                XCTAssertEqual(host.fittingSize.width, width)
            }
        }
    }

    @MainActor func testIndependentActionRoutingAndBusyRefreshOnly() {
        var refreshes = 0, openings = 0
        for busy in [false, true, false] {
            let header = SettingsHeader(statusText: "已保存", tone: .green, isBusy: busy,
                refresh: { refreshes += 1 }, openWindow: { openings += 1 })
            header.perform(.refresh); header.perform(.openWindow)
        }
        XCTAssertEqual(refreshes, 2); XCTAssertEqual(openings, 3)
    }

    @MainActor func testWindowHeaderHasOnlyRefreshAndPreservesInset() throws {
        for width: CGFloat in [320, 400, 520] {
            let header = SettingsHeader(isWindow: true, statusText: "有冲突", tone: .red,
                refresh: {}, openWindow: { XCTFail("independent window cannot open another window") })
            header.perform(.openWindow)
            let (_, bitmap) = try render(header, width: width)
            XCTAssertGreaterThan(paintedPixels(bitmap, width: width, from: width - 36, to: width - 10), 20)
            XCTAssertEqual(paintedPixels(bitmap, width: width, from: 0, to: 88), 0)
        }
    }

    @MainActor func testBusyAnimationKeepsBothPaintAreas() throws {
        let (_, bitmap) = try render(SettingsHeader(statusText: "读取中", tone: .neutral, isBusy: true,
            refresh: {}, openWindow: {}), width: 400)
        XCTAssertGreaterThan(paintedPixels(bitmap, width: 400, from: 329, to: 355), 20)
        XCTAssertGreaterThan(paintedPixels(bitmap, width: 400, from: 364, to: 390), 20)
        XCTAssertEqual(paintedPixels(bitmap, width: 400, from: 355, to: 364), 0)
    }
}
