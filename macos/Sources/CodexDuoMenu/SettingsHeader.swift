import SwiftUI

/// Header actions keep their own space when the title or status needs more room.
struct SettingsHeader: View {
    var isWindow = false
    let statusText: String
    let tone: Tone
    var isBusy = false
    let refresh: () -> Void
    let openWindow: () -> Void

    enum Action { case refresh, openWindow }
    func perform(_ action: Action) {
        switch action {
        case .refresh: if !isBusy { refresh() }
        case .openWindow: if !isWindow { openWindow() }
        }
    }

    private var brand: some View {
        HStack(spacing: 9) {
            LogoMark(size: isWindow ? 22 : 26)
            VStack(alignment: .leading, spacing: 0) {
                Text(Brand.name).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Theme.fg)
                if !isWindow {
                    Text(Brand.tagline).font(.system(size: 10.5)).foregroundStyle(Theme.muted)
                }
            }.lineLimit(1)
        }
    }

    private var status: some View {
        StatusPill(text: statusText, tone: tone)
            .lineLimit(1).truncationMode(.tail)
            .accessibilityLabel("状态：\(statusText)")
    }

    var body: some View {
        HStack(spacing: 9) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 9) { brand; status }
                VStack(alignment: .leading, spacing: 4) { brand; status }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 9) {
                IconButton(systemImage: "arrow.clockwise", help: "刷新（保留未保存的修改）",
                           spinning: isBusy, action: { perform(.refresh) })
                    .disabled(isBusy)
                    .accessibilityIdentifier("header-refresh")
                if !isWindow {
                    IconButton(systemImage: "macwindow", help: "在独立窗口中打开", action: { perform(.openWindow) })
                        .accessibilityIdentifier("header-open-window")
                }
            }
            .fixedSize(horizontal: true, vertical: true)
        }
        // Clear the independent window's traffic lights; the floating panel has none.
        .padding(.leading, isWindow ? 88 : 14).padding(.trailing, 10).padding(.vertical, 10)
        .frame(minHeight: isWindow ? 52 : 50)
    }
}
