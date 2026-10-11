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

struct Workflow: Codable, Equatable {
    var activation: String
    var coordinatorMode: String
    var maxWorkerTurns: Int
    var maxParallelWorkers: Int = 1
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
        case plannerMode = "planner_mode"
        case plannerModel = "planner_model"
        case plannerReasoningEffort = "planner_reasoning_effort"
        case maxPlannerTurns = "max_planner_turns"
    }
    init(activation: String, coordinatorMode: String, maxWorkerTurns: Int, maxParallelWorkers: Int = 1) {
        self.activation = activation; self.coordinatorMode = coordinatorMode
        self.maxWorkerTurns = maxWorkerTurns; self.maxParallelWorkers = maxParallelWorkers
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        activation = try values.decode(String.self, forKey: .activation)
        coordinatorMode = try values.decode(String.self, forKey: .coordinatorMode)
        maxWorkerTurns = try values.decode(Int.self, forKey: .maxWorkerTurns)
        maxParallelWorkers = values.contains(.maxParallelWorkers)
            ? try values.decode(Int.self, forKey: .maxParallelWorkers) : 1
        plannerMode = values.contains(.plannerMode) ? try values.decode(String.self, forKey: .plannerMode) : "disabled"
        plannerModel = values.contains(.plannerModel) ? try values.decode(String.self, forKey: .plannerModel) : ""
        plannerReasoningEffort = values.contains(.plannerReasoningEffort) ? try values.decode(String.self, forKey: .plannerReasoningEffort) : ""
        maxPlannerTurns = values.contains(.maxPlannerTurns) ? try values.decode(Int.self, forKey: .maxPlannerTurns) : 1
    }
    var isValid: Bool {
        ["manual", "automatic_project"].contains(activation)
            && ["current_thread", "selected_model"].contains(coordinatorMode)
            && (1...10).contains(maxWorkerTurns) && (1...3).contains(maxParallelWorkers)
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

struct ServiceState: Decodable {
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
        case catalog, saved, workflow, error, scope, source, effective, layers
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
