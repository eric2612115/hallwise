import SwiftUI

/// What the badge shows and where it streams. Stored on the phone.
final class BadgeSettings: ObservableObject {
    @AppStorage("serverURL") var serverURL = "ws://192.168.0.142:8790"
    @AppStorage("ownerName") var ownerName = "Eric"
    @AppStorage("ownerCompany") var ownerCompany = "Hallwise"
    @AppStorage("ownerTitle") var ownerTitle = ""
    @AppStorage("contact") var contact = ""          // email or handle, goes into the QR card
    @AppStorage("keywords") var keywords = "Hallwise"  // comma-separated recognition hints
    @AppStorage("eventName") var eventName = ""      // tonight's event, stored with each recording
    @AppStorage("venue") var venue = ""
    @AppStorage("yawOffset") var yawOffset = 0.0     // degrees, calibrates the badge's forward direction
    @AppStorage("appearance") var appearance = Theme.Appearance.system.rawValue
    @AppStorage("followRecording") var followRecording = ""  // debug: watch this recording instead of capturing

    var colorScheme: ColorScheme? { Theme.Appearance(rawValue: appearance)?.colorScheme }

    var keywordList: [String] {
        keywords.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    /// A corrected word becomes a recognition hint for the next recording.
    func remember(_ word: String) {
        let w = word.trimmingCharacters(in: .whitespaces)
        guard !w.isEmpty, !keywordList.contains(where: { $0.caseInsensitiveCompare(w) == .orderedSame }) else { return }
        keywords = (keywordList + [w]).joined(separator: ", ")
    }

    func forget(_ word: String) {
        keywords = keywordList.filter { $0 != word }.joined(separator: ", ")
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
                Section("Tonight") {
                    TextField("Event (e.g. ETH Taipei afterparty)", text: $settings.eventName)
                    TextField("Venue", text: $settings.venue)
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
                Section("Debug") {
                    TextField("Follow recording id (no capture)", text: $settings.followRecording)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section("Appearance") {
                    Picker("Paper", selection: $settings.appearance) {
                        Text("System").tag(Theme.Appearance.system.rawValue)
                        Text("Light").tag(Theme.Appearance.light.rawValue)
                        Text("Dark").tag(Theme.Appearance.dark.rawValue)
                    }
                    .pickerStyle(.segmented)
                }
            }
            .scrollContentBackground(.hidden)
            .background(PaperBackground())
            .tint(Theme.accent)
            .navigationTitle("Settings")
            .toolbar { Button("Done") { dismiss() } }
        }
    }
}
