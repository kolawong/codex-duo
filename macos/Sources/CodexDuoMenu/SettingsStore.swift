import Foundation
import Observation

@Observable @MainActor
final class SettingsStore {
    private(set) var scope = "project"
    private(set) var source = "unconfigured"
    private(set) var globalRevision: String? = nil
    private(set) var hasProjectOverride = false
    private(set) var pendingScope: String?
    var sourceLabel: String { source == "project" ? "项目独立设置" : source == "global" ? (scope == "project" ? "继承全局默认" : "已保存的全局默认") : "未配置" }
    private(set) var projectRoot: String
    var draft: Draft? {
        didSet {
            if draft != baseline && !hasExternalChange { notice = nil }
        }
    }
    private(set) var catalog: Catalog?
    private(set) var baseline: Draft?
    private(set) var revision = "none"
    private(set) var isBusy = false
    private(set) var hasExternalChange = false
    private(set) var needsSave = false
    private(set) var errorMessage: String?
    private(set) var notice: String?
    private(set) var savedWarning: String?
    private var client: any CodexDuoServing
    private let clientFactory: (String) -> any CodexDuoServing
    private let history: ProjectHistory
    private(set) var recentProjects: [String]
    private(set) var pendingProject: String?
    private(set) var projectEnabled = false
    private(set) var copySelection: Selection?
    var canCopySelection: Bool { needsSave && copySelection != nil && !isBusy }
    var requiresProjectEnable: Bool { scope == "project" && source != "global" && draft?.workflow.activation == "automatic_project" && !projectEnabled }


    init(projectRoot: String, client: (any CodexDuoServing)? = nil,
         history: ProjectHistory = ProjectHistory(),
         clientFactory: @escaping (String) -> any CodexDuoServing = { CodexDuoClient(projectRoot: $0) }) {
        self.projectRoot = projectRoot
        self.clientFactory = clientFactory
        self.client = client ?? clientFactory(projectRoot)
        self.history = history
        self.recentProjects = history.paths
    }

    func requestProject(_ path: String) async {
        guard !isBusy else { return }
        do {
            let root = try ProjectHistory.validate(path)
            guard root != projectRoot else { return }
            if isDirty || hasExternalChange { pendingProject = root; return }
            await switchProject(root)
        } catch { errorMessage = error.localizedDescription }
    }

    func cancelProjectSwitch() { pendingProject = nil }

    func resolveProjectSwitch(saveFirst: Bool) async {
        guard !isBusy, let root = pendingProject else { return }
        if saveFirst {
            await save()
            guard !isDirty, !needsSave, errorMessage == nil else { return }
        }
        await switchProject(root)
    }

