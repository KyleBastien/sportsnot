import type { NHLPlayoffSeries } from '@sportsnot/types';

export const bracket = [
  {
    "seriesCode": "A",
    "round": 1,
    "topSeedTeam": {
      "id": 10,
      "name": "Toronto Maple Leafs",
      "abbreviation": "TOR"
    },
    "bottomSeedTeam": {
      "id": 9,
      "name": "Ottawa Senators",
      "abbreviation": "OTT"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 2,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 10,
          "name": "Toronto Maple Leafs"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 2
        }
      },
      "bottomSeed": {
        "team": {
          "id": 9,
          "name": "Ottawa Senators"
        },
        "seriesRecord": {
          "wins": 2,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 10,
      "name": "Toronto Maple Leafs"
    }
  },
  {
    "seriesCode": "B",
    "round": 1,
    "topSeedTeam": {
      "id": 14,
      "name": "Tampa Bay Lightning",
      "abbreviation": "TBL"
    },
    "bottomSeedTeam": {
      "id": 13,
      "name": "Florida Panthers",
      "abbreviation": "FLA"
    },
    "topSeedWins": 1,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 14,
          "name": "Tampa Bay Lightning"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 13,
          "name": "Florida Panthers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 13,
      "name": "Florida Panthers"
    }
  },
  {
    "seriesCode": "C",
    "round": 1,
    "topSeedTeam": {
      "id": 15,
      "name": "Washington Capitals",
      "abbreviation": "WSH"
    },
    "bottomSeedTeam": {
      "id": 8,
      "name": "Montréal Canadiens",
      "abbreviation": "MTL"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 1,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 15,
          "name": "Washington Capitals"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      },
      "bottomSeed": {
        "team": {
          "id": 8,
          "name": "Montréal Canadiens"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 15,
      "name": "Washington Capitals"
    }
  },
  {
    "seriesCode": "D",
    "round": 1,
    "topSeedTeam": {
      "id": 12,
      "name": "Carolina Hurricanes",
      "abbreviation": "CAR"
    },
    "bottomSeedTeam": {
      "id": 1,
      "name": "New Jersey Devils",
      "abbreviation": "NJD"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 1,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 12,
          "name": "Carolina Hurricanes"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      },
      "bottomSeed": {
        "team": {
          "id": 1,
          "name": "New Jersey Devils"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 12,
      "name": "Carolina Hurricanes"
    }
  },
  {
    "seriesCode": "E",
    "round": 1,
    "topSeedTeam": {
      "id": 52,
      "name": "Winnipeg Jets",
      "abbreviation": "WPG"
    },
    "bottomSeedTeam": {
      "id": 19,
      "name": "St. Louis Blues",
      "abbreviation": "STL"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 3,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 52,
          "name": "Winnipeg Jets"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 3
        }
      },
      "bottomSeed": {
        "team": {
          "id": 19,
          "name": "St. Louis Blues"
        },
        "seriesRecord": {
          "wins": 3,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 52,
      "name": "Winnipeg Jets"
    }
  },
  {
    "seriesCode": "F",
    "round": 1,
    "topSeedTeam": {
      "id": 25,
      "name": "Dallas Stars",
      "abbreviation": "DAL"
    },
    "bottomSeedTeam": {
      "id": 21,
      "name": "Colorado Avalanche",
      "abbreviation": "COL"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 3,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 25,
          "name": "Dallas Stars"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 3
        }
      },
      "bottomSeed": {
        "team": {
          "id": 21,
          "name": "Colorado Avalanche"
        },
        "seriesRecord": {
          "wins": 3,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 25,
      "name": "Dallas Stars"
    }
  },
  {
    "seriesCode": "G",
    "round": 1,
    "topSeedTeam": {
      "id": 54,
      "name": "Vegas Golden Knights",
      "abbreviation": "VGK"
    },
    "bottomSeedTeam": {
      "id": 30,
      "name": "Minnesota Wild",
      "abbreviation": "MIN"
    },
    "topSeedWins": 4,
    "bottomSeedWins": 2,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 54,
          "name": "Vegas Golden Knights"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 2
        }
      },
      "bottomSeed": {
        "team": {
          "id": 30,
          "name": "Minnesota Wild"
        },
        "seriesRecord": {
          "wins": 2,
          "losses": 4
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 54,
      "name": "Vegas Golden Knights"
    }
  },
  {
    "seriesCode": "H",
    "round": 1,
    "topSeedTeam": {
      "id": 26,
      "name": "Los Angeles Kings",
      "abbreviation": "LAK"
    },
    "bottomSeedTeam": {
      "id": 22,
      "name": "Edmonton Oilers",
      "abbreviation": "EDM"
    },
    "topSeedWins": 2,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 26,
          "name": "Los Angeles Kings"
        },
        "seriesRecord": {
          "wins": 2,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 22,
          "name": "Edmonton Oilers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 2
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 22,
      "name": "Edmonton Oilers"
    }
  },
  {
    "seriesCode": "I",
    "round": 2,
    "topSeedTeam": {
      "id": 10,
      "name": "Toronto Maple Leafs",
      "abbreviation": "TOR"
    },
    "bottomSeedTeam": {
      "id": 13,
      "name": "Florida Panthers",
      "abbreviation": "FLA"
    },
    "topSeedWins": 3,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 10,
          "name": "Toronto Maple Leafs"
        },
        "seriesRecord": {
          "wins": 3,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 13,
          "name": "Florida Panthers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 3
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 13,
      "name": "Florida Panthers"
    }
  },
  {
    "seriesCode": "J",
    "round": 2,
    "topSeedTeam": {
      "id": 15,
      "name": "Washington Capitals",
      "abbreviation": "WSH"
    },
    "bottomSeedTeam": {
      "id": 12,
      "name": "Carolina Hurricanes",
      "abbreviation": "CAR"
    },
    "topSeedWins": 1,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 15,
          "name": "Washington Capitals"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 12,
          "name": "Carolina Hurricanes"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 12,
      "name": "Carolina Hurricanes"
    }
  },
  {
    "seriesCode": "K",
    "round": 2,
    "topSeedTeam": {
      "id": 52,
      "name": "Winnipeg Jets",
      "abbreviation": "WPG"
    },
    "bottomSeedTeam": {
      "id": 25,
      "name": "Dallas Stars",
      "abbreviation": "DAL"
    },
    "topSeedWins": 2,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 52,
          "name": "Winnipeg Jets"
        },
        "seriesRecord": {
          "wins": 2,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 25,
          "name": "Dallas Stars"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 2
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 25,
      "name": "Dallas Stars"
    }
  },
  {
    "seriesCode": "L",
    "round": 2,
    "topSeedTeam": {
      "id": 54,
      "name": "Vegas Golden Knights",
      "abbreviation": "VGK"
    },
    "bottomSeedTeam": {
      "id": 22,
      "name": "Edmonton Oilers",
      "abbreviation": "EDM"
    },
    "topSeedWins": 1,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 54,
          "name": "Vegas Golden Knights"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 22,
          "name": "Edmonton Oilers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 22,
      "name": "Edmonton Oilers"
    }
  },
  {
    "seriesCode": "M",
    "round": 3,
    "topSeedTeam": {
      "id": 12,
      "name": "Carolina Hurricanes",
      "abbreviation": "CAR"
    },
    "bottomSeedTeam": {
      "id": 13,
      "name": "Florida Panthers",
      "abbreviation": "FLA"
    },
    "topSeedWins": 1,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 12,
          "name": "Carolina Hurricanes"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 13,
          "name": "Florida Panthers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 13,
      "name": "Florida Panthers"
    }
  },
  {
    "seriesCode": "N",
    "round": 3,
    "topSeedTeam": {
      "id": 25,
      "name": "Dallas Stars",
      "abbreviation": "DAL"
    },
    "bottomSeedTeam": {
      "id": 22,
      "name": "Edmonton Oilers",
      "abbreviation": "EDM"
    },
    "topSeedWins": 1,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 25,
          "name": "Dallas Stars"
        },
        "seriesRecord": {
          "wins": 1,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 22,
          "name": "Edmonton Oilers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 1
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 22,
      "name": "Edmonton Oilers"
    }
  },
  {
    "seriesCode": "O",
    "round": 4,
    "topSeedTeam": {
      "id": 22,
      "name": "Edmonton Oilers",
      "abbreviation": "EDM"
    },
    "bottomSeedTeam": {
      "id": 13,
      "name": "Florida Panthers",
      "abbreviation": "FLA"
    },
    "topSeedWins": 2,
    "bottomSeedWins": 4,
    "matchupTeams": {
      "topSeed": {
        "team": {
          "id": 22,
          "name": "Edmonton Oilers"
        },
        "seriesRecord": {
          "wins": 2,
          "losses": 4
        }
      },
      "bottomSeed": {
        "team": {
          "id": 13,
          "name": "Florida Panthers"
        },
        "seriesRecord": {
          "wins": 4,
          "losses": 2
        }
      }
    },
    "isComplete": true,
    "seriesWinner": {
      "id": 13,
      "name": "Florida Panthers"
    }
  }
] as const satisfies readonly NHLPlayoffSeries[];
