import SwiftUI

/// What the badge shows and where it streams. Stored on the phone.
final class BadgeSettings: ObservableObject {
    @AppStorage("serverURL") var serverURL = "ws://192.168.0.142:8787"
    @AppStorage("ownerName") var ownerName = "Eric"
    @AppStorage("ownerCompany") var ownerCompany = "Vexi"
    @AppStorage("ownerTitle") var ownerTitle = ""
    @AppStorage("contact") var contact = ""          // email or handle, goes into the QR card
    @AppStorage("keywords") var keywords = "Vexi"    // comma-separated recognition hints
    @AppStorage("yawOffset") var yawOffset = 0.0     // degrees, calibrates the badge's forward direction

    var keywordList: [String] {
        keywords.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    /// A vCard for the badge's QR code.
    var vCard: String {
        var lines = ["BEGIN:VCARD", "VERSION:3.0", "FN:\(ownerName)", "ORG:\(ownerCompany)"]
        if !ownerTitle.isEmpty { lines.append("TITLE:\(ownerTitle)") }
        if contact.contains("@") { lines.append("EMAIL:\(contact)") } else if !contact.isEmpty { lines.append("NOTE:\(contact)") }
        lines.append("END:VCARD")
        return lines.joined(separator: "\n")
    }
}

struct SettingsView: View {
    @ObservedObject var settings: BadgeSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Badge") {
                    TextField("Name", text: $settings.ownerName)
                    TextField("Company", text: $settings.ownerCompany)
                    TextField("Title (optional)", text: $settings.ownerTitle)
                    TextField("Email or handle for the QR card", text: $settings.contact)
                        .textInputAutocapitalization(.never)
                }
                Section("Listening") {
                    TextField("Server", text: $settings.serverURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                    TextField("Words to recognise (comma-separated)", text: $settings.keywords)
                    Stepper(value: $settings.yawOffset, in: -180...180, step: 15) {
                        Text("Forward offset \(Int(settings.yawOffset))°")
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar { Button("Done") { dismiss() } }
        }
    }
}
