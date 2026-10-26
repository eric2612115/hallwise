import SwiftUI
import UIKit

/// The camera when there is one, the photo library when there isn't (the simulator).
struct PhotoPicker: UIViewControllerRepresentable {
    let onPick: (UIImage?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        #if targetEnvironment(simulator)
        picker.sourceType = .photoLibrary  // the simulator's camera is a grey card
        #else
        picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
        #endif
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ vc: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(onPick: onPick) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onPick: (UIImage?) -> Void
        init(onPick: @escaping (UIImage?) -> Void) { self.onPick = onPick }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onPick(info[.originalImage] as? UIImage)
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { onPick(nil) }
    }
}

struct TakenPhoto: Identifiable {
    let id = UUID()
    let image: UIImage
}

extension UIImage {
    /// Upright, at most `maxSide` on the long edge: what gets sent and what gets cropped.
    func normalised(maxSide: CGFloat = 1280) -> UIImage {
        let scale = min(1, maxSide / max(size.width, size.height))
        let target = CGSize(width: size.width * scale, height: size.height * scale)
        return UIGraphicsImageRenderer(size: target, format: .init()).image { _ in draw(in: CGRect(origin: .zero, size: target)) }
    }

    /// The head, with some air around it, as a square.
    func face(in box: [Double], pad: CGFloat = 0.35) -> UIImage? {
        guard box.count == 4, let cg = cgImage else { return nil }
        let w = CGFloat(cg.width), h = CGFloat(cg.height)
        var r = CGRect(x: box[0] * w, y: box[1] * h, width: (box[2] - box[0]) * w, height: (box[3] - box[1]) * h)
        let side = max(r.width, r.height) * (1 + pad)
        r = CGRect(x: r.midX - side / 2, y: r.midY - side / 2, width: side, height: side)
            .intersection(CGRect(x: 0, y: 0, width: w, height: h))
        guard let crop = cg.cropping(to: r) else { return nil }
        return UIImage(cgImage: crop)
    }
}

/// The photo with Hallwise's guesses: who each face is. Change any with a tap, then keep.
struct PhotoMatchSheet: View {
    let photo: UIImage
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @Environment(\.dismiss) private var dismiss

    struct Face: Identifiable {
        let id: Int
        let box: [Double]
        var key: String
        let confidence: Double
        let why: String
    }

    @State private var faces: [Face] = []
    @State private var notes = ""
    @State private var state = "Looking…"
    @State private var done = false
    @State private var started = false

