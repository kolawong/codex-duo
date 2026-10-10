// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "FusionMenu",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "FusionMenu", targets: ["FusionMenu"])],
    targets: [
        .executableTarget(name: "FusionMenu", resources: [.copy("Resources/bridge.py"), .copy("Resources/Brand")]),
        .testTarget(name: "FusionMenuTests", dependencies: ["FusionMenu"])
    ],
    swiftLanguageModes: [.v5]
)
