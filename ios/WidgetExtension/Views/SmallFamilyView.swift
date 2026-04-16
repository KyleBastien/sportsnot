import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct SmallFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let error = entry.errorMessage {
                Text(error).font(.caption2).foregroundStyle(.secondary)
            } else if let snapshot = entry.snapshot {
                Text(snapshot.league.name)
                    .font(.caption.bold())
                    .lineLimit(1)
                let total = snapshot.players.reduce(0) { $0 + $1.fantasyPoints }
                Text(String(format: "%.0f pts", total))
                    .font(.title3.bold().monospacedDigit())
                if let top = snapshot.players.max(by: { $0.fantasyPoints < $1.fantasyPoints }) {
                    Text("Top: \(top.name)")
                        .font(.caption2)
                        .lineLimit(1)
                }
                if let liveCount = liveGameCount(snapshot) {
                    Label("\(liveCount) live", systemImage: "dot.radiowaves.left.and.right")
                        .font(.caption2)
                        .foregroundStyle(.green)
                }
            } else {
                Text("SportsNot").font(.headline)
                Text("Waiting for today's slate").font(.caption2).foregroundStyle(.secondary)
            }
            if entry.staleFromCache {
                Text("• cached").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func liveGameCount(_ s: WidgetSnapshot) -> Int? {
        let c = s.games.filter { $0.state == "LIVE" }.count
        return c == 0 ? nil : c
    }
}
