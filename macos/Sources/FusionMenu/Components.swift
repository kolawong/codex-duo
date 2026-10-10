import SwiftUI
import AppKit

// MARK: - Surfaces

struct PanelBackground: View {
    var body: some View {
        ZStack {
            VisualEffect(material: .popover)
            Theme.bg.opacity(0.92)
        }
        .ignoresSafeArea()
    }
}

struct VisualEffect: NSViewRepresentable {
    var material: NSVisualEffectView.Material
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = .behindWindow
        view.state = .followsWindowActiveState
        return view
    }
    func updateNSView(_ view: NSVisualEffectView, context: Context) { view.material = material }
}

/// A white card with a hairline ring and a breath of shadow; rows inside it are
/// separated by `CardDivider`.
struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: 0) { content }
            .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous).strokeBorder(Theme.line, lineWidth: 1))
            .shadow(color: .black.opacity(0.04), radius: 1, y: 1)
    }
}

struct CardDivider: View {
    var inset: CGFloat = 12
    var body: some View { Theme.line2.frame(height: 1).padding(.leading, inset) }
}

struct PanelSection<Content: View>: View {
    let title: String
    var trailing: String?
    var footnote: String?
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.system(size: 11.5, weight: .semibold)).foregroundStyle(Theme.muted)
                Spacer()
                if let trailing {
                    Text(trailing).font(.system(size: 11)).foregroundStyle(Theme.faint)
                }
            }
            .padding(.horizontal, 4)
            .accessibilityAddTraits(.isHeader)
            content
            if let footnote {
                Text(footnote).font(.system(size: 11)).foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 4)
            }
        }
    }
}

struct FieldRow<Trailing: View>: View {
    let label: String
    var systemImage: String?
    var changed = false
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: 9) {
            if let systemImage {
                Image(systemName: systemImage).font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.muted).frame(width: 16)
                    .accessibilityHidden(true)
            }
            Text(label).font(.system(size: 12.5)).foregroundStyle(Theme.fg)
            if changed {
                Circle().fill(Theme.amber).frame(width: 5, height: 5)
                    .transition(.scale.combined(with: .opacity))
                    .help("已修改，尚未保存")
                    .accessibilityLabel("已修改")
            }
            Spacer(minLength: 12)
            trailing
        }
        .padding(.leading, 12).padding(.trailing, 8)
        .frame(minHeight: 40)
    }
}

// MARK: - Brand and status

struct LogoMark: View {
    var size: CGFloat = 26
    var body: some View {
        Group {
            if let icon = Brand.appIcon {
                Image(nsImage: icon).resizable().interpolation(.high)
            } else {
                RoundedRectangle(cornerRadius: size * 0.22, style: .continuous).fill(Theme.ink)
            }
        }
        // The artwork sits on the macOS icon grid (824 of 1024), so scale past the frame to fill it.
        .frame(width: size * 1024 / 824, height: size * 1024 / 824)
        .frame(width: size, height: size)
        .shadow(color: .black.opacity(0.22), radius: 2.5, y: 1)
        .accessibilityHidden(true)
    }
}

enum Tone {
    case neutral, accent, green, amber, red
    var fg: Color {
        switch self {
        case .neutral: Theme.muted
        case .accent: Theme.accent
        case .green: Theme.green
        case .amber: Theme.amber
        case .red: Theme.red
        }
    }
    var soft: Color {
        switch self {
        case .neutral: Theme.hover
        case .accent: Theme.accentSoft
        case .green: Theme.greenSoft
        case .amber: Theme.amberSoft
        case .red: Theme.redSoft
        }
    }
}

struct StatusPill: View {
    let text: String
    let tone: Tone
    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(tone.fg).frame(width: 5, height: 5)
            Text(text).font(.system(size: 11, weight: .medium))
        }
        .foregroundStyle(tone.fg)
        .padding(.horizontal, 8).frame(height: 20)
        .background(tone.soft, in: Capsule())
        .overlay(Capsule().strokeBorder(tone.fg.opacity(0.22), lineWidth: 0.5))
        .contentTransition(.opacity)
    }
}

struct Banner: View {
    let text: String
    let systemImage: String
    let tone: Tone
    var actionTitle: String?
    var action: (() -> Void)?
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: systemImage).font(.system(size: 12, weight: .semibold)).foregroundStyle(tone.fg)
                .padding(.top, 1).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 6) {
                Text(text).font(.system(size: 12)).foregroundStyle(Theme.fg2)
                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                if let actionTitle, let action {
                    Button(actionTitle, action: action).buttonStyle(LinkStyle(tone: tone))
                }
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(tone.soft, in: RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous).strokeBorder(tone.fg.opacity(0.18), lineWidth: 0.5))
    }
}

// MARK: - Buttons

