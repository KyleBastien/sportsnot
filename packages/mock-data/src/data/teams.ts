import type { NHLTeam } from '@sportsnot/types';

export const teams: NHLTeam[] = [
  {
    id: 22,
    name: 'Edmonton Oilers',
    abbreviation: 'EDM',
    teamName: 'Oilers',
    locationName: 'Edmonton',
    division: { id: 15, name: 'Pacific' },
    conference: { id: 5, name: 'Western' },
    logo: 'https://assets.nhle.com/logos/nhl/svg/EDM_light.svg',
  },
  {
    id: 13,
    name: 'Florida Panthers',
    abbreviation: 'FLA',
    teamName: 'Panthers',
    locationName: 'Florida',
    division: { id: 17, name: 'Atlantic' },
    conference: { id: 6, name: 'Eastern' },
    logo: 'https://assets.nhle.com/logos/nhl/svg/FLA_light.svg',
  },
  {
    id: 25,
    name: 'Dallas Stars',
    abbreviation: 'DAL',
    teamName: 'Stars',
    locationName: 'Dallas',
    division: { id: 15, name: 'Central' },
    conference: { id: 5, name: 'Western' },
    logo: 'https://assets.nhle.com/logos/nhl/svg/DAL_light.svg',
  },
  {
    id: 12,
    name: 'Carolina Hurricanes',
    abbreviation: 'CAR',
    teamName: 'Hurricanes',
    locationName: 'Carolina',
    division: { id: 18, name: 'Metropolitan' },
    conference: { id: 6, name: 'Eastern' },
    logo: 'https://assets.nhle.com/logos/nhl/svg/CAR_light.svg',
  },
] as const;
