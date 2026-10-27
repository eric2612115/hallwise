import SwiftUI

/// The close button every sheet in the app wears: a round "xmark" in the top-right corner, in the header's paper
/// circle, with a 44 pt hit area. It is pinned (a safe-area bar, not part of the scrolling content), so a long
/// list underneath never takes it away, and it is the sure way out when a swipe down only scrolls the list.
struct SheetCloseButton: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Button { dismiss() } label: {
            Image(systemName: "xmark")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Theme.paperDeep))
                .overlay(Circle().stroke(Theme.rule, lineWidth: 0.5))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Close")
    }
}

private struct ClosableSheet: ViewModifier {
    func body(content: Content) -> some View {
        content.safeAreaBar(edge: .top, spacing: 0) {
            HStack(spacing: 0) {
                Spacer(minLength: 0)
                SheetCloseButton()
            }
            .padding(.top, 10)
            .padding(.trailing, 16)
            .padding(.bottom, 2)
        }
    }
}

extension View {
    /// One look for every sheet we present (system sheets such as the share sheet, the camera and the calendar
    /// editor have their own): the close button, the drag indicator, and the detents. Put it on the sheet's
    /// content, inside the `.sheet { }` closure. Content that has its own top padding can keep less of it: the
    /// bar already holds the first 56 pt.
    func closableSheet(_ detents: Set<PresentationDetent> = [.large]) -> some View {
        modifier(ClosableSheet())
            .presentationDetents(detents)
            .presentationDragIndicator(.visible)
    }
}
