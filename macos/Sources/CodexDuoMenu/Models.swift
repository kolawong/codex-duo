import Foundation

struct ServiceError: Codable, Equatable, LocalizedError {
    var code: String
    var message: String
    var errorDescription: String? { message }
}

struct ModelOption: Codable, Equatable, Identifiable {
    var id: String
    var name: String
    var description: String
    var efforts: [String]
    var defaultEffort: String
    enum CodingKeys: String, CodingKey {
        case id, name, description, efforts
        case defaultEffort = "default_effort"
    }
}

struct Catalog: Codable, Equatable {
    var models: [ModelOption]
    var fingerprint: String
}

struct ModelChoice: Codable, Equatable {
    var model: String
    var reasoningEffort: String
    enum CodingKeys: String, CodingKey {
        case model
        case reasoningEffort = "reasoning_effort"
    }
    mutating func selectModel(_ id: String, catalog: Catalog?) {
        model = id
        guard let option = catalog?.models.first(where: { $0.id == id }) else { return }
        if !option.efforts.contains(reasoningEffort) { reasoningEffort = option.defaultEffort }
    }
    func isValid(in catalog: Catalog?) -> Bool {
        catalog?.models.contains { $0.id == model && $0.efforts.contains(reasoningEffort) } == true
    }
}

struct Selection: Codable, Equatable {
    var coordinator: ModelChoice
    var worker: ModelChoice
}

struct WorkerPreset: Decodable, Identifiable {
    var id: String
    var name: String
    var selection: Selection
    var workerOnly: Bool? = nil
    enum CodingKeys: String, CodingKey {
        case id, name, selection
        case workerOnly = "worker_only"
    }
}

enum AgentActivity: String, CaseIterable {
    case conservative, balanced, aggressive

    var title: String {
        switch self {
        case .conservative: "保守"
        case .balanced: "均衡"
        case .aggressive: "积极"
        }
    }
    var description: String {
        switch self {
        case .conservative: "优先自己完成；任务复杂或耗时且适合交接时派代理。"
        case .balanced: "简单任务自己完成；有明确收益时派代理。"
        case .aggressive: "更主动委派可独立执行的工作；琐碎任务仍自己完成。"
        }
    }
    var sliderValue: Double { Double(Self.allCases.firstIndex(of: self)!) }
    static func at(_ value: Double) -> Self? {
        guard value.isFinite, value.rounded() == value, (0...2).contains(value) else { return nil }
        return allCases[Int(value)]
    }
}

enum WorkerTier: String, CaseIterable, Identifiable {
    case light, standard, complex
    var id: String { rawValue }
    var title: String {
        switch self { case .light: "轻量"; case .standard: "标准"; case .complex: "复杂" }
    }
}

struct Workflow: Codable, Equatable {
    var activation: String
    var coordinatorMode: String
    var maxWorkerTurns: Int
    var maxParallelWorkers: Int = 1
    var agentActivity: String = "balanced"
    var workerStrategy: String = "fixed"
    var workerProfiles: [String: ModelChoice] = [:]
    var plannerMode: String = "disabled"
    var plannerModel: String = ""
    var plannerReasoningEffort: String = ""
    var maxPlannerTurns: Int = 1
    var plannerChoice: ModelChoice {
        get { ModelChoice(model: plannerModel, reasoningEffort: plannerReasoningEffort) }
        set { plannerModel = newValue.model; plannerReasoningEffort = newValue.reasoningEffort }
    }
    static let initial = Workflow(activation: "manual", coordinatorMode: "current_thread", maxWorkerTurns: 3)
    enum CodingKeys: String, CodingKey {
        case activation
        case coordinatorMode = "coordinator_mode"
        case maxWorkerTurns = "max_worker_turns"
        case maxParallelWorkers = "max_parallel_workers"
        case agentActivity = "agent_activity"
        case workerStrategy = "worker_strategy"
        case workerProfiles = "worker_profiles"
        case plannerMode = "planner_mode"
        case plannerModel = "planner_model"
        case plannerReasoningEffort = "planner_reasoning_effort"
        case maxPlannerTurns = "max_planner_turns"
    }
    init(activation: String, coordinatorMode: String, maxWorkerTurns: Int, maxParallelWorkers: Int = 1, agentActivity: String = "balanced") {
        self.activation = activation; self.coordinatorMode = coordinatorMode
        self.maxWorkerTurns = maxWorkerTurns; self.maxParallelWorkers = maxParallelWorkers
        self.agentActivity = agentActivity
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        activation = try values.decode(String.self, forKey: .activation)
        coordinatorMode = try values.decode(String.self, forKey: .coordinatorMode)
        maxWorkerTurns = try values.decode(Int.self, forKey: .maxWorkerTurns)
        maxParallelWorkers = values.contains(.maxParallelWorkers)
            ? try values.decode(Int.self, forKey: .maxParallelWorkers) : 1
        agentActivity = values.contains(.agentActivity) ? try values.decode(String.self, forKey: .agentActivity) : "balanced"
        guard AgentActivity(rawValue: agentActivity) != nil else {
            throw DecodingError.dataCorruptedError(forKey: .agentActivity, in: values,
                debugDescription: "Unsupported agent activity")
        }
        workerStrategy = values.contains(.workerStrategy) ? try values.decode(String.self, forKey: .workerStrategy) : "fixed"
        workerProfiles = values.contains(.workerProfiles) ? try values.decode([String: ModelChoice].self, forKey: .workerProfiles) : [:]
        plannerMode = values.contains(.plannerMode) ? try values.decode(String.self, forKey: .plannerMode) : "disabled"
        plannerModel = values.contains(.plannerModel) ? try values.decode(String.self, forKey: .plannerModel) : ""
        plannerReasoningEffort = values.contains(.plannerReasoningEffort) ? try values.decode(String.self, forKey: .plannerReasoningEffort) : ""
        maxPlannerTurns = values.contains(.maxPlannerTurns) ? try values.decode(Int.self, forKey: .maxPlannerTurns) : 1
    }
    var hasCompleteWorkerProfiles: Bool {
        Set(workerProfiles.keys) == Set(WorkerTier.allCases.map(\.rawValue))
    }
    func workerChoicesValid(in catalog: Catalog?) -> Bool {
        (workerProfiles.isEmpty && workerStrategy == "fixed")
            || (hasCompleteWorkerProfiles && workerProfiles.values.allSatisfy { $0.isValid(in: catalog) })
    }
    var isValid: Bool {
        ["fixed", "adaptive"].contains(workerStrategy)
            && ((workerProfiles.isEmpty && workerStrategy == "fixed") || hasCompleteWorkerProfiles)
            && ["manual", "automatic_project"].contains(activation)
            && ["current_thread", "selected_model"].contains(coordinatorMode)
            && (1...10).contains(maxWorkerTurns) && (1...3).contains(maxParallelWorkers)
            && AgentActivity(rawValue: agentActivity) != nil
            && ["disabled", "plan_only"].contains(plannerMode) && (1...3).contains(maxPlannerTurns)
            && (plannerMode == "disabled" || (!plannerModel.isEmpty && !plannerReasoningEffort.isEmpty))
    }
}