struct IconButton: View {
    let systemImage: String
    let help: String
    var spinning = false
    let action: () -> Void
    @State private var hovering = false
    var body: some View {
        Button(action: action) {
            // A repeatForever animation would also animate layout moves of the button,
            // so the spin is driven by the clock instead.
            TimelineView(.animation(paused: !spinning)) { context in
                Image(systemName: systemImage).font(.system(size: 12.5, weight: .medium))
                    .rotationEffect(.degrees(spinning
                        ? context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 0.9) / 0.9 * 360 : 0))
            }
                .frame(width: 26, height: 26)
                .foregroundStyle(hovering ? Theme.fg : Theme.muted)
                .background(hovering ? Theme.hover : .clear, in: RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help(help)
        .accessibilityLabel(help)
    }
}

struct PrimaryStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12.5, weight: .semibold))
            .foregroundStyle(enabled ? Theme.inkFg : Theme.faint)
            .padding(.horizontal, 14).frame(height: 28)
            .background(enabled ? Theme.ink : Theme.hover, in: RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                .strokeBorder(.white.opacity(enabled ? 0.08 : 0), lineWidth: 0.5))
            .shadow(color: enabled ? .black.opacity(0.18) : .clear, radius: 2, y: 1)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct QuietStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        QuietLabel(label: configuration.label, pressed: configuration.isPressed)
    }
    private struct QuietLabel<Label: View>: View {
        let label: Label
        let pressed: Bool
        @Environment(\.isEnabled) private var enabled
        @State private var hovering = false
        var body: some View {
            label
                .font(.system(size: 12.5))
                .foregroundStyle(enabled ? (hovering ? Theme.fg : Theme.fg2) : Theme.faint)
                .padding(.horizontal, 10).frame(height: 28)
                .background(hovering && enabled ? Theme.hover : .clear, in: RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous))
                .contentShape(Rectangle())
                .onHover { hovering = $0 }
                .opacity(pressed ? 0.7 : 1)
        }
    }
}

struct LinkStyle: ButtonStyle {
    var tone: Tone = .accent
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(tone.fg)
            .opacity(configuration.isPressed ? 0.6 : 1)
            .contentShape(Rectangle())
    }
}

/// The pop-up button look: a white pill with a hairline edge, a breath of shadow,
/// and an accent ring while its menu is open.
struct PillChrome: ViewModifier {
    var hovering: Bool
    var active = false
    func body(content: Content) -> some View {
        content
            .background(hovering ? Theme.pillHover : Theme.pill, in: RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                .strokeBorder(active ? Theme.accent : Theme.pillLine, lineWidth: 1))
            .shadow(color: .black.opacity(0.05), radius: 0.5, y: 0.5)
    }
}

// MARK: - Pop-up menu picker

struct PickerOption: Identifiable, Equatable {
    var id: String
    var title: String
    var detail: String?
    var available = true
}

/// A pill that drops a native menu under itself. Native NSMenu tracking keeps the
/// menu bar panel open and key while choosing, unlike a popover window.
struct PopupPicker<Leading: View>: View {
    let label: String
    let options: [PickerOption]
    @Binding var selection: String
    var minWidth: CGFloat = 0
    @ViewBuilder var leading: Leading
    @State private var hovering = false
    @State private var open = false
    @State private var anchor = MenuAnchor.Box()
    @Environment(\.isEnabled) private var enabled

    private var current: PickerOption? { options.first { $0.id == selection } }

    var body: some View {
        Button(action: present) {
            HStack(spacing: 6) {
                leading
                Text(current?.title ?? selection).font(.system(size: 12, weight: .medium))
                    .foregroundStyle(current?.available == false ? Theme.amber : Theme.fg)
                    .lineLimit(1).truncationMode(.tail)
                Spacer(minLength: 0)
                Image(systemName: "chevron.up.chevron.down").font(.system(size: 8, weight: .bold))
                    .foregroundStyle(hovering || open ? Theme.muted : Theme.faint)
            }
            .padding(.leading, 8).padding(.trailing, 6)
            .frame(minWidth: minWidth, maxWidth: 220).frame(height: 24)
            .fixedSize(horizontal: minWidth == 0, vertical: false)
            .modifier(PillChrome(hovering: hovering && enabled, active: open))
            .contentShape(Rectangle())
            .background(MenuAnchor(box: anchor))
        }
        .buttonStyle(.plain)
        .opacity(enabled ? 1 : 0.5)
        .onHover { hovering = $0 }
        .accessibilityLabel(label)
        .accessibilityValue(current?.title ?? selection)
    }