    private var people: [LiveModel.Person] { live.peopleOrder.compactMap { live.people[$0] } }

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(alignment: .leading, spacing: 14) {
                Text("Who's who")
                    .font(.system(size: 24, weight: .bold, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .padding(.top, 18)
                GeometryReader { geo in
                    let fit = fitted(photo.size, in: geo.size)
                    ZStack(alignment: .topLeading) {
                        Image(uiImage: photo)
                            .resizable()
                            .frame(width: fit.width, height: fit.height)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        ForEach(faces) { f in
                            let r = CGRect(x: f.box[0] * fit.width, y: f.box[1] * fit.height,
                                           width: (f.box[2] - f.box[0]) * fit.width, height: (f.box[3] - f.box[1]) * fit.height)
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(colour(for: f.key), lineWidth: 2.5)
                                .frame(width: r.width, height: r.height)
                                .offset(x: r.minX, y: r.minY)
                            Text(name(for: f.key))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(Theme.paper)
                                .padding(.horizontal, 6).padding(.vertical, 3)
                                .background(Capsule().fill(colour(for: f.key)))
                                .offset(x: r.minX, y: max(0, r.minY - 22))
                        }
                    }
                    .frame(width: fit.width, height: fit.height)
                    .frame(maxWidth: .infinity)
                }
                .frame(height: 260)
                if faces.isEmpty {
                    HStack(spacing: 8) {
                        if !done { ProgressView().tint(Theme.inkSoft) }
                        Text(state).font(.system(size: 15, design: .serif)).foregroundStyle(Theme.inkSoft)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 8) {
                            ForEach($faces) { $f in
                                HStack(spacing: 12) {
                                    if let crop = photo.face(in: f.box) {
                                        Image(uiImage: crop).resizable().scaledToFill()
                                            .frame(width: 44, height: 44).clipShape(Circle())
                                            .overlay(Circle().stroke(colour(for: f.key), lineWidth: 2))
                                    }
                                    Menu {
                                        ForEach(people) { p in
                                            Button(p.name) { f.key = p.id }
                                        }
                                        Button("Not a guest") { f.key = "" }
                                    } label: {
                                        HStack(spacing: 6) {
                                            Text(name(for: f.key)).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                                            Image(systemName: "chevron.up.chevron.down").font(.system(size: 12)).foregroundStyle(Theme.inkSoft)
                                        }
                                    }
                                    Spacer()
                                    if !f.key.isEmpty {
                                        Text("\(Int(f.confidence * 100))%").font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                                    }
                                }
                                .padding(.horizontal, 12)
                                .frame(height: 56)
                                .background(RoundedRectangle(cornerRadius: 12).fill(Theme.paperDeep))
                            }
                            if !notes.isEmpty {
                                Text(notes).font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                }
                Spacer(minLength: 0)
                HStack(spacing: 10) {
                    Button { dismiss() } label: {
                        Text("Discard").font(.system(size: 17, weight: .medium)).foregroundStyle(Theme.ink)
                            .frame(maxWidth: .infinity).frame(height: 56)
                            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
                            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    Button { keep() } label: {
                        Text("Keep faces").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.paper)
                            .frame(maxWidth: .infinity).frame(height: 56)
                            .background(RoundedRectangle(cornerRadius: 14).fill(faces.contains { !$0.key.isEmpty } ? Theme.accent : Theme.inkSoft))
                    }
                    .buttonStyle(.plain)
                    .disabled(!faces.contains { !$0.key.isEmpty })
                }
                .padding(.bottom, 16)
            }
            .padding(.horizontal, 20)
        }
        .preferredColorScheme(settings.colorScheme)
        .onAppear {
            // a plain Task: SwiftUI's .task is cancelled when the presentation re-lays out mid-request
            guard !started else { return }
            started = true
            Task { await match() }
        }
    }

    private func fitted(_ image: CGSize, in box: CGSize) -> CGSize {
        let k = min(box.width / image.width, box.height / image.height)
        return CGSize(width: image.width * k, height: image.height * k)
    }

    private func name(for key: String) -> String { key.isEmpty ? "Not a guest" : live.name(for: key) }
    private func colour(for key: String) -> Color { key.isEmpty ? Theme.inkSoft : live.color(for: key) }

    /// Send the photo with everyone's bearing; Spark says which face is which.
    private func match() async {
        guard let jpeg = photo.jpegData(compressionQuality: 0.8) else { state = "Could not read the photo"; done = true; return }
        let rid = live.recordingID.isEmpty ? (app.link.recordingID ?? "") : live.recordingID
        guard !rid.isEmpty else { state = "No recording to attach this to"; done = true; return }
        let who: [[String: Any]] = people.map { p in
            ["key": p.id, "name": p.name, "company": p.company,
             "bearing": live.relativeBearing(of: p, offset: settings.yawOffset) ?? 0]
        }
        do {
            let result = try await app.link.matchPhoto(base: settings.serverURL, recording: rid, jpeg: jpeg, people: who, hint: "")
            let list = result["faces"] as? [[String: Any]] ?? []
            faces = list.enumerated().map { i, f in
                Face(id: i, box: (f["box"] as? [Double]) ?? (f["box"] as? [NSNumber])?.map(\.doubleValue) ?? [],
                     key: f["person_key"] as? String ?? "", confidence: f["confidence"] as? Double ?? 0, why: f["why"] as? String ?? "")
            }.filter { $0.box.count == 4 }
            notes = result["notes"] as? String ?? ""
            if faces.isEmpty { state = "No faces found" }
        } catch {
            state = "Hallwise could not look: \(error.localizedDescription)"
        }
        done = true
    }

    private func keep() {
        let base = settings.serverURL
        for f in faces where !f.key.isEmpty {
            let crop = photo.face(in: f.box)
            live.setPhoto(crop, for: f.key)
            // and on the server, under the person, so the face is there the next evening they turn up
            if let crop {
                let key = live.indexKey(for: f.key)
                Task.detached { await Faces.upload(base: base, key: key, image: crop) }
            }
        }
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        dismiss()
    }
}

/// A face where there is one, the colour dot where there isn't.
struct FaceDot: View {
    @ObservedObject var live: LiveModel
    let key: String
    var size: CGFloat = 12
    var ring: Bool = false

    var body: some View {
        if let face = live.photos[key] {
            Image(uiImage: face).resizable().scaledToFill()
                .frame(width: size * 2, height: size * 2).clipShape(Circle())
                .overlay(Circle().stroke(ring ? live.color(for: key) : Theme.paper, lineWidth: 2))
        } else {
            Circle().fill(live.color(for: key)).frame(width: size, height: size)
        }
    }
}
