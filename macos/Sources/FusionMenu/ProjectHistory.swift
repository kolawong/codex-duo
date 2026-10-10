import Foundation

/// App-local navigation only. It never writes project files or routes Codex chats.
struct ProjectHistory {
    private let defaults: UserDefaults
    private let key = "codex-duo.recent-projects"
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    var paths: [String] { defaults.stringArray(forKey: key) ?? [] }
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