    private func present() {
        guard let view = anchor.view else { return }
        let menu = NSMenu()
        menu.autoenablesItems = false
        for option in options {
            let item = NSMenuItem(title: option.title, action: #selector(MenuTarget.fire(_:)), keyEquivalent: "")
            let target = MenuTarget { selection = option.id }
            item.target = target
            item.representedObject = target
            item.state = option.id == selection ? .on : .off
            item.isEnabled = option.available
            if let detail = option.detail, !detail.isEmpty {
                if #available(macOS 14.4, *) { item.subtitle = detail } else { item.toolTip = detail }
            }
            menu.addItem(item)
        }
        menu.minimumWidth = view.bounds.width
        open = true
        let below = NSPoint(x: 0, y: view.isFlipped ? view.bounds.height + 4 : -4)
        menu.popUp(positioning: nil, at: below, in: view)
        open = false
    }
}

extension PopupPicker where Leading == EmptyView {
    init(label: String, options: [PickerOption], selection: Binding<String>, minWidth: CGFloat = 0) {
        self.init(label: label, options: options, selection: selection, minWidth: minWidth) { EmptyView() }
    }
}

private final class MenuTarget: NSObject {
    let handler: () -> Void
    init(_ handler: @escaping () -> Void) { self.handler = handler }
    @objc func fire(_ sender: NSMenuItem) { handler() }
}

struct MenuAnchor: NSViewRepresentable {
    final class Box { weak var view: NSView? }
    let box: Box
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        box.view = view
        return view
    }
    func updateNSView(_ view: NSView, context: Context) { box.view = view }
}

// MARK: - Segmented control and stepper

struct SegmentOption: Identifiable {
    var id: String
    var title: String
    var systemImage: String?
}

struct SegmentedControl: View {
    let label: String
    let options: [SegmentOption]
    @Binding var selection: String
    @Namespace private var thumb
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        HStack(spacing: 2) {
            ForEach(options) { option in
                let on = option.id == selection
                Button { withAnimation(Theme.ease) { selection = option.id } } label: {
                    HStack(spacing: 5) {
                        if let image = option.systemImage {
                            Image(systemName: image).font(.system(size: 10.5, weight: .semibold))
                        }
                        Text(option.title).font(.system(size: 12, weight: on ? .semibold : .regular))
                    }
                    .foregroundStyle(on ? Theme.fg : Theme.muted)
                    .frame(maxWidth: .infinity).frame(height: 26)
                    .background {
                        if on {
                            RoundedRectangle(cornerRadius: Theme.segmentRadius - 2, style: .continuous).fill(Theme.segThumb)
                                .shadow(color: .black.opacity(0.12), radius: 1, y: 1)
                                .overlay(RoundedRectangle(cornerRadius: Theme.segmentRadius - 2, style: .continuous)
                                    .strokeBorder(Theme.line, lineWidth: 0.5))
                                .matchedGeometryEffect(id: "thumb", in: thumb)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(option.title)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(2)
        .background(Theme.segTrack, in: RoundedRectangle(cornerRadius: Theme.segmentRadius, style: .continuous))
        .opacity(enabled ? 1 : 0.5)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(label)
    }
}

struct PillStepper: View {
    let label: String
    @Binding var value: Int
    let range: ClosedRange<Int>
    let unit: String

    var body: some View {
        HStack(spacing: 0) {
            step("minus", by: -1, disabled: value <= range.lowerBound)
            Theme.pillLine.frame(width: 1, height: 14)
            Text("\(value) \(unit)").font(.system(size: 12, weight: .medium).monospacedDigit())
                .foregroundStyle(Theme.fg).frame(minWidth: 44)
                .contentTransition(.numericText(value: Double(value)))
            Theme.pillLine.frame(width: 1, height: 14)
            step("plus", by: 1, disabled: value >= range.upperBound)
        }
        .frame(height: 24)
        .modifier(PillChrome(hovering: false))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityValue("\(value) \(unit)")
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: change(1)
            case .decrement: change(-1)
            @unknown default: break
            }
        }
    }

    private func step(_ image: String, by delta: Int, disabled: Bool) -> some View {
        Button { change(delta) } label: {
            Image(systemName: image).font(.system(size: 9, weight: .bold))
                .foregroundStyle(disabled ? Theme.faint.opacity(0.6) : Theme.fg2)
                .frame(width: 24, height: 24).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
    }

    private func change(_ delta: Int) {
        let next = min(max(value + delta, range.lowerBound), range.upperBound)
        if next != value { withAnimation(.snappy(duration: 0.2)) { value = next } }
    }
}

/// Four rising bars that read the reasoning effort at a glance.
struct EffortMeter: View {
    let effort: String
    private var level: Int {
        switch effort {
        case "none": 0
        case "minimal", "low": 1
        case "medium": 2
        case "high": 3
        default: 4
        }
    }
    var body: some View {
        HStack(alignment: .bottom, spacing: 1.5) {
            ForEach(0..<4, id: \.self) { index in
                RoundedRectangle(cornerRadius: 0.75)
                    .fill(index < level ? Theme.accent : Theme.faint.opacity(0.35))
                    .frame(width: 2.5, height: 4 + CGFloat(index) * 2.2)
            }
        }
        .frame(height: 11)
        .accessibilityHidden(true)
    }
}
