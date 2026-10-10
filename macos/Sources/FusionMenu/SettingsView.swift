import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct SettingsView: View {
    @Bindable var store: SettingsStore
    var isWindow = false
    @State private var advanced = false
    @State private var confirmReload = false
    @State private var confirmReset = false
    @State private var showProjectPicker = false
    @State private var contentHeight: CGFloat = 480

    private var draft: Draft? { store.draft }
    private var baseline: Draft? { store.baseline }
    private var justSaved: Bool { !store.isDirty && store.notice?.hasPrefix("已保存") == true }
    private var canDiscard: Bool { store.isDirty || store.hasExternalChange }

    /// Notices worth a banner; a successful save is shown on the save button instead.
    private var visibleNotice: String? { justSaved ? nil : store.notice }
    private var hasMessages: Bool {
        store.savedWarning != nil || store.errorMessage != nil || visibleNotice != nil
    }

    private var changeCount: Int {
        guard let draft, let baseline else { return 0 }
        let (d, b) = (draft, baseline)
        return [d.selection.worker.model != b.selection.worker.model,
                d.selection.worker.reasoningEffort != b.selection.worker.reasoningEffort,
                d.workflow.activation != b.workflow.activation,
                d.workflow.maxWorkerTurns != b.workflow.maxWorkerTurns,
                d.workflow.maxParallelWorkers != b.workflow.maxParallelWorkers,
                d.workflow.coordinatorMode != b.workflow.coordinatorMode,
                d.selection.coordinator.model != b.selection.coordinator.model,
                d.selection.coordinator.reasoningEffort != b.selection.coordinator.reasoningEffort]
            .filter { $0 }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    PanelSection(title: "设置范围") {
                        Card {
                            FieldRow(label: "编辑范围", systemImage: "slider.horizontal.3") {
                                PopupPicker(label: "编辑范围", options: [PickerOption(id: "global", title: "全局默认"), PickerOption(id: "project", title: "当前项目")], selection: Binding(get: { store.scope }, set: { value in Task { await store.requestScope(value) } }), minWidth: 180)
                            }
                            CardDivider(inset: 37)
                            FieldRow(label: "当前来源", systemImage: "arrow.down.circle") { Text(store.sourceLabel).font(.system(size: 11.5)).foregroundStyle(Theme.muted) }
                        }
                        if store.scope == "global" {
                            Text("适用于所有未单独配置的项目。")
                                .font(.system(size: 11)).foregroundStyle(Theme.muted)
                        }
                        if store.scope == "project" && store.hasProjectOverride {
                            Button("清除项目覆盖，继承全局") { confirmReset = true }.buttonStyle(LinkStyle(tone: .accent)).disabled(store.isBusy || store.hasExternalChange)
                        }
                    }
                    if store.scope == "project" { project }
                    if draft != nil {
                        settings
                    } else if store.isBusy {
                        loading
                    }
                    if hasMessages { messages }
                }
                .padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 14)
                .animation(Theme.ease, value: draft == nil)
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
            }
            .scrollIndicators(.never)
            .scrollBounceBehavior(.basedOnSize)
            // A ScrollView takes all offered height; hug the content up to the cap instead.
            .frame(height: min(max(contentHeight, 1), 560))
            footer
        }
        .frame(width: 400)
        .background { surface }
        .tint(Theme.accent)
        .task { await store.refresh() }
        // The panel is reused between openings. Refresh whenever a window regains focus.
        .onReceive(NotificationCenter.default.publisher(for: NSWindow.didBecomeKeyNotification)) { _ in
            Task { await store.refresh() }
        }
        .fileImporter(isPresented: $showProjectPicker, allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result { Task { await store.requestProject(url.path) } }
        }
        .alert("切换范围前保存修改？", isPresented: Binding(get: { store.pendingScope != nil }, set: { _ in })) {
            Button("保存并切换") { Task { await store.resolveScopeSwitch(saveFirst: true) } }.disabled(!store.canSave)
            Button("放弃并切换", role: .destructive) { Task { await store.resolveScopeSwitch(saveFirst: false) } }
            Button("取消", role: .cancel) { store.cancelScopeSwitch() }
        } message: { Text("切换失败会保留原范围和修改。") }
        .alert("继承全局默认？", isPresented: $confirmReset) {
            Button("取消", role: .cancel) { }
            Button("清除覆盖", role: .destructive) { Task { await store.resetToInherit() } }
        } message: { Text("清除当前项目覆盖并备份原配置。全局设置不会改变，未保存的修改会丢失。") }
        .alert("切换项目前保存修改？", isPresented: Binding(
            get: { store.pendingProject != nil },
            set: { _ in })) {
            Button("保存并切换") { Task { await store.resolveProjectSwitch(saveFirst: true) } }
                .disabled(!store.canSave)
            Button("放弃并切换", role: .destructive) { Task { await store.resolveProjectSwitch(saveFirst: false) } }
            Button("取消", role: .cancel) { store.cancelProjectSwitch() }
        } message: {
            Text("当前项目有未保存的修改。切换失败会保留原项目和修改。")
        }
        .alert("放弃未保存的修改？", isPresented: $confirmReload) {
            Button("取消", role: .cancel) { }
            Button("放弃并重新载入", role: .destructive) { Task { await store.refresh(discardDraft: true) } }
        } message: {
            Text("将重新读取所选范围的最新配置，面板里未保存的修改会丢失。")
        }
    }

    /// The floating panel already draws the native material and clips to its radius;
    /// here it only gets a warm tint and the hairline edge, on the same radius.
    @ViewBuilder private var surface: some View {
        if isWindow {
            PanelBackground()
        } else {
            let shape = RoundedRectangle(cornerRadius: Theme.panelRadius, style: .continuous)
            shape.fill(Theme.bg.opacity(0.72))
                .overlay(shape.strokeBorder(Theme.panelEdge, lineWidth: 1))
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 9) {
            LogoMark(size: isWindow ? 22 : 26)
            VStack(alignment: .leading, spacing: 0) {
                Text(Brand.name).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Theme.fg)
                if !isWindow {
                    Text(Brand.tagline).font(.system(size: 10.5)).foregroundStyle(Theme.muted)
                }
            }
            status.animation(.easeOut(duration: 0.2), value: statusText)
            Spacer()
            IconButton(systemImage: "arrow.clockwise", help: "刷新（保留未保存的修改）",
                       spinning: store.isBusy) { Task { await store.refresh() } }
                .disabled(store.isBusy)
            if !isWindow {
                IconButton(systemImage: "macwindow", help: "在独立窗口中打开") { StartupDelegate.presentSettings() }
            }
        }
        // 88pt clears the traffic lights, which centre in a 52pt unified title bar.
        .padding(.leading, isWindow ? 88 : 14).padding(.trailing, 10)
        .frame(height: isWindow ? 52 : 50)
    }

    private var statusText: String {
        if store.isBusy && draft == nil { return "读取中" }
        if store.hasExternalChange { return "有冲突" }
        if store.isDirty { return "未保存" }
        if store.needsSave { return "未配置" }
        if draft == nil { return store.errorMessage == nil ? "读取中" : "读取失败" }
        return "已保存"
    }

    private var status: some View {
        let tone: Tone = switch statusText {
        case "读取中": .neutral
        case "有冲突", "读取失败": .red
        case "未保存": .amber
        case "未配置": .accent
        default: .green
        }
        return StatusPill(text: statusText, tone: tone)
            .accessibilityLabel("状态：\(statusText)")
    }

    // MARK: Project

    private var project: some View {
        PanelSection(title: "项目", footnote: "全局默认用于各项目，项目覆盖优先。Codex 聊天始终使用各自项目，切换不会改变聊天路径。") {
            Card {
                HStack(spacing: 10) {
                    Image(systemName: "folder.fill").font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.fg2)
                        .frame(width: 30, height: 30)
                        .background(Theme.segTrack, in: RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous))
                        .accessibilityHidden(true)
                    Button { showProjectPicker = true } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(store.projectName).font(.system(size: 13, weight: .medium)).foregroundStyle(Theme.fg)
                            .lineLimit(1)
                        Text(store.projectRoot).font(.system(size: 11, design: .monospaced)).foregroundStyle(Theme.muted)
                            .lineLimit(1).truncationMode(.middle)
                            .help(store.projectRoot)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).disabled(store.isBusy)
                    .accessibilityLabel("选择项目目录，当前项目：\(store.projectName)")
                    Menu {
                        Button("选择项目目录…") { showProjectPicker = true }
                        if !store.recentProjects.isEmpty { Divider() }
                        ForEach(store.recentProjects, id: \.self) { path in
                            Button(path) { Task { await store.requestProject(path) } }
                        }
                    } label: { Image(systemName: "chevron.down").foregroundStyle(Theme.muted) }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().disabled(store.isBusy)
                    .help("选择目录或最近项目")
                    IconButton(systemImage: "arrow.up.forward.square", help: "在访达中打开") {
                        NSWorkspace.shared.open(URL(fileURLWithPath: store.projectRoot))
                    }
                }
                .padding(.leading, 10).padding(.trailing, 8).padding(.vertical, 9)
            }
            if store.canCopySelection {
                Button("复制上个项目保存的模型选项") { store.copyPreviousModels() }
                    .buttonStyle(LinkStyle(tone: .accent))
                Text("也可使用下面的默认选项。新项目保持手动，选择自动后保存才启用项目。")
                    .font(.system(size: 11)).foregroundStyle(Theme.muted)
            }
        }
    }

    // MARK: Settings

    private var settings: some View {
        let automatic = draft?.workflow.activation == "automatic_project"
        return VStack(alignment: .leading, spacing: 16) {
            PanelSection(title: "执行代理", footnote: "当前聊天把任务交给它完成，再由聊天验收结果。") {
                Card {
                    ModelFields(choice: choice(coordinator: false), baseline: baseline?.selection.worker,
                                catalog: store.catalog)
                }
            }
            PanelSection(title: "启用方式", footnote: "首次执行和每次修正各算一次；用完后停止，并说明还剩哪些工作。") {
                Card {
                    VStack(alignment: .leading, spacing: 8) {
                        SegmentedControl(label: "启用方式", options: [
                            SegmentOption(id: "automatic_project", title: "自动", systemImage: "bolt.fill"),
                            SegmentOption(id: "manual", title: "手动", systemImage: "hand.tap")
                        ], selection: workflow(\.activation, fallback: "manual"))
                        Text(store.scope == "global"
                             ? (automatic ? "各项目开发任务自动启用；项目独立设置优先。" : "各项目默认手动启用；项目覆盖优先。")
                             : store.source == "global"
                             ? (automatic ? "继承全局自动模式，编辑后保存为当前项目独立设置。" : "继承全局手动模式，仅明确要求时启用。")
                             : automatic
                             ? (store.requiresProjectEnable
                                ? "保存会在本项目 AGENTS.md 添加 Codex Duo 指令，之后开发任务自动启用。已打开的聊天首次可调用 $codex-duo。"
                                : "在这个项目里提开发任务时自动启用，不用每次说明。")
                             : "只在你于聊天中明确要求时启用。")
                            .font(.system(size: 11.5)).foregroundStyle(Theme.muted)
                            .padding(.horizontal, 2)
                            .contentTransition(.opacity)
                            .animation(Theme.ease, value: automatic)
                    }
                    .padding(10)
                    CardDivider(inset: 0)
                    FieldRow(label: "执行次数上限", systemImage: "repeat",
                             changed: draft?.workflow.maxWorkerTurns != baseline?.workflow.maxWorkerTurns) {
                        PillStepper(label: "执行次数上限",
                                    value: workflow(\.maxWorkerTurns, fallback: 3), range: 1...10, unit: "次")
                    }
                }
            }
            advancedSection
        }
        .disabled(store.isBusy)
        .animation(Theme.ease, value: changeCount)
    }

    private var advancedSection: some View {
        let selected = draft?.workflow.coordinatorMode == "selected_model"
        let modeChanged = draft?.workflow.coordinatorMode != baseline?.workflow.coordinatorMode
        return Card {
            Button { withAnimation(Theme.ease) { advanced.toggle() } } label: {
                HStack(spacing: 9) {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.muted).frame(width: 16)
                    Text("高级设置").font(.system(size: 12.5, weight: .medium)).foregroundStyle(Theme.fg)
                    Text("高级").font(.system(size: 10.5, weight: .medium)).foregroundStyle(Theme.muted)
                        .padding(.horizontal, 5).frame(height: 16)
                        .background(Theme.segTrack, in: Capsule())
                    if modeChanged || draft?.workflow.maxParallelWorkers != baseline?.workflow.maxParallelWorkers || (!advanced && coordinatorModelChanged) {
                        Circle().fill(Theme.amber).frame(width: 5, height: 5)
                    }
                    Spacer()
                    Text(selected ? "指定模型" : "当前聊天").font(.system(size: 11.5)).foregroundStyle(Theme.muted)
                    Image(systemName: "chevron.right").font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(Theme.faint)
                        .rotationEffect(.degrees(advanced ? 90 : 0))
                }
                .padding(.horizontal, 12).frame(height: 40)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("高级设置，规划方和并行执行")
            .accessibilityValue(advanced ? "已展开" : "已收起")

            if advanced {
                CardDivider(inset: 0)
                FieldRow(label: "最大并行执行代理数", systemImage: "person.2",
                         changed: draft?.workflow.maxParallelWorkers != baseline?.workflow.maxParallelWorkers) {
                    PillStepper(label: "最大并行执行代理数",
                                value: workflow(\.maxParallelWorkers, fallback: 1), range: 1...3, unit: "个")
                }
                Text("默认 1；主控仅并行派发独立任务，并受宿主容量和整个任务总执行次数限制。")
                    .font(.system(size: 11)).foregroundStyle(Theme.muted)
                    .padding(.horizontal, 12).padding(.bottom, 9)
                CardDivider(inset: 0)
                VStack(alignment: .leading, spacing: 8) {
                    SegmentedControl(label: "由谁规划", options: [
                        SegmentOption(id: "current_thread", title: "当前聊天", systemImage: "bubble.left"),
                        SegmentOption(id: "selected_model", title: "指定模型", systemImage: "cpu")
                    ], selection: workflow(\.coordinatorMode, fallback: "current_thread"))
                    Text(selected
                         ? "只记录你偏好的规划模型。不会自动新建聊天，只有你明确要求时才会新建。"
                         : "你正在使用的聊天负责拆解任务和验收结果。\(Brand.name) 不会更改它的模型。")
                        .font(.system(size: 11.5)).foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 2)
                        .contentTransition(.opacity)
                }
                .padding(10)
                .background(Theme.card2)
                CardDivider(inset: 0)
                ModelFields(choice: choice(coordinator: true), baseline: baseline?.selection.coordinator,
                            catalog: store.catalog)
                    .disabled(!selected)
                    .background(Theme.card2)
                CardDivider(inset: 0)
                Text(selected ? "切换方式不会清除已选的模型。" : "选「指定模型」后才会使用上面的模型；切换不会清除已选内容。")
                    .font(.system(size: 11)).foregroundStyle(Theme.muted)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12).padding(.vertical, 9)
                    .background(Theme.card2)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
    }

    private var coordinatorModelChanged: Bool {
        guard let draft, let baseline else { return false }
        return draft.selection.coordinator != baseline.selection.coordinator
    }

    private var loading: some View {
        Card {
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text("正在读取模型列表和配置…").font(.system(size: 12.5)).foregroundStyle(Theme.muted)
                Spacer()
            }
            .padding(14)
        }
    }

    // MARK: Messages and footer

    @ViewBuilder private var messages: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let warning = store.savedWarning {
                Banner(text: warning, systemImage: "exclamationmark.triangle.fill", tone: .amber)
            }
            if let error = store.errorMessage {
                Banner(text: error, systemImage: "exclamationmark.octagon.fill", tone: .red,
                       actionTitle: store.isBusy ? nil : "重试",
                       action: store.isBusy ? nil : { Task { await store.refresh() } })
            }
            if let notice = visibleNotice {
                Banner(text: notice,
                       systemImage: store.hasExternalChange ? "arrow.triangle.2.circlepath" : "info.circle.fill",
                       tone: store.hasExternalChange ? .amber : .accent,
                       actionTitle: store.hasExternalChange ? "放弃修改并重新载入" : nil,
                       action: store.hasExternalChange ? { confirmReload = true } : nil)
            }
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
        .animation(Theme.ease, value: store.notice)
        .animation(Theme.ease, value: store.errorMessage)
    }

    private var footer: some View {
        VStack(spacing: 0) {
            Theme.line.frame(height: 1)
            HStack(spacing: 6) {
                if changeCount > 0 || store.hasExternalChange {
                    HStack(spacing: 6) {
                        Circle().fill(Theme.amber).frame(width: 6, height: 6)
                        Text(changeCount > 0 ? "\(changeCount) 项修改未保存" : "配置已在别处更新")
                            .font(.system(size: 12)).foregroundStyle(Theme.fg2)
                            .contentTransition(.numericText(value: Double(changeCount)))
                        Button("放弃") { confirmReload = true }
                            .buttonStyle(LinkStyle(tone: .accent))
                            .disabled(store.isBusy)
                            .help("放弃修改并重新载入")
                    }
                    .padding(.leading, 6)
                    .transition(.opacity.combined(with: .move(edge: .leading)))
                } else {
                    Button("退出") { NSApplication.shared.terminate(nil) }
                        .buttonStyle(QuietStyle())
                        .help("退出 \(Brand.name)（也可右键点击菜单栏图标）")
                        .transition(.opacity)
                }
                Spacer()
                saveButton
            }
            .padding(.horizontal, 10).padding(.vertical, 9)
            .animation(Theme.ease, value: changeCount)
            .animation(Theme.ease, value: justSaved)
        }
    }

    @ViewBuilder private var saveButton: some View {
        if justSaved {
            HStack(spacing: 5) {
                Image(systemName: "checkmark.circle.fill").font(.system(size: 12, weight: .semibold))
                Text("已保存").font(.system(size: 12.5, weight: .semibold))
            }
            .foregroundStyle(Theme.green)
            .padding(.horizontal, 12).frame(height: 28)
            .transition(.scale(scale: 0.9).combined(with: .opacity))
            .accessibilityLabel("已保存，之后的新任务会使用这套设置")
        } else {
            Button { Task { await store.save() } } label: {
                HStack(spacing: 7) {
                    if store.isBusy && store.isDirty {
                        ProgressView().controlSize(.mini).tint(Theme.inkFg)
                        Text("保存中…")
                    } else {
                        Text("保存")
                        Text("⌘S").font(.system(size: 10.5, weight: .medium)).opacity(0.55)
                    }
                }
            }
            .buttonStyle(PrimaryStyle())
            .disabled(!store.canSave)
            .keyboardShortcut("s", modifiers: .command)
            .help(store.hasExternalChange ? "配置已在别处更新，需先重新载入" : "保存后，之后的新任务会使用这套设置")
            .transition(.opacity)
        }
    }

    // MARK: Bindings

    private func choice(coordinator: Bool) -> Binding<ModelChoice> {
        Binding(get: {
            let fallback = ModelChoice(model: "", reasoningEffort: "")
            return coordinator ? draft?.selection.coordinator ?? fallback : draft?.selection.worker ?? fallback
        }, set: { value in
            if coordinator { store.draft?.selection.coordinator = value }
            else { store.draft?.selection.worker = value }
        })
    }

    private func workflow<Value>(_ key: WritableKeyPath<Workflow, Value>, fallback: Value) -> Binding<Value> {
        Binding(get: { draft?.workflow[keyPath: key] ?? fallback },
                set: { store.draft?.workflow[keyPath: key] = $0 })
    }
}

