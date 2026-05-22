import { sumRoundPointsThroughRound } from '../../utils/roundUtils';

interface StandingsMemberLike {
  team_name: string;
  total_points: number;
  round_points?: Record<string, number> | null;
}

export type DisplayStandingsMember<T extends StandingsMemberLike> = T & {
  selected_total_points: number;
};

function hasRoundPoints(
  roundPoints: Record<string, number> | null | undefined
): boolean {
  return Object.keys(roundPoints ?? {}).length > 0;
}

function usesCurrentTotalPoints(
  selectedRound: number,
  currentRound: number,
  roundPoints: Record<string, number> | null | undefined
): boolean {
  return selectedRound === currentRound && !hasRoundPoints(roundPoints);
}

export function getSelectedTotalPoints(
  member: StandingsMemberLike,
  selectedRound: number,
  currentRound: number
): number {
  if (
    usesCurrentTotalPoints(selectedRound, currentRound, member.round_points)
  ) {
    return member.total_points;
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
