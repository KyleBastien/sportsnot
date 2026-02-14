import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  useState,
  useEffect,
  type ReactNode,
} from 'react';
import { useAuthContext } from './AuthContext';

const MAX_COMPARE_PLAYERS = 4;

export interface ComparePlayer {
  playerId: number;
  name: string;
  teamAbbrev: string;
  position: string;
  headshot?: string;
  stats: Record<string, number>;
}

interface CompareContextValue {
  players: ComparePlayer[];
  isFull: boolean;
  addPlayer: (player: ComparePlayer) => void;
  removePlayer: (playerId: number) => void;
  clearAll: () => void;
}

const CompareContext = createContext<CompareContextValue | null>(null);

export function CompareProvider({ children }: { children: ReactNode }) {
  const [players, setPlayers] = useState<ComparePlayer[]>([]);
  const { user } = useAuthContext();

  // Reset state on sign-out
  useEffect(() => {
    if (!user) {
      setPlayers([]);
    }
  }, [user]);

  const isFull = players.length >= MAX_COMPARE_PLAYERS;

  const addPlayer = useCallback((player: ComparePlayer) => {
    setPlayers((prev) => {
      if (prev.length >= MAX_COMPARE_PLAYERS) return prev;
      if (prev.some((p) => p.playerId === player.playerId)) return prev;
      return [...prev, player];
    });
  }, []);

  const removePlayer = useCallback((playerId: number) => {
    setPlayers((prev) => prev.filter((p) => p.playerId !== playerId));
  }, []);

  const clearAll = useCallback(() => {
    setPlayers([]);
  }, []);

  const value = useMemo<CompareContextValue>(
    () => ({ players, isFull, addPlayer, removePlayer, clearAll }),
    [players, isFull, addPlayer, removePlayer, clearAll]
  );

  return (
    <CompareContext.Provider value={value}>{children}</CompareContext.Provider>
  );
}

export function useCompareContext() {
  const context = useContext(CompareContext);
  if (!context) {
    throw new Error('useCompareContext must be used within a CompareProvider');
  }
  return context;
}
