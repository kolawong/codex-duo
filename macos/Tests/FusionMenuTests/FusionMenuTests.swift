import XCTest
@testable import FusionMenu

final class StubService: FusionServing {
    var response: ServiceState
    var readError: ServiceError?
    var saveError: ServiceError?
    var saved: SavedState?
    var sent: SaveBody?
    var readDelay: UInt64 = 0
    var requestedScope: String?
    var resetResponse: ServiceState?
    var resetError: ServiceError?
    var resetSent: SaveBody?
    init(_ state: ServiceState) { response = state }
    func state() async throws -> ServiceState {
        if readDelay > 0 { try await Task.sleep(nanoseconds: readDelay) }
        if let readError { throw readError }
        return response
    }
    func state(scope: String) async throws -> ServiceState { requestedScope = scope; return try await state() }
    func reset(_ body: SaveBody) async throws -> ServiceState {
        resetSent = body
        if let resetError { throw resetError }
        return resetResponse!
    }
    func save(_ body: SaveBody) async throws -> SavedState {
        sent = body
        if let saveError { throw saveError }
        return saved!
    }
}

final class FusionMenuTests: XCTestCase {
    @MainActor func testParallelLimitLegacyDefaultDraftValidationAndSave() async throws {
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        XCTAssertEqual(store.draft?.workflow.maxParallelWorkers, 1)
        XCTAssertFalse(store.isDirty)
        store.draft?.workflow.maxParallelWorkers = 3
        XCTAssertTrue(store.canSave)
        await store.refresh()
        XCTAssertEqual(store.draft?.workflow.maxParallelWorkers, 3)
        store.draft?.workflow.maxParallelWorkers = 4
        XCTAssertFalse(store.canSave)
        store.draft?.workflow.maxParallelWorkers = 2
        let draft = store.draft!
        service.saved = SavedState(document: SavedDocument(selection: draft.selection, workflow: draft.workflow, savedAt: "now"), revision: "saved", error: nil)
        await store.save()
        XCTAssertEqual(service.sent?.workflow.maxParallelWorkers, 2)
        XCTAssertFalse(store.isDirty)
        XCTAssertEqual(store.draft?.workflow.maxParallelWorkers, 2)
    }

    func testParallelLimitExplicitMalformedValueDoesNotDefault() throws {
        for value in ["null", "true", "\"2\""] {
            let json = "{\"activation\":\"manual\",\"coordinator_mode\":\"current_thread\",\"max_worker_turns\":3,\"max_parallel_workers\":\(value)}"
            XCTAssertThrowsError(try JSONDecoder().decode(Workflow.self, from: Data(json.utf8)))
        }
    }

    func testProcessDrainsBothPipesAndEnforcesOutputLimit() {
        XCTAssertThrowsError(try FusionClient.run(executable: "/bin/sh",
            arguments: ["-c", "/usr/bin/head -c 2100000 /dev/zero; /usr/bin/head -c 2100000 /dev/zero >&2"],
            input: Data(), environment: [:], timeout: 5)) { error in
                XCTAssertEqual((error as? ServiceError)?.code, "output_limit")
            }
    }

    func testProcessTimeoutKillsAnUnresponsiveChild() {
        let start = Date()
        XCTAssertThrowsError(try FusionClient.run(executable: "/bin/sh",
            arguments: ["-c", "trap '' TERM; exec /bin/sleep 5"],
            input: Data(repeating: 65, count: 128 * 1024), environment: [:], timeout: 0.1)) { error in
                XCTAssertEqual((error as? ServiceError)?.code, "timeout")
            }
        XCTAssertLessThan(Date().timeIntervalSince(start), 4)
    }

    private func state(revision: String = "first", effort: String = "high") throws -> ServiceState {
        let json = """
        {"catalog":{"models":[
          {"id":"alpha","name":"Alpha","description":"A","efforts":["low","high"],"default_effort":"high"},
          {"id":"beta","name":"Beta","description":"B","efforts":["medium"],"default_effort":"medium"}],"fingerprint":"catalog"},
         "default":{"coordinator":{"model":"alpha","reasoning_effort":"high"},"worker":{"model":"alpha","reasoning_effort":"high"}},
         "saved":{"document":{"selection":{"coordinator":{"model":"alpha","reasoning_effort":"high"},"worker":{"model":"alpha","reasoning_effort":"\(effort)"}},
         "workflow":{"activation":"automatic_project","coordinator_mode":"current_thread","max_worker_turns":7},"saved_at":"today"},"revision":"\(revision)","error":null},
         "workflow":{"activation":"automatic_project","coordinator_mode":"current_thread","max_worker_turns":7},"project_opt_in":{"enabled":true,"error":null},"project_root":"/isolated/project"}
        """
        return try JSONDecoder().decode(ServiceState.self, from: Data(json.utf8))
    }

