import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react';
import { BotAutoPickRunner } from './bot/BotAutoPickRunner';
import { mockHooksRegistry, type MockHooksRegistry } from './mockHooksRegistry';
import {
  getInitialState,
  type MockAction,
  mockReducer,
  type MockState,
} from './mockDataCore';

export * from './mockDataCore';

interface MockDataContextValue {
  state: MockState;
  dispatch: Dispatch<MockAction>;
  hooks: MockHooksRegistry;
}

const MockDataContext = createContext<MockDataContextValue | null>(null);

export function MockDataProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(mockReducer, undefined, getInitialState);

  return (
    <MockDataContext.Provider
      value={{ state, dispatch, hooks: mockHooksRegistry }}
    >
      <BotAutoPickRunner />
      {children}
    </MockDataContext.Provider>
  );
}

const EMPTY_MOCK_STATE: MockState = {
  leagues: [],
  currentLeague: null,
  draftState: null,
  completedDrafts: [],
  rosters: {},
  rosterHistory: {},
  simulationDate: '',
  currentRound: 1,
  roundComplete: false,
  seasonComplete: false,
  playerStats: {},
  mockUser: { id: '', email: '', displayName: '', avatarUrl: '' },
};

const EMPTY_CONTEXT: MockDataContextValue = {
  state: EMPTY_MOCK_STATE,
  dispatch: () => {},
  hooks: mockHooksRegistry,
};

export function useMockData(): MockDataContextValue {
  const context = useContext(MockDataContext);
  return context ?? EMPTY_CONTEXT;
}