struct SavedDocument: Codable, Equatable {
    var selection: Selection
    var workflow: Workflow?
    var savedAt: String
    enum CodingKeys: String, CodingKey {
        case selection, workflow
        case savedAt = "saved_at"
    }
}

struct ProjectOptIn: Codable, Equatable {
    var enabled: Bool
    var error: ServiceError?
}

struct SavedState: Codable, Equatable {
    var document: SavedDocument?
    var revision: String
    var error: ServiceError?
    var projectOptIn: ProjectOptIn? = nil
    enum CodingKeys: String, CodingKey {
        case document, revision, error
        case projectOptIn = "project_opt_in"
    }
}

struct SavedLayers: Decodable {
    var global: SavedState
    var project: SavedState
}

struct ExecutionStatus: Decodable, Equatable {
    struct WaitingWorkstream: Decodable, Equatable, Identifiable {
        var id: String
        var reason: String
    }
    var handoffID: String
    var taskID: String
    var goal: String
    var updatedAt: String
    var configuredMaxParallelWorkers: Int
    var reportedHostCapacity: Int
    var effectiveMaxParallelWorkers: Int
    var occupiedWorkers: Int
    var queuedWorkstreams: Int
    var readyWorkstreams: [String]
    var waitingWorkstreams: [WaitingWorkstream]
    enum CodingKeys: String, CodingKey {
        case handoffID = "handoff_id", taskID = "task_id", goal
        case updatedAt = "updated_at"
        case configuredMaxParallelWorkers = "configured_max_parallel_workers"
        case reportedHostCapacity = "reported_host_capacity"
        case effectiveMaxParallelWorkers = "effective_max_parallel_workers"
        case occupiedWorkers = "occupied_workers", queuedWorkstreams = "queued_workstreams"
        case readyWorkstreams = "ready_workstreams", waitingWorkstreams = "waiting_workstreams"
        case remainingWorkerTurns = "remaining_worker_turns"
    }
    var remainingWorkerTurns: Int
    var capacitySummary: String {
        "配置上限：\(configuredMaxParallelWorkers) · 已报告容量：\(reportedHostCapacity) · 有效上限：\(effectiveMaxParallelWorkers)"
    }
    var queueSummary: String {
        "占用（已预留/执行中）：\(occupiedWorkers) · 等待：\(queuedWorkstreams) · 剩余执行次数：\(remainingWorkerTurns)"
    }
}

struct ServiceState: Decodable {
    var suggestedWorkerProfiles: [String: ModelChoice]? = nil
    var executionStatus: ExecutionStatus? = nil
    var presets: [WorkerPreset]? = nil
    var scope: String? = nil
    var source: String? = nil
    var globalRevision: String? = nil
    var effective: SavedState? = nil
    var layers: SavedLayers? = nil
    var catalog: Catalog?
    var defaultSelection: Selection?
    var saved: SavedState?
    var workflow: Workflow?
    var error: ServiceError?
    var projectOptIn: ProjectOptIn? = nil
    var projectRoot: String?
    enum CodingKeys: String, CodingKey {
        case catalog, saved, workflow, error, scope, source, effective, layers, presets
        case suggestedWorkerProfiles = "suggested_worker_profiles"
        case executionStatus = "execution_status"
        case globalRevision = "global_revision"
        case projectOptIn = "project_opt_in"
        case defaultSelection = "default"
        case projectRoot = "project_root"
    }
}

struct Draft: Equatable {
    var selection: Selection
    var workflow: Workflow
}

struct SaveBody: Encodable {
    var selection: Selection
    var workflow: Workflow
    var expectedRevision: String
    var enableProject: Bool? = nil
    var scope: String? = nil
    var expectedGlobalRevision: String? = nil
    enum CodingKeys: String, CodingKey {
        case selection, workflow
        case expectedRevision = "expected_revision"
        case enableProject = "enable_project"
        case scope
        case expectedGlobalRevision = "expected_global_revision"
    }
}
