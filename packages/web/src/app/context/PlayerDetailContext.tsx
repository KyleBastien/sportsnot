import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

interface PlayerDetailContextValue {
  selectedPlayerId: number | null;
  openPlayerDetail: (playerId: number) => void; // eslint-disable-line no-unused-vars
  closePlayerDetail: () => void;
}

const PlayerDetailContext = createContext<PlayerDetailContextValue | null>(null);

export function PlayerDetailProvider({ children }: { children: ReactNode }) {
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null);

  const openPlayerDetail = useCallback((playerId: number) => {
    setSelectedPlayerId(playerId);
  }, []);

  const closePlayerDetail = useCallback(() => {
    setSelectedPlayerId(null);
  }, []);

  const value = useMemo<PlayerDetailContextValue>(
    () => ({ selectedPlayerId, openPlayerDetail, closePlayerDetail }),
    [selectedPlayerId, openPlayerDetail, closePlayerDetail]
  );

  return (
    <PlayerDetailContext.Provider value={value}>
      {children}
    </PlayerDetailContext.Provider>
  );
}

export function usePlayerDetailContext() {
  const context = useContext(PlayerDetailContext);
  if (!context) {
    throw new Error(
      'usePlayerDetailContext must be used within a PlayerDetailProvider'
    );
  }
  return context;
}
