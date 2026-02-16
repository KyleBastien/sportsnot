/**
 * Mock Hooks Registry — centralizes all mock hook implementations.
 * Exposed through MockDataProvider context for transparent hook swapping.
 */
import {
  useMockMyLeagues,
  useMockLeagues,
  useMockLeague,
  useMockCreateLeague,
  useMockJoinLeague,
} from './hooks/useMockLeagues';
import {
  useMockDraft,
  useMockStartDraft,
  useMockMakePick,
  useMockLeagueMembers,
  useMockCompletedDrafts,
  useMockStartReDraft,
} from './hooks/useMockDraft';
import {
  useMockRoster,
  useMockLeagueRosters,
  useMockActivateIR,
  useMockDeactivateIR,
} from './hooks/useMockRoster';
import { useMockStandings } from './hooks/useMockStandings';
import { useMockScoringHistory } from './hooks/useMockScoringHistory';
import {
  useMockLiveGames,
  useMockLiveGamesTeamStats,
} from './hooks/useMockLiveGames';
import { useMockPlayoffBracket } from './hooks/useMockPlayoffBracket';
import {
  useMockPlayoffPlayers,
  useMockPlayoffTeams,
  useMockRegularSeasonPlayers,
} from './hooks/useMockNhlApi';
import { useMockAuth } from './hooks/useMockAuth';

export interface MockHooksRegistry {
  // Auth
  useMockAuth: typeof useMockAuth;
  // Leagues
  useMockMyLeagues: typeof useMockMyLeagues;
  useMockLeagues: typeof useMockLeagues;
  useMockLeague: typeof useMockLeague;
  useMockCreateLeague: typeof useMockCreateLeague;
  useMockJoinLeague: typeof useMockJoinLeague;
  // Draft
  useMockDraft: typeof useMockDraft;
  useMockStartDraft: typeof useMockStartDraft;
  useMockMakePick: typeof useMockMakePick;
  useMockLeagueMembers: typeof useMockLeagueMembers;
  useMockCompletedDrafts: typeof useMockCompletedDrafts;
  useMockStartReDraft: typeof useMockStartReDraft;
  // Roster
  useMockRoster: typeof useMockRoster;
  useMockLeagueRosters: typeof useMockLeagueRosters;
  useMockActivateIR: typeof useMockActivateIR;
  useMockDeactivateIR: typeof useMockDeactivateIR;
  // Standings & Scoring
  useMockStandings: typeof useMockStandings;
  useMockScoringHistory: typeof useMockScoringHistory;
  // Live Games
  useMockLiveGames: typeof useMockLiveGames;
  useMockLiveGamesTeamStats: typeof useMockLiveGamesTeamStats;
  // Bracket
  useMockPlayoffBracket: typeof useMockPlayoffBracket;
  // NHL API
  useMockPlayoffPlayers: typeof useMockPlayoffPlayers;
  useMockPlayoffTeams: typeof useMockPlayoffTeams;
  useMockRegularSeasonPlayers: typeof useMockRegularSeasonPlayers;
}

export const mockHooksRegistry: MockHooksRegistry = {
  useMockAuth,
  useMockMyLeagues,
  useMockLeagues,
  useMockLeague,
  useMockCreateLeague,
  useMockJoinLeague,
  useMockDraft,
  useMockStartDraft,
  useMockMakePick,
  useMockLeagueMembers,
  useMockCompletedDrafts,
  useMockStartReDraft,
  useMockRoster,
  useMockLeagueRosters,
  useMockActivateIR,
  useMockDeactivateIR,
  useMockStandings,
  useMockScoringHistory,
  useMockLiveGames,
  useMockLiveGamesTeamStats,
  useMockPlayoffBracket,
  useMockPlayoffPlayers,
  useMockPlayoffTeams,
  useMockRegularSeasonPlayers,
};
