# Draft Oracle cheat sheet

- League size: 4 manager(s)
- IR slots: off
- Roster demand per manager: 5 F / 3 D / 1 G (team)
- Replacement level (points): F 5.09 / D 3.00 / G 0.00

Sorted by value over replacement (VOR). The G rows are whole-team goalie
slots and carry no per-game quantiles.

> Combined R3+R4 draft: projections span the conference final and the conditional Cup Final (weighted by each team's advance probability). In teams.csv/parquet, e_goalie_points is combined R3+R4; e_wins, e_games, and e_shutout_wins remain R3-only.

| Rank | Pos | Player | Team | Proj | p10 | p50 | p90 | Repl | VOR | Status |
| ---: | :-- | :----- | :--- | ---: | --: | --: | --: | ---: | --: | :----- |
| 1 | G | COL | COL | 12.40 | - | - | - | 0.00 | 12.40 |  |
| 2 | G | CAR | CAR | 11.65 | - | - | - | 0.00 | 11.65 |  |
| 3 | G | MTL | MTL | 7.49 | - | - | - | 0.00 | 7.49 |  |
| 4 | F | Nathan MacKinnon | COL | 12.35 | 6.00 | 12.00 | 19.00 | 5.09 | 7.26 |  |
| 5 | G | VGK | VGK | 6.25 | - | - | - | 0.00 | 6.25 |  |
| 6 | F | Martin Necas | COL | 10.59 | 5.00 | 10.00 | 17.00 | 5.09 | 5.50 |  |
| 7 | D | Cale Makar | COL | 8.17 | 3.00 | 8.00 | 13.00 | 3.00 | 5.17 |  |
| 8 | D | Lane Hutson | MTL | 6.03 | 2.00 | 5.00 | 11.00 | 3.00 | 3.03 |  |
| 9 | F | Sebastian Aho | CAR | 8.07 | 3.00 | 8.00 | 13.00 | 5.09 | 2.99 |  |
| 10 | D | Shayne Gostisbehere | CAR | 5.68 | 2.00 | 5.00 | 10.00 | 3.00 | 2.68 |  |
| 11 | F | Seth Jarvis | CAR | 7.44 | 3.00 | 7.00 | 12.00 | 5.09 | 2.35 |  |
| 12 | F | Nick Suzuki | MTL | 7.40 | 3.00 | 7.00 | 13.00 | 5.09 | 2.31 |  |
| 13 | F | Jack Eichel | VGK | 6.98 | 3.00 | 6.00 | 12.00 | 5.09 | 1.89 |  |
| 14 | F | Jackson Blake | CAR | 6.79 | 3.00 | 6.00 | 11.00 | 5.09 | 1.71 |  |
| 15 | D | Sam Malinski | COL | 4.41 | 1.00 | 4.00 | 8.00 | 3.00 | 1.41 |  |
| 16 | F | Mitch Marner | VGK | 6.44 | 2.00 | 6.00 | 11.00 | 5.09 | 1.36 |  |
| 17 | F | Andrei Svechnikov | CAR | 6.32 | 2.00 | 6.00 | 11.00 | 5.09 | 1.24 |  |
| 18 | F | Cole Caufield | MTL | 6.22 | 2.00 | 6.00 | 11.00 | 5.09 | 1.14 |  |
| 19 | F | Gabriel Landeskog | COL | 6.22 | 2.00 | 6.00 | 10.00 | 5.09 | 1.13 |  |
| 20 | F | Nikolaj Ehlers | CAR | 6.18 | 2.00 | 6.00 | 11.00 | 5.09 | 1.10 |  |
| 21 | D | K'Andre Miller | CAR | 3.88 | 1.00 | 4.00 | 7.00 | 3.00 | 0.88 |  |
| 22 | D | Shea Theodore | VGK | 3.69 | 1.00 | 3.00 | 7.00 | 3.00 | 0.69 |  |
| 23 | D | Keaton Middleton | COL | 3.61 | 1.00 | 3.00 | 6.00 | 3.00 | 0.61 |  |
| 24 | F | Mark Stone | VGK | 5.69 | 2.00 | 5.00 | 10.00 | 5.09 | 0.60 |  |
| 25 | F | Brock Nelson | COL | 5.63 | 2.00 | 5.00 | 10.00 | 5.09 | 0.55 |  |
| 26 | D | Devon Toews | COL | 3.50 | 1.00 | 3.00 | 6.00 | 3.00 | 0.50 |  |
| 27 | F | Artturi Lehkonen | COL | 5.58 | 2.00 | 5.00 | 9.00 | 5.09 | 0.50 |  |
| 28 | F | Logan Stankoven | CAR | 5.57 | 2.00 | 5.00 | 10.00 | 5.09 | 0.48 |  |
| 29 | F | Juraj Slafkovský | MTL | 5.55 | 2.00 | 5.00 | 10.00 | 5.09 | 0.46 |  |
| 30 | F | T.J. Tynan | COL | 5.51 | 2.00 | 5.00 | 9.00 | 5.09 | 0.43 |  |
| 31 | F | Taylor Hall | CAR | 5.30 | 2.00 | 5.00 | 9.00 | 5.09 | 0.22 |  |
| 32 | D | Alexander Nikishin | CAR | 3.16 | 1.00 | 3.00 | 6.00 | 3.00 | 0.16 |  |
| 33 | D | Brent Burns | COL | 3.14 | 1.00 | 3.00 | 6.00 | 3.00 | 0.14 |  |
| 34 | D | Noah Dobson | MTL | 3.11 | 1.00 | 3.00 | 6.00 | 3.00 | 0.11 |  |
| 35 | D | Domenick Fensore | CAR | 3.10 | 1.00 | 3.00 | 6.00 | 3.00 | 0.10 |  |
| 36 | F | Alex Barre-Boulet | COL | 5.16 | 2.00 | 5.00 | 9.00 | 5.09 | 0.07 |  |
| 37 | F | Valeri Nichushkin | COL | 5.09 | 2.00 | 5.00 | 9.00 | 5.09 | 0.00 |  |
| 38 | D | Ronan Seeley | CAR | 3.00 | 1.00 | 3.00 | 6.00 | 3.00 | 0.00 |  |
| 39 | F | Pavel Dorofeyev | VGK | 5.06 | 2.00 | 5.00 | 9.00 | 5.09 | -0.02 |  |
| 40 | D | Sean Walker | CAR | 2.93 | 1.00 | 3.00 | 6.00 | 3.00 | -0.07 |  |
| 41 | D | Josh Manson | COL | 2.86 | 1.00 | 3.00 | 5.00 | 3.00 | -0.14 |  |
| 42 | D | Jack Ahcan | COL | 2.64 | 1.00 | 2.00 | 5.00 | 3.00 | -0.36 |  |
| 43 | D | Noah Hanifin | VGK | 2.64 | 0.00 | 2.00 | 5.00 | 3.00 | -0.36 |  |
| 44 | D | Mike Matheson | MTL | 2.57 | 0.00 | 2.00 | 5.00 | 3.00 | -0.43 |  |
| 45 | F | Tristen Nielsen | COL | 4.56 | 1.00 | 4.00 | 8.00 | 5.09 | -0.53 |  |
| 46 | D | Charles Alexis Legault | CAR | 2.42 | 0.00 | 2.00 | 5.00 | 3.00 | -0.58 |  |
| 47 | F | Jason Polin | COL | 4.50 | 1.00 | 4.00 | 8.00 | 5.09 | -0.59 |  |
| 48 | D | Samuel Girard | COL | 2.31 | 0.00 | 2.00 | 4.00 | 3.00 | -0.69 |  |
| 49 | D | Jalen Chatfield | CAR | 2.26 | 0.00 | 2.00 | 4.00 | 3.00 | -0.74 |  |
| 50 | D | Jaccob Slavin | CAR | 2.08 | 0.00 | 2.00 | 4.00 | 3.00 | -0.92 |  |
| 51 | D | Mike Reilly | CAR | 2.08 | 0.00 | 2.00 | 4.00 | 3.00 | -0.92 |  |
| 52 | F | Felix Unger Sorum | CAR | 4.14 | 1.00 | 4.00 | 7.00 | 5.09 | -0.94 |  |
| 53 | D | Ilya Solovyov | COL | 1.99 | 0.00 | 2.00 | 4.00 | 3.00 | -1.01 |  |
| 54 | D | Joel Nystrom | CAR | 1.94 | 0.00 | 2.00 | 4.00 | 3.00 | -1.06 |  |
| 55 | D | Kaiden Guhle | MTL | 1.94 | 0.00 | 2.00 | 4.00 | 3.00 | -1.06 |  |
| 56 | D | Alexandre Carrier | MTL | 1.90 | 0.00 | 2.00 | 4.00 | 3.00 | -1.10 |  |
| 57 | D | Dylan Coghlan | VGK | 1.87 | 0.00 | 2.00 | 4.00 | 3.00 | -1.13 |  |
| 58 | D | David Reinbacher | MTL | 1.87 | 0.00 | 2.00 | 4.00 | 3.00 | -1.13 |  |
| 59 | F | Tomas Hertl | VGK | 3.90 | 1.00 | 3.00 | 7.00 | 5.09 | -1.19 |  |
| 60 | F | Justin Robidas | CAR | 3.86 | 1.00 | 4.00 | 7.00 | 5.09 | -1.23 |  |
| 61 | F | Ivan Barbashev | VGK | 3.85 | 1.00 | 3.00 | 7.00 | 5.09 | -1.23 |  |
| 62 | D | Jaycob Megna | VGK | 1.76 | 0.00 | 2.00 | 4.00 | 3.00 | -1.24 |  |
| 63 | D | Ben Hutton | VGK | 1.72 | 0.00 | 1.00 | 4.00 | 3.00 | -1.28 |  |
| 64 | F | Josiah Slavin | CAR | 3.76 | 1.00 | 3.00 | 7.00 | 5.09 | -1.32 |  |
| 65 | D | Zach Whitecloud | VGK | 1.57 | 0.00 | 1.00 | 3.10 | 3.00 | -1.43 |  |
| 66 | D | Brayden McNabb | VGK | 1.55 | 0.00 | 1.00 | 3.00 | 3.00 | -1.45 |  |
| 67 | F | Jordan Staal | CAR | 3.63 | 1.00 | 3.00 | 7.00 | 5.09 | -1.45 |  |
| 68 | F | Ivan Ivan | COL | 3.59 | 1.00 | 3.00 | 6.00 | 5.09 | -1.50 |  |
| 69 | F | Ivan Demidov | MTL | 3.56 | 1.00 | 3.00 | 7.00 | 5.09 | -1.52 |  |
| 70 | F | Parker Kelly | COL | 3.41 | 1.00 | 3.00 | 6.00 | 5.09 | -1.68 |  |
| 71 | F | Victor Olofsson | COL | 3.41 | 1.00 | 3.00 | 6.00 | 5.09 | -1.68 |  |
| 72 | F | Raphael Lavoie | VGK | 3.37 | 1.00 | 3.00 | 6.00 | 5.09 | -1.72 |  |
| 73 | F | Skyler Brind'Amour | CAR | 3.31 | 1.00 | 3.00 | 6.00 | 5.09 | -1.77 |  |
| 74 | D | Adam Engstrom | MTL | 1.21 | 0.00 | 1.00 | 3.00 | 3.00 | -1.79 |  |
| 75 | D | Kaedan Korczak | VGK | 1.19 | 0.00 | 1.00 | 3.00 | 3.00 | -1.81 |  |
| 76 | D | Jeremy Lauzon | VGK | 1.14 | 0.00 | 1.00 | 3.00 | 3.00 | -1.86 |  |
| 77 | D | Jayden Struble | MTL | 1.12 | 0.00 | 1.00 | 3.00 | 3.00 | -1.88 |  |
| 78 | F | William Karlsson | VGK | 3.20 | 1.00 | 3.00 | 6.00 | 5.09 | -1.88 |  |
| 79 | F | Taylor Makar | COL | 3.20 | 1.00 | 3.00 | 6.00 | 5.09 | -1.88 |  |
| 80 | F | Logan O'Connor | COL | 3.11 | 1.00 | 3.00 | 6.00 | 5.09 | -1.98 |  |
| 81 | F | Bradly Nadeau | CAR | 3.05 | 1.00 | 3.00 | 6.00 | 5.09 | -2.04 |  |
| 82 | F | Kai Uchacz | VGK | 3.04 | 1.00 | 3.00 | 6.00 | 5.09 | -2.04 |  |
| 83 | D | Arber Xhekaj | MTL | 0.91 | 0.00 | 1.00 | 2.00 | 3.00 | -2.08 |  |
| 84 | F | Ross Colton | COL | 2.99 | 1.00 | 3.00 | 6.00 | 5.09 | -2.09 |  |
| 85 | F | Jordan Martinook | CAR | 2.96 | 1.00 | 3.00 | 6.00 | 5.09 | -2.13 |  |
| 86 | F | Alex Newhook | MTL | 2.92 | 1.00 | 3.00 | 6.00 | 5.09 | -2.16 |  |
| 87 | F | Jack Drury | COL | 2.89 | 1.00 | 3.00 | 5.00 | 5.09 | -2.19 |  |
| 88 | F | Jonas Rondbjerg | VGK | 2.84 | 1.00 | 2.00 | 6.00 | 5.09 | -2.24 |  |
| 89 | F | Braeden Bowman | VGK | 2.79 | 1.00 | 2.00 | 5.10 | 5.09 | -2.30 |  |
| 90 | F | Brett Howden | VGK | 2.74 | 0.00 | 2.00 | 5.00 | 5.09 | -2.34 |  |
| 91 | F | Tanner Laczynski | VGK | 2.72 | 1.00 | 2.00 | 5.00 | 5.09 | -2.36 |  |
| 92 | F | Reilly Smith | VGK | 2.61 | 0.00 | 2.00 | 5.00 | 5.09 | -2.47 |  |
| 93 | F | Joshua Roy | MTL | 2.60 | 0.00 | 2.00 | 5.00 | 5.09 | -2.48 |  |
| 94 | F | Alexandre Texier | MTL | 2.59 | 0.00 | 2.00 | 5.00 | 5.09 | -2.49 |  |
| 95 | F | Oliver Kapanen | MTL | 2.51 | 0.00 | 2.00 | 5.00 | 5.09 | -2.58 |  |
| 96 | F | Zachary Bolduc | MTL | 2.47 | 0.00 | 2.00 | 5.00 | 5.09 | -2.61 |  |
| 97 | F | Patrik Laine | MTL | 2.45 | 0.00 | 2.00 | 5.00 | 5.09 | -2.64 |  |
| 98 | F | Kirby Dach | MTL | 2.44 | 0.00 | 2.00 | 5.00 | 5.09 | -2.64 |  |
| 99 | F | Florian Xhekaj | MTL | 2.39 | 0.00 | 2.00 | 5.00 | 5.09 | -2.70 |  |
| 100 | F | Brendan Gallagher | MTL | 2.32 | 0.00 | 2.00 | 5.00 | 5.09 | -2.77 |  |
| 101 | F | Jake Evans | MTL | 2.27 | 0.00 | 2.00 | 5.00 | 5.09 | -2.81 |  |
| 102 | F | Owen Beck | MTL | 2.14 | 0.00 | 2.00 | 4.00 | 5.09 | -2.94 |  |
| 103 | F | Josh Anderson | MTL | 2.04 | 0.00 | 2.00 | 4.00 | 5.09 | -3.04 |  |
| 104 | F | Phillip Danault | MTL | 2.04 | 0.00 | 2.00 | 4.00 | 5.09 | -3.04 |  |
| 105 | F | Jared Davidson | MTL | 1.96 | 0.00 | 2.00 | 4.00 | 5.09 | -3.12 |  |
| 106 | F | Mark Jankowski | CAR | 1.95 | 0.00 | 2.00 | 4.00 | 5.09 | -3.13 |  |
| 107 | F | Gavin Brindley | COL | 1.95 | 0.00 | 2.00 | 4.00 | 5.09 | -3.14 |  |
| 108 | F | Joel Kiviranta | COL | 1.92 | 0.00 | 2.00 | 4.00 | 5.09 | -3.16 |  |
| 109 | F | Colton Sissons | VGK | 1.89 | 0.00 | 2.00 | 4.00 | 5.09 | -3.19 |  |
| 110 | F | Brandon Saad | VGK | 1.88 | 0.00 | 2.00 | 4.00 | 5.09 | -3.21 |  |
| 111 | F | Jesperi Kotkaniemi | CAR | 1.84 | 0.00 | 2.00 | 4.00 | 5.09 | -3.25 |  |
| 112 | F | Eric Robinson | CAR | 1.79 | 0.00 | 2.00 | 4.00 | 5.09 | -3.30 |  |
| 113 | F | Cole Reinhardt | VGK | 1.74 | 0.00 | 1.00 | 4.00 | 5.09 | -3.34 |  |
| 114 | F | William Carrier | CAR | 1.71 | 0.00 | 1.00 | 4.00 | 5.09 | -3.37 |  |
| 115 | F | Alexander Holtz | VGK | 1.70 | 0.00 | 1.00 | 4.00 | 5.09 | -3.39 |  |
| 116 | F | Samuel Blais | MTL | 1.66 | 0.00 | 1.00 | 4.00 | 5.09 | -3.43 |  |
| 117 | F | Zakhar Bardakov | COL | 1.55 | 0.00 | 1.00 | 3.00 | 5.09 | -3.53 |  |
| 118 | F | Keegan Kolesar | VGK | 1.33 | 0.00 | 1.00 | 3.00 | 5.09 | -3.75 |  |
| 119 | F | Joseph Veleno | MTL | 1.31 | 0.00 | 1.00 | 3.00 | 5.09 | -3.78 |  |