    func testServiceSchemaDecodingAndSaveEncoding() throws {
        let state = try state()
        XCTAssertEqual(state.catalog?.models[1].defaultEffort, "medium")
        XCTAssertEqual(state.saved?.document?.selection.worker.reasoningEffort, "high")
        XCTAssertEqual(state.workflow?.maxWorkerTurns, 7)
        XCTAssertEqual(state.workflow?.maxParallelWorkers, 1)
        let data = try JSONEncoder().encode(SaveBody(selection: state.defaultSelection!, workflow: .initial, expectedRevision: "rev"))
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(json["expected_revision"] as? String, "rev")
        let workflow = json["workflow"] as! [String: Any]
        XCTAssertEqual(workflow["max_worker_turns"] as? Int, 3)
        XCTAssertEqual(workflow["max_parallel_workers"] as? Int, 1)
    }

    func testModelChangesKeepSupportedEffortAndChooseDefaultOtherwise() throws {
        let catalog = try state().catalog!
        var choice = ModelChoice(model: "alpha", reasoningEffort: "low")
        choice.selectModel("alpha", catalog: catalog)
        XCTAssertEqual(choice.reasoningEffort, "low")
        choice.selectModel("beta", catalog: catalog)
        XCTAssertEqual(choice.reasoningEffort, "medium")
        XCTAssertTrue(choice.isValid(in: catalog))
    }

    @MainActor func testRefreshRetainsDraftAndOldRevisionOnExternalChange() async throws {
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        store.draft?.workflow.maxWorkerTurns = 4
        let draft = store.draft
        service.response = try state(revision: "external", effort: "low")
        await store.refresh()
        XCTAssertEqual(store.draft, draft)
        XCTAssertEqual(store.revision, "first")
        XCTAssertTrue(store.hasExternalChange)
        XCTAssertFalse(store.canSave)
        await store.refresh(discardDraft: true)
        XCTAssertEqual(store.revision, "external")
        XCTAssertEqual(store.draft?.selection.worker.reasoningEffort, "low")
        XCTAssertFalse(store.isDirty)
    }

    @MainActor func testFailedReloadKeepsDraftAndDoesNotSave() async throws {
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        store.selectModel("beta", coordinator: false)
        let draft = store.draft
        service.readError = ServiceError(code: "catalog_unavailable", message: "目录不可用")
        await store.refresh(discardDraft: true)
        XCTAssertEqual(store.draft, draft)
        XCTAssertEqual(store.errorMessage, "目录不可用")
        XCTAssertNil(service.sent)
    }

    @MainActor func testConflictSavePreservesDirtyDraftAndDoesNotRetry() async throws {
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        store.draft?.workflow.maxWorkerTurns = 2
        let draft = store.draft
        service.saveError = ServiceError(code: "revision_conflict", message: "配置已更新")
        await store.save()
        XCTAssertEqual(service.sent?.expectedRevision, "first")
        XCTAssertEqual(store.draft, draft)
        XCTAssertTrue(store.isDirty)
        XCTAssertTrue(store.hasExternalChange)
        XCTAssertFalse(store.canSave)
        XCTAssertEqual(store.errorMessage, "配置已更新")
    }

    @MainActor func testSuccessfulSaveAndInactiveCoordinatorChoice() async throws {
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        store.selectModel("beta", coordinator: true)
        store.draft?.workflow.coordinatorMode = "selected_model"
        store.draft?.workflow.coordinatorMode = "current_thread"
        let draft = store.draft!
        service.saved = SavedState(document: SavedDocument(selection: draft.selection, workflow: draft.workflow, savedAt: "now"), revision: "saved", error: nil)
        await store.save()
        XCTAssertEqual(service.sent?.selection.coordinator.model, "beta")
        XCTAssertEqual(service.sent?.workflow.coordinatorMode, "current_thread")
        XCTAssertEqual(store.revision, "saved")
        XCTAssertFalse(store.isDirty)
        XCTAssertFalse(store.canSave)
        XCTAssertTrue(store.notice?.contains("已保存") == true)
        store.draft?.workflow.maxWorkerTurns = 2
        XCTAssertNil(store.notice)
        XCTAssertTrue(store.isDirty)
    }

