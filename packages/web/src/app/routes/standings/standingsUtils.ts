import { sumRoundPointsThroughRound } from '../../utils/roundUtils';

interface StandingsMemberLike {
  team_name: string;
  total_points: number;
  round_points?: Record<string, number> | null;
}

export type DisplayStandingsMember<T extends StandingsMemberLike> = T & {
  selected_total_points: number;
};

export function getSelectedTotalPoints(
  member: StandingsMemberLike,
  selectedRound: number,
  currentRound: number
): number {
  if (
    selectedRound === currentRound &&
    (!member.round_points || Object.keys(member.round_points).length === 0)
  ) {
    return member.total_points ?? 0;
  }

  return sumRoundPointsThroughRound(member.round_points, selectedRound);
}

export function buildStandingsMembers<T extends StandingsMemberLike>(
  members: T[],
  selectedRound: number,
  currentRound: number
): Array<DisplayStandingsMember<T>> {
  return members
    .map((member) => ({
      ...member,
      selected_total_points: getSelectedTotalPoints(
        member,
        selectedRound,
        currentRound
      ),
    }))
    .sort(
      (a, b) =>
        b.selected_total_points - a.selected_total_points ||
        a.team_name.localeCompare(b.team_name)
    );
}

export function getVisibleRoundNumbers(
  roundNumbers: number[],
  selectedRound: number
): number[] {
  return roundNumbers.filter((round) => round <= selectedRound);
}
