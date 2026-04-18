import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct LargeFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(entry.snapshot?.league.name ?? "SportsNot").font(.headline).lineLimit(1)
                Spacer()
                if let totalLabel = myTeamTotalLabel() {
                    Text(totalLabel)
                        .font(.subheadline.monospacedDigit().bold())
                }
            }
            if let team = entry.myTeamName, !team.isEmpty {
                Text(team)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text("Today's games").font(.caption).foregroundStyle(.secondary)
            if let games = entry.snapshot?.games, !games.isEmpty {
                ForEach(games.prefix(6)) { g in
                    HStack(spacing: 6) {
                        Text("\(g.awayTeamAbbrev) \(g.awayScore)")
                            .font(.caption.monospacedDigit())
                        Text("@").font(.caption2).foregroundStyle(.secondary)
                        Text("\(g.homeTeamAbbrev) \(g.homeScore)")
                            .font(.caption.monospacedDigit())
                        Spacer()
                        statusLabel(for: g)
                    }
                }
            } else {
                Text("No games today").font(.caption).foregroundStyle(.secondary)
            }

            Divider()

            HStack {
                Text("Drafted players").font(.caption).foregroundStyle(.secondary)
                Spacer()
                if entry.totalPages > 1 {
                    Text("\(entry.pageIndex + 1)/\(entry.totalPages)")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
            }
            if let snapshot = entry.snapshot {
                let playingToday = snapshot.players
                    .filter { $0.gameId != nil }
                    .sorted(by: { $0.fantasyPoints > $1.fantasyPoints })
                if playingToday.isEmpty {
                    Text("No players playing today").font(.caption).foregroundStyle(.secondary)
                } else {
                    let perPage = SnapshotTimelineProvider.playersPerPage(for: .systemLarge)
                    let start = min(entry.pageIndex * perPage, playingToday.count)
                    let end = min(start + perPage, playingToday.count)
                    let page = Array(playingToday[start..<end])
                    ForEach(page, id: \.id) { p in
                        HStack {
                            Text(p.teamAbbrev).font(.caption2.bold()).foregroundStyle(Color.accentColor)
                                .frame(width: 36, alignment: .leading)
                            Text(p.name).font(.caption).lineLimit(1)
                            Spacer()
                            Text(p.ownedByTeamName).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            Text(String(format: "%.0f", p.fantasyPoints))
                                .font(.caption.monospacedDigit())
                                .frame(width: 44, alignment: .trailing)
                        }
                    }
                }
            }
            if entry.staleFromCache {
                Text("• showing cached snapshot").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func statusLabel(for g: WidgetSnapshot.Game) -> some View {
        switch g.state {
        case "LIVE":
            Text("P\(g.period ?? 0) \(g.timeRemaining ?? "")")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.green)
        case "FINAL", "OFF":
            Text("F").font(.caption2).foregroundStyle(.secondary)
        default:
            Text(g.state).font(.caption2).foregroundStyle(.secondary)
        }
    }

    /// Sum of fantasy points for players owned by the user's team in this
    /// league. Falls back to the league-wide total if the user has not yet
    /// linked a team (i.e. before tapping Feature on iOS widget post-update).
    private func myTeamTotalLabel() -> String? {
        guard let snapshot = entry.snapshot else { return nil }
        if let team = entry.myTeamName, !team.isEmpty {
            let total = snapshot.players
                .filter { $0.ownedByTeamName == team }
                .reduce(0) { $0 + $1.fantasyPoints }
            return String(format: "%.0f pts", total)
        }
        let total = snapshot.players.reduce(0) { $0 + $1.fantasyPoints }
        return String(format: "%.0f pts", total)
    }
}
