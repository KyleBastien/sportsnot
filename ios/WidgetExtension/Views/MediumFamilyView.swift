import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct MediumFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 4) {
                    Text(entry.snapshot?.league.name ?? "SportsNot")
                        .font(.caption.bold())
                        .lineLimit(1)
                    Spacer()
                    if entry.totalPages > 1 {
                        Text("\(entry.pageIndex + 1)/\(entry.totalPages)")
                            .font(.system(size: 9).monospacedDigit())
                            .foregroundStyle(.tertiary)
                    }
                }
                if let snapshot = entry.snapshot {
                    let playingToday = snapshot.players
                        .filter { $0.gameId != nil }
                        .sorted(by: { $0.fantasyPoints > $1.fantasyPoints })
                    if playingToday.isEmpty {
                        Text("No players playing today")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } else {
                        let perPage = SnapshotTimelineProvider.playersPerPage(for: .systemMedium)
                        let start = min(entry.pageIndex * perPage, playingToday.count)
                        let end = min(start + perPage, playingToday.count)
                        let page = Array(playingToday[start..<end])
                        ForEach(page, id: \.id) { p in
                            HStack {
                                Text(p.teamAbbrev).font(.caption2.bold()).foregroundStyle(Color.accentColor)
                                    .frame(width: 34, alignment: .leading)
                                Text(p.name).font(.caption).lineLimit(1)
                                Spacer()
                                Text(String(format: "%.0f", p.fantasyPoints))
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.primary)
                            }
                        }
                    }
                } else {
                    Text(entry.errorMessage ?? "Loading…").font(.caption2).foregroundStyle(.secondary)
                }
            }

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                Text("Today").font(.caption.bold())
                if let games = entry.snapshot?.games, !games.isEmpty {
                    ForEach(games.prefix(4)) { g in
                        HStack(spacing: 4) {
                            Text("\(g.awayTeamAbbrev) \(g.awayScore)")
                                .font(.caption.monospacedDigit())
                            Text("@").font(.caption2).foregroundStyle(.secondary)
                            Text("\(g.homeTeamAbbrev) \(g.homeScore)")
                                .font(.caption.monospacedDigit())
                            Spacer()
                            gameStatus(g)
                        }
                    }
                } else {
                    Text("No games today").font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func gameStatus(_ g: WidgetSnapshot.Game) -> some View {
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
}
