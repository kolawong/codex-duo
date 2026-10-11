import Foundation

/// App-local navigation only. It never writes project files or routes Codex chats.
struct ProjectHistory {
    private let defaults: UserDefaults
    private let key = "codex-duo.recent-projects"
    private let legacyDomain: String
    init(defaults: UserDefaults = .standard, legacyDomain: String = "io.kola.fusion.menu") {
        self.defaults = defaults
        self.legacyDomain = legacyDomain
    }
    // Read-only migration recognition. A current value, including [], wins.
    var paths: [String] {
        defaults.stringArray(forKey: key)
            ?? defaults.persistentDomain(forName: legacyDomain)?[key] as? [String]
            ?? []
    }
    func remember(_ path: String) {
        defaults.set(Array(([path] + paths.filter { $0 != path }).prefix(12)), forKey: key)
    }
    static func validate(_ path: String) throws -> String {
        guard path.hasPrefix("/"), !path.split(separator: "/").contains("..") else {
            throw ServiceError(code: "invalid_project", message: "请选择现有的绝对路径目录。")
        }
        let url = URL(fileURLWithPath: path)
        let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else {
            throw ServiceError(code: "invalid_project", message: "请选择现有目录，不能选择符号链接。")
        }
        return url.resolvingSymlinksInPath().standardizedFileURL.path
    }
}