private struct ModelFields: View {
    @Binding var choice: ModelChoice
    let baseline: ModelChoice?
    let catalog: Catalog?
    private var model: ModelOption? { catalog?.models.first { $0.id == choice.model } }

    private var modelOptions: [PickerOption] {
        var options = (catalog?.models ?? []).map { PickerOption(id: $0.id, title: $0.name, detail: $0.description) }
        if model == nil {
            options.insert(PickerOption(id: choice.model, title: "\(choice.model)（本机不可用）", available: false), at: 0)
        }
        return options
    }

    private var effortOptions: [PickerOption] {
        var options = (model?.efforts ?? []).map { PickerOption(id: $0, title: Self.effortName($0), detail: $0) }
        if !(model?.efforts.contains(choice.reasoningEffort) ?? false) {
            options.insert(PickerOption(id: choice.reasoningEffort, title: "\(Self.effortName(choice.reasoningEffort))（此模型不支持）",
                                        available: false), at: 0)
        }
        return options
    }

    var body: some View {
        VStack(spacing: 0) {
            FieldRow(label: "模型", systemImage: "cpu", changed: baseline.map { $0.model != choice.model } ?? false) {
                PopupPicker(label: "模型", options: modelOptions, selection: Binding(get: { choice.model }, set: { id in
                    choice.selectModel(id, catalog: catalog)
                }), minWidth: 150)
            }
            CardDivider(inset: 37)
            FieldRow(label: "推理强度", systemImage: "brain",
                     changed: baseline.map { $0.reasoningEffort != choice.reasoningEffort } ?? false) {
                PopupPicker(label: "推理强度", options: effortOptions, selection: $choice.reasoningEffort,
                            minWidth: 150) {
                    EffortMeter(effort: choice.reasoningEffort)
                }
            }
        }
    }

    static func effortName(_ value: String) -> String {
        let titles = ["none": "关闭", "minimal": "极低", "low": "低", "medium": "中", "high": "高",
                      "xhigh": "很高", "max": "最高", "ultra": "超高"]
        return titles[value] ?? value
    }
}