    @MainActor func testEmptyAndLegacyStatesAndProjectMismatch() throws {
        var incoming = try state()
        incoming.saved = SavedState(document: nil, revision: "none", error: nil)
        incoming.workflow = nil
        let store = SettingsStore(projectRoot: "/isolated/project", client: StubService(incoming))
        try store.apply(incoming)
        XCTAssertEqual(store.draft?.workflow, .initial)
        XCTAssertTrue(store.canSave)
        XCTAssertFalse(store.isDirty)
        incoming.projectRoot = "/different/project"
        XCTAssertThrowsError(try store.apply(incoming))
        XCTAssertEqual(store.revision, "none")
        XCTAssertFalse(Workflow(activation: "manual", coordinatorMode: "current_thread", maxWorkerTurns: 11).isValid)
        XCTAssertFalse(Workflow(activation: "manual", coordinatorMode: "current_thread", maxWorkerTurns: 3, maxParallelWorkers: 4).isValid)
    }
    @MainActor func testProjectSwitchPreservesDraftOnCancelFailureAndBusyThenCopiesOnlyModels() async throws {
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let a = temp.appendingPathComponent("a"), b = temp.appendingPathComponent("b")
        try FileManager.default.createDirectory(at: a, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: b, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temp) }
        let rootA = a.resolvingSymlinksInPath().path, rootB = b.resolvingSymlinksInPath().path
        let suite = "duo-tests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var incomingA = try state(); incomingA.projectRoot = rootA
        var incomingB = try state(); incomingB.projectRoot = rootB
        incomingB.saved = SavedState(document: nil, revision: "none", error: nil)
        incomingB.workflow = .initial; incomingB.projectOptIn = ProjectOptIn(enabled: false, error: nil)
        let serviceA = StubService(incomingA), serviceB = StubService(incomingB)
        let store = SettingsStore(projectRoot: rootA, client: serviceA, history: ProjectHistory(defaults: defaults),
                                  clientFactory: { $0 == rootB ? serviceB : serviceA })
        await store.refresh()
        store.draft?.workflow.maxWorkerTurns = 5
        let unsaved = store.draft
        await store.requestProject(rootB)
        XCTAssertEqual(store.pendingProject, rootB)
        XCTAssertEqual(store.projectRoot, rootA)
        store.cancelProjectSwitch()
        XCTAssertEqual(store.draft, unsaved)
        await store.requestProject(rootB)
        serviceB.readError = ServiceError(code: "offline", message: "无法读取")
        await store.resolveProjectSwitch(saveFirst: false)
        XCTAssertEqual(store.projectRoot, rootA)
        XCTAssertEqual(store.draft, unsaved)
        XCTAssertTrue(store.isDirty)
        XCTAssertTrue(defaults.dictionaryRepresentation().keys.filter { $0.hasPrefix("codex-duo.") }.isEmpty)
        serviceB.readError = nil; serviceB.readDelay = 100_000_000
        let switching = Task { await store.resolveProjectSwitch(saveFirst: false) }
        for _ in 0..<10 where !store.isBusy { await Task.yield() }
        XCTAssertTrue(store.isBusy)
        await store.requestProject(rootA)
        await store.save()
        XCTAssertNil(serviceA.sent)
        await switching.value
        XCTAssertEqual(store.projectRoot, rootB)
        XCTAssertEqual(store.draft?.workflow.activation, "manual")
        XCTAssertEqual(store.recentProjects, [rootB, rootA])
        XCTAssertTrue(store.canCopySelection)
        store.draft?.workflow.activation = "automatic_project"
        store.copyPreviousModels()
        XCTAssertEqual(store.draft?.selection, incomingA.saved?.document?.selection)
        XCTAssertEqual(store.draft?.workflow.activation, "automatic_project")
        XCTAssertTrue(store.notice?.contains("当前选择") == true)
        XCTAssertTrue(store.requiresProjectEnable)
        let draft = store.draft!
        serviceB.saved = SavedState(document: SavedDocument(selection: draft.selection, workflow: draft.workflow, savedAt: "now"),
                                   revision: "new", error: nil, projectOptIn: ProjectOptIn(enabled: true, error: nil))
        await store.save()
        XCTAssertEqual(serviceB.sent?.enableProject, true)
        XCTAssertNil(serviceA.sent)
        XCTAssertTrue(store.projectEnabled)
        XCTAssertFalse(store.canSave)
    }

    @MainActor func testSaveBeforeSwitchFailureKeepsOldProjectAndDraft() async throws {
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temp) }
        let target = temp.resolvingSymlinksInPath().path
        let suite = "duo-tests-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let service = StubService(try state())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service,
                                  history: ProjectHistory(defaults: defaults), clientFactory: { _ in service })
        await store.refresh(); store.draft?.workflow.maxWorkerTurns = 5
        let draft = store.draft
        await store.requestProject(target)
        service.saveError = ServiceError(code: "denied", message: "保存失败")
        await store.resolveProjectSwitch(saveFirst: true)
        XCTAssertEqual(store.projectRoot, "/isolated/project")
        XCTAssertEqual(store.draft, draft)
        XCTAssertEqual(store.pendingProject, target)
        XCTAssertNil(service.sent?.enableProject)
        XCTAssertEqual(service.sent?.expectedRevision, "first")
    }

    private func inherited(globalRevision: String = "global-first") throws -> ServiceState {
        var incoming = try state(revision: "none")
        let global = SavedState(document: incoming.saved!.document, revision: globalRevision, error: nil)
        incoming.scope = "project"; incoming.source = "global"; incoming.globalRevision = globalRevision
        incoming.saved = SavedState(document: nil, revision: "none", error: nil)
        incoming.effective = global
        incoming.layers = SavedLayers(global: global, project: incoming.saved!)
        return incoming
    }

    @MainActor func testInheritedGlobalStateNeedsNoSaveOrProjectEnableAndConflictsOnGlobalChange() async throws {
        let service = StubService(try inherited())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh()
        XCTAssertFalse(store.needsSave); XCTAssertFalse(store.canSave); XCTAssertFalse(store.requiresProjectEnable)
        XCTAssertEqual(store.sourceLabel, "继承全局默认")
        XCTAssertEqual(store.draft?.workflow.activation, "automatic_project")
        store.draft?.workflow.maxWorkerTurns = 5
        service.response = try inherited(globalRevision: "global-external")
        await store.refresh()
        XCTAssertTrue(store.hasExternalChange); XCTAssertFalse(store.canSave)
        XCTAssertEqual(store.draft?.workflow.maxWorkerTurns, 5)
        XCTAssertEqual(store.globalRevision, "global-first")
    }

    @MainActor func testScopeSwitchRetainsDraftOnCancelAndReadFailureThenSavesExplicitGlobalScope() async throws {
        let service = StubService(try inherited())
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh(); store.draft?.workflow.maxWorkerTurns = 5
        await store.requestScope("global")
        XCTAssertEqual(store.pendingScope, "global"); XCTAssertEqual(store.scope, "project")
        store.cancelScopeSwitch(); XCTAssertEqual(store.draft?.workflow.maxWorkerTurns, 5)
        await store.requestScope("global")
        service.readError = ServiceError(code: "offline", message: "无法读取")
        await store.resolveScopeSwitch(saveFirst: false)
        XCTAssertEqual(store.scope, "project"); XCTAssertEqual(store.draft?.workflow.maxWorkerTurns, 5)
        service.readError = nil
        var global = try state()
        global.scope = "global"; global.source = "global"; global.globalRevision = "first"
        service.response = global
        await store.resolveScopeSwitch(saveFirst: false)
        XCTAssertEqual(store.scope, "global"); XCTAssertEqual(service.requestedScope, "global")
        store.draft?.workflow.maxWorkerTurns = 9
        service.saved = global.saved
        await store.save()
        XCTAssertEqual(service.sent?.scope, "global"); XCTAssertNil(service.sent?.enableProject)
        XCTAssertEqual(service.sent?.expectedGlobalRevision, "first")
    }

    @MainActor func testResetToInheritChecksBothRevisionsAndKeepsDraftOnFailure() async throws {
        var local = try state()
        local.scope = "project"; local.source = "project"; local.globalRevision = "g1"
        let service = StubService(local)
        let store = SettingsStore(projectRoot: "/isolated/project", client: service)
        await store.refresh(); store.draft?.workflow.activation = "manual"
        let previous = store.draft
        service.resetError = ServiceError(code: "denied", message: "重置失败")
        await store.resetToInherit()
        XCTAssertEqual(store.draft, previous); XCTAssertEqual(store.source, "project")
        XCTAssertEqual(service.resetSent?.expectedRevision, "first")
        XCTAssertEqual(service.resetSent?.expectedGlobalRevision, "g1")
        service.resetError = nil; service.resetResponse = try inherited()
        await store.resetToInherit()
        XCTAssertEqual(store.source, "global"); XCTAssertFalse(store.hasProjectOverride)
        XCTAssertFalse(store.canSave); XCTAssertFalse(store.requiresProjectEnable)
    }

}
