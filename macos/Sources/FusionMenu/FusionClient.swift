import Foundation
import Darwin

protocol FusionServing {
    func state() async throws -> ServiceState
    func save(_ body: SaveBody) async throws -> SavedState
    func state(scope: String) async throws -> ServiceState
    func reset(_ body: SaveBody) async throws -> ServiceState
}

extension FusionServing {
    func state(scope: String) async throws -> ServiceState { try await state() }
    func reset(_ body: SaveBody) async throws -> ServiceState {
        throw ServiceError(code: "unsupported", message: "服务不支持继承重置，请更新应用。")
    }
}

struct BridgeEnvelope<Value: Decodable>: Decodable {
    var ok: Bool
    var data: Value?
    var error: ServiceError?
}

private final class OutputBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var bytes = Data()
    private var exceeded = false
    func append(_ data: Data) {
        lock.lock(); defer { lock.unlock() }
        let available = max(0, 2 * 1024 * 1024 - bytes.count)
        bytes.append(data.prefix(available))
        if data.count > available { exceeded = true }
    }
    func result() -> (Data, Bool) {
        lock.lock(); defer { lock.unlock() }
        return (bytes, exceeded)
    }
}

struct FusionClient: FusionServing {
    let projectRoot: String
    private struct Request: Encodable { var operation: String; var body: SaveBody?; var scope: String? }

    func state() async throws -> ServiceState {
        try await call(operation: "state", body: nil, as: ServiceState.self)
    }
    func state(scope: String) async throws -> ServiceState {
        try await call(operation: "state", body: nil, scope: scope, as: ServiceState.self)
    }
    func reset(_ body: SaveBody) async throws -> ServiceState {
        try await call(operation: "reset", body: body, as: ServiceState.self)
    }
    func save(_ body: SaveBody) async throws -> SavedState {
        try await call(operation: "save", body: body, as: SavedState.self)
    }

    private func call<Value: Decodable>(operation: String, body: SaveBody?, scope: String? = nil, as type: Value.Type) async throws -> Value {
        let input = try JSONEncoder().encode(Request(operation: operation, body: body, scope: scope))
        let root = projectRoot
        // Process waits and pipe I/O are kept off the main actor.
        let output = try await Task.detached(priority: .userInitiated) {
            let resource = Bundle.main.resourceURL?.appendingPathComponent("bridge.py")
            let bridge = resource.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
                ?? Bundle.module.url(forResource: "bridge", withExtension: "py")
            guard let bridge else { throw ServiceError(code: "bridge_unavailable", message: "应用缺少内置的配置服务，请重新构建应用。") }
            let environment = Self.environment()
            let python = try Self.python(environment: environment)
            return try Self.run(executable: python, arguments: ["-I", "-B", bridge.path, "--project-root", root],
                                input: input, environment: environment, timeout: 25)
        }.value
        do {
            let response = try JSONDecoder().decode(BridgeEnvelope<Value>.self, from: output.stdout)
            if !response.ok { throw response.error ?? ServiceError(code: "bridge_failure", message: "配置服务出错了，但没有说明原因。") }
            guard output.exitCode == 0, let value = response.data else {
                throw ServiceError(code: "invalid_response", message: "配置服务返回的数据不完整。")
            }
            return value
        } catch let error as ServiceError { throw error }
        catch {
            let detail = String(data: output.stderr.prefix(1200), encoding: .utf8) ?? ""
            throw ServiceError(code: "invalid_response", message: "看不懂配置服务的返回内容。\(detail.isEmpty ? "" : "\n" + detail)")
        }
    }

    private static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (env["PATH"] ?? "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env
    }

    private static func python(environment: [String: String]) throws -> String {
        let names = ["python3", "python3.14", "python3.13", "python3.12", "python3.11"]
        var candidates = [String]()
        for directory in (environment["PATH"] ?? "").split(separator: ":") where directory.hasPrefix("/") {
            for name in names {
                let path = String(directory) + "/" + name
                if !candidates.contains(path), FileManager.default.isExecutableFile(atPath: path) { candidates.append(path) }
            }
        }
        let deadline = Date().addingTimeInterval(6)
        for candidate in candidates {
            let remaining = deadline.timeIntervalSinceNow
            guard remaining > 0 else { break }
            if let result = try? run(executable: candidate,
                                    arguments: ["-I", "-c", "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"],
                                    input: Data(), environment: environment, timeout: min(3, remaining)), result.exitCode == 0 {
                return candidate
            }
        }
        throw ServiceError(code: "python_unavailable", message: "需要 Python 3.11 或更新版本。安装后重新打开应用。")
    }

    struct ProcessOutput { var stdout: Data; var stderr: Data; var exitCode: Int32 }
    static func run(executable: String, arguments: [String], input: Data,
                            environment: [String: String], timeout: TimeInterval) throws -> ProcessOutput {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.environment = environment
        process.currentDirectoryURL = URL(fileURLWithPath: "/")
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        _ = fcntl(stdin.fileHandleForWriting.fileDescriptor, F_SETNOSIGPIPE, 1)
        process.standardInput = stdin; process.standardOutput = stdout; process.standardError = stderr
        let exited = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in exited.signal() }
        try process.run()
        let group = DispatchGroup()
        let out = OutputBuffer(), err = OutputBuffer()
        for (handle, buffer) in [(stdout.fileHandleForReading, out), (stderr.fileHandleForReading, err)] {
            group.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                defer { try? handle.close(); group.leave() }
                while let chunk = try? handle.read(upToCount: 16 * 1024), !chunk.isEmpty { buffer.append(chunk) }
            }
        }
        // Writing must share the deadline too: a stalled Python startup may not read stdin.
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            defer { try? stdin.fileHandleForWriting.close(); group.leave() }
            try? stdin.fileHandleForWriting.write(contentsOf: input)
        }
        if exited.wait(timeout: .now() + timeout) == .timedOut {
            process.terminate()
            if exited.wait(timeout: .now() + 1) == .timedOut {
                kill(process.processIdentifier, SIGKILL)
                _ = exited.wait(timeout: .now() + 2)
            }
            throw ServiceError(code: "timeout", message: "配置服务响应超时。请确认 Python 和 Codex CLI 可用，然后点刷新重试。")
        }
        guard group.wait(timeout: .now() + 2) == .success else {
            throw ServiceError(code: "timeout", message: "配置服务的返回被中断了，请点刷新重试。")
        }
        let (output, tooLarge) = out.result(), (errors, errorsTooLarge) = err.result()
        guard !tooLarge, !errorsTooLarge else { throw ServiceError(code: "output_limit", message: "配置服务返回的内容过大，已停止读取。") }
        return ProcessOutput(stdout: output, stderr: errors, exitCode: process.terminationStatus)
    }
}
