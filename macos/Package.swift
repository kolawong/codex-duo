// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CodexDuoMenu",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "CodexDuoMenu", targets: ["CodexDuoMenu"])],
    targets: [
        .executableTarget(name: "CodexDuoMenu", resources: [.copy("Resources/bridge.py"), .copy("Resources/Brand")]),
        .testTarget(name: "CodexDuoMenuTests", dependencies: ["CodexDuoMenu"])
    ],
    swiftLanguageModes: [.v5]
)