    private func switchProject(_ root: String) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            let canonical = try ProjectHistory.validate(root)
            let newClient = clientFactory(canonical)
            let state = try await newClient.state(scope: scope)
            // Validate without publishing a new project or dropping the old draft.
            let candidate = SettingsStore(projectRoot: canonical, client: newClient, history: history,
                                          clientFactory: clientFactory)
            try candidate.apply(state, discardDraft: true, settingsScope: scope)
            let previousSelection = needsSave ? nil : baseline?.selection
            let previousRoot = projectRoot
            projectRoot = canonical; client = newClient
            catalog = candidate.catalog; draft = candidate.draft; baseline = candidate.baseline
            revision = candidate.revision; needsSave = candidate.needsSave
            scope = candidate.scope; source = candidate.source; globalRevision = candidate.globalRevision
            hasProjectOverride = candidate.hasProjectOverride
            projectEnabled = candidate.projectEnabled; savedWarning = candidate.savedWarning
            hasExternalChange = false; errorMessage = nil; notice = candidate.notice
            copySelection = previousSelection; pendingProject = nil
            if let validPrevious = try? ProjectHistory.validate(previousRoot) { history.remember(validPrevious) }
            history.remember(canonical); recentProjects = history.paths
        } catch { errorMessage = "切换失败，原项目和修改已保留。" + error.localizedDescription }
    }

    func copyPreviousModels() {
        guard canCopySelection, let copySelection else { return }
        draft?.selection = copySelection
        notice = "已复制上个项目保存的模型选项。只复制模型，启用方式保持当前选择；确认后保存到当前项目。"
    }

    var projectName: String { URL(fileURLWithPath: projectRoot).lastPathComponent }
    var isDirty: Bool { draft != baseline }
    var canSave: Bool {
        guard let draft, !isBusy, !hasExternalChange else { return false }
        return (isDirty || needsSave || requiresProjectEnable) && draft.selection.worker.isValid(in: catalog)
            && draft.selection.coordinator.isValid(in: catalog) && draft.workflow.isValid
            && (draft.workflow.plannerMode == "disabled" || draft.workflow.plannerChoice.isValid(in: catalog))
    }

    func refresh(discardDraft: Bool = false) async {
        guard !isBusy else { return }
        isBusy = true
        defer { isBusy = false }
        errorMessage = nil
        do {
            let state = try await client.state(scope: scope)
            try apply(state, discardDraft: discardDraft)
        } catch { errorMessage = error.localizedDescription }
    }

    func apply(_ state: ServiceState, discardDraft: Bool = false, settingsScope: String? = nil) throws {
        guard let catalog = state.catalog, let saved = state.saved,
              let selection = saved.document?.selection ?? state.defaultSelection else {
            throw state.error ?? ServiceError(code: "invalid_response", message: "读不到模型列表或已保存的配置。")
        }
        guard state.projectRoot == projectRoot else {
            throw ServiceError(code: "project_mismatch", message: "配置服务返回的项目与当前项目不一致，已停止读取。")
        }
        let incomingScope = state.scope ?? settingsScope ?? scope
        if let settingsScope, incomingScope != settingsScope {
            throw ServiceError(code: "scope_mismatch", message: "配置范围不一致，原修改已保留。")
        }
        self.catalog = catalog
        projectEnabled = state.projectOptIn?.enabled == true
        savedWarning = saved.error?.message ?? (incomingScope == "project" ? state.effective?.error?.message : nil)
        let incoming = Draft(selection: selection, workflow: state.workflow ?? saved.document?.workflow ?? .initial)
        if isDirty && !discardDraft {
            hasExternalChange = saved.revision != revision || state.globalRevision != globalRevision
            if hasExternalChange { notice = "这份配置刚在别处被修改。你的修改还在，重新载入后才能保存。" }
            return
        }
        scope = incomingScope
        source = state.source ?? (saved.document == nil ? "unconfigured" : "project")
        globalRevision = state.globalRevision
        hasProjectOverride = state.layers?.project.document != nil || state.layers?.project.error != nil || (scope == "project" && saved.document != nil)
        draft = incoming
        baseline = incoming
        revision = saved.revision
        hasExternalChange = false
        needsSave = saved.error != nil || (saved.document == nil && (scope == "global" || state.effective?.document == nil))
        notice = needsSave ? "此范围还没有保存过配置。确认下面的选项后点「保存」。" : nil
    }

    func requestScope(_ value: String) async {
        guard !isBusy, ["global", "project"].contains(value), value != scope else { return }
        if isDirty || hasExternalChange { pendingScope = value; return }
        await switchScope(value)
    }
    func cancelScopeSwitch() { pendingScope = nil }
    func resolveScopeSwitch(saveFirst: Bool) async {
        guard let value = pendingScope, !isBusy else { return }
        if saveFirst { await save(); guard !isDirty, errorMessage == nil else { return } }
        await switchScope(value)
    }
    private func switchScope(_ value: String) async {
        isBusy = true; defer { isBusy = false }
        do {
            let incoming = try await client.state(scope: value)
            try apply(incoming, discardDraft: true, settingsScope: value)
            pendingScope = nil; errorMessage = nil
        } catch { errorMessage = "切换失败，原范围和修改已保留。" + error.localizedDescription }
    }
    func resetToInherit() async {
        guard scope == "project", !isBusy, !hasExternalChange, let draft else { return }
        isBusy = true; defer { isBusy = false }
        do {
            let state = try await client.reset(SaveBody(selection: draft.selection, workflow: draft.workflow,
                expectedRevision: revision, scope: "project", expectedGlobalRevision: globalRevision))
            try apply(state, discardDraft: true, settingsScope: "project")
            errorMessage = nil; notice = "已清除项目覆盖，后续任务继承全局默认。"
        } catch {
            errorMessage = error.localizedDescription
            if (error as? ServiceError)?.code == "revision_conflict" { hasExternalChange = true }
        }
    }



    func selectModel(_ id: String, coordinator: Bool) {
        guard var draft else { return }
        if coordinator { draft.selection.coordinator.selectModel(id, catalog: catalog) }
        else { draft.selection.worker.selectModel(id, catalog: catalog) }
        self.draft = draft
        notice = hasExternalChange ? notice : nil
    }

    func save() async {
        guard canSave, let sent = draft else { return }
        isBusy = true
        errorMessage = nil; notice = nil
        defer { isBusy = false }
        do {
            let saved = try await client.save(SaveBody(selection: sent.selection, workflow: sent.workflow,
                                                       expectedRevision: revision,
                                                       enableProject: requiresProjectEnable ? true : nil,
                                                       scope: scope, expectedGlobalRevision: globalRevision))
            guard let document = saved.document, saved.error == nil else {
                throw saved.error ?? ServiceError(code: "invalid_response", message: "保存后没能读回配置，请刷新确认。")
            }
            baseline = Draft(selection: document.selection, workflow: document.workflow ?? .initial)
            revision = saved.revision
            source = scope; hasProjectOverride = scope == "project" || hasProjectOverride
            if scope == "global" { globalRevision = saved.revision }
            projectEnabled = saved.projectOptIn?.enabled ?? projectEnabled
            needsSave = false; hasExternalChange = false; savedWarning = nil
            notice = "已保存。之后的新任务会使用这套设置。"
        } catch {
            errorMessage = error.localizedDescription
            if (error as? ServiceError)?.code == "revision_conflict" {
                hasExternalChange = true
                notice = "保存前配置已在别处被修改。你的修改还在，重新载入后再保存。"
            }
        }
    }
}
