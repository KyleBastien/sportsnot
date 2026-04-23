import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct MediumFamilyView: View {
    let entry: SnapshotEntry

    private let columns = [
        GridItem(.flexible(), spacing: 8, alignment: .topLeading),
        GridItem(.flexible(), spacing: 8, alignment: .topLeading),
    ]

    var body: some View {
        let sections = WidgetScheduleLayout.pageSections(
            for: entry.snapshot,
            family: .systemMedium,
            pageIndex: entry.pageIndex
        )

        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text(entry.snapshot?.league.name ?? "SportsNot")
                    .font(.caption.bold())
                    .lineLimit(1)
                Spacer(minLength: 4)
                if entry.totalPages > 1 {
                    Text("\(entry.pageIndex + 1)/\(entry.totalPages)")
                        .font(.system(size: 9).monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
            }

            if let error = entry.errorMessage, entry.snapshot == nil {
                Text(error)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
            } else if sections.isEmpty {
                Text("No games today")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(sections.enumerated()), id: \.element.id) { index, section in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(WidgetScheduleLayout.headerText(for: section.game))
                            .font(.caption.bold())
                            .lineLimit(1)

                        let visibleTeams = WidgetScheduleLayout.visibleFantasyTeams(
                            for: section,
                            family: .systemMedium
                        )

                        if visibleTeams.isEmpty {
                            Text("No drafted teams in this game")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        } else {
                            LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
                                ForEach(visibleTeams) { team in
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(team.name)
                                            .font(.system(size: 10, weight: .semibold))
                                            .lineLimit(1)
                                            .minimumScaleFactor(0.75)

                                        ForEach(
                                            WidgetScheduleLayout.teamLines(
                                                for: team,
                                                family: .systemMedium
                                            ),
                                            id: \.self
                                        ) { line in
                                            Text(line)
                                                .font(.system(size: 9))
                                                .foregroundStyle(.secondary)
                                                .lineLimit(1)
                                                .minimumScaleFactor(0.7)
                                        }
                                    }
                                }
                            }

                            let hiddenTeams = WidgetScheduleLayout.hiddenFantasyTeamCount(
                                for: section,
                                family: .systemMedium
                            )
                            if hiddenTeams > 0 {
                                Text("+\(hiddenTeams) more teams")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }

                    if index < sections.count - 1 {
                        Divider()
                    }
                }
            }

            Spacer(minLength: 0)

            if let footer = WidgetScheduleLayout.footerText(for: entry) {
                Text(footer)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}
