# Broken Treaties Atlas

An interactive network of more than 1,000 treaties signed between 1648 and 2026, and a record of which ones were broken or were followed by war between their own signatories.

Open `index.html` in a browser to use it. It is a single self-contained page (the data is embedded), so it also works on GitHub Pages: *Settings → Pages → Deploy from a branch → `main` / root*.

## What the explorer shows

- **Network.** Countries linked by the treaties they signed together. Line width reflects how much two countries signed together; large multilateral treaties are down-weighted (each pair in a treaty with *k* parties gets 1/(*k*−1)). Orange links mark pairs that signed together and later fought each other; red links mark pairs that shared a treaty with a documented breach.
- **Timeline.** Treaties per decade, split by what happened next.
- **Ledger.** Every treaty, searchable, with its parties, any documented breach, the later wars between its signatories, and a source link.
- **Controls.** Era or year range, treaty type, the war window (1–50 years) and a "major wars only" switch. All counts update live.

## Method

Each treaty is tested against two measurable rules, plus one interpretive flag kept apart from the counts.

| Rule | Definition |
|---|---|
| **Documented breach** | The treaty was violated, repudiated or abrogated before its intended end. For alliances 1815–2018 this is ATOP's own coding (`TERM = 2`, ended by violation or abrogation). For curated treaties it is a dated event with a source. A later war alone is not a breach. |
| **War between signatories** | Two parties fought each other in an interstate war that began within *N* years of signing (default 20). For peace treaties only former enemies count (pairs across the two sides). For alliances any two members count, once both had joined, whether or not the alliance was still in force. The war the treaty ended is excluded. |
| **Historian-flagged** | Treaties widely argued to have set up a later war without being breached directly, such as Versailles and the Second World War or Frankfurt (1871) and the First. These are interpretations, shown with a one-line rationale and never added to the breach or war counts. |

"Major" wars are great-power wars or wars with roughly 10,000+ battle deaths.

## Coverage

| Period | Treaties | Wars |
|---|---|---|
| 1648–1814 | Hand-curated: major peace treaties and alliances | Hand-curated: major interstate wars |
| 1815–2018 | **Alliances:** ATOP 5.1 (all formal alliances, non-aggression, neutrality and consultation pacts). **Peace and security treaties:** hand-curated | 1816–2003: COW Inter-State War v4.0 |
| 2019–2026 | Hand-curated peace, ceasefire and security agreements only | 2004–2026: hand-curated |

Known gaps and caveats:

- Coverage before 1815 is limited to major treaties and is not directly comparable with the systematic ATOP data after 1815.
- Alliances signed after 2018 are not included (ATOP 5.1 ends there).
- Only interstate wars count. Civil wars and wars against non-state groups are outside the scope, although a few post-2003 records include non-state parties (for example the Donetsk and Luhansk entities) alongside states.
- Multilateral peace settlements list their principal signatories, not every state that signed.
- ATOP does not say which member violated an alliance, so ATOP-coded breaches carry no "by" field.
- Each curated treaty has a `verification` field: `fetched` or `checked` (verified against a source), `search` (confirmed by search results), or `knowledge` (not yet checked against a source).

## Repository layout

```
index.html                  the explorer (generated; do not edit by hand)
scripts/
  build.py                  merges all sources, computes the rules, writes data/data.json and index.html
  template.html             the explorer page; build.py injects the data
  rda_reader.py             minimal R .rda reader used to export the COW war data from peacesciencer
data/
  data.json                 merged dataset (generated)
  atop_names.json           common names for well-known ATOP alliances (e.g. 3180 → NATO)
  curated/                  hand-curated records (edit these)
    treaties_1648_1815.json   treaties_1816_2026.json
    wars_1648_1815.json       wars_2004_2026.json
    cow_war_names.json        names and "major" flags for COW war numbers
    countries_extra*.json     codes for entities outside the COW state list (e.g. HRE, PLC, VNC)
  raw/
    atop/                   ATOP 5.1 alliance- and member-level CSVs
    cow/                    COW Inter-State War v4.0 (dyad-year) and state list
```

## Rebuilding

Requires Python 3 and pandas.

```
python scripts/build.py
```

The script prints a validation report (unknown country codes, broken war references, merged duplicates) and rewrites `data/data.json` and `index.html`.

### Adding or correcting a treaty

Edit the JSON in `data/curated/` and rebuild. Country codes are Correlates of War abbreviations (`UKG`, `FRN`, `GMY` for Prussia/Germany, `AUH` for Austria, `TUR` for the Ottoman Empire/Turkey, `RUS` for Russia/USSR); codes for other entities live in `countries_extra*.json`. A treaty record looks like this (party lists shortened):

```json
{
  "id": "t_versailles_1919",
  "name": "Treaty of Versailles",
  "date": "1919-06-28",
  "year": 1919,
  "type": "peace",
  "parties": ["FRN", "GMY", "ITA", "JPN", "UKG", "USA"],
  "sides": [["FRN", "ITA", "JPN", "UKG", "USA"], ["GMY"]],
  "ends_war": "cow_106",
  "violated": {"is": true, "year": 1935, "by": ["GMY"], "how": "Germany repudiated the military clauses in 1935 and remilitarised the Rhineland in 1936."},
  "judgment": {"led_to": "cow_139", "rationale": "Many historians argue the settlement's terms fed German revisionism."},
  "summary": "Peace with Germany: territorial losses, reparations, disarmament and a demilitarised Rhineland.",
  "source_url": "https://en.wikipedia.org/wiki/Treaty_of_Versailles",
  "verification": "checked"
}
```

`type` is one of `peace`, `armistice`, `ceasefire`, `alliance`, `nonaggression`, `guarantee`, `normalization` or `other`. Curated alliances that duplicate an ATOP record (same year and members, or listed in `MANUAL_DUP` in `build.py`) are merged into the ATOP record rather than counted twice.

## Data sources and citations

The raw data belongs to its producers and is redistributed here for research use. Please cite them if you use this project.

- **ATOP 5.1.** Leeds, Brett Ashley, Jeffrey M. Ritter, Sara McLaughlin Mitchell, and Andrew G. Long. 2002. "Alliance Treaty Obligations and Provisions, 1815–1944." *International Interactions* 28: 237–260. Data and codebook: [atopdata.org](http://www.atopdata.org/). The CSVs here are the unmodified ATOP 5.1 alliance (`atop5_1a`) and member (`atop5_1m`) files.
- **COW Inter-State War v4.0.** Sarkees, Meredith Reid, and Frank Wayman. 2010. *Resort to War: 1816–2007.* Washington, DC: CQ Press. [correlatesofwar.org](https://correlatesofwar.org/)
- **COW State System Membership (v2016).** Correlates of War Project. 2017. "State System Membership List, v2016."
- **peacesciencer.** Miller, Steven V. 2022. "peacesciencer: An R Package for Quantitative Peace Science Research." *Conflict Management and Peace Science* 39(6): 755–779. The two COW CSVs were exported from the versions packaged in peacesciencer.
- **Curated records** were compiled from standard references (mainly Wikipedia and Britannica); each record carries its own `source_url`.
