# PlanIT Control: Team Guide

How we split the work, how we use git, and how we make decisions.
Data shapes and endpoints live in `api/CONTRACT.md`. For exact field names
and JSON, the running API's `/docs` page is the final word, because it is
generated from the code.

## The project

PlanIT Control, for the Sperry Tech challenge at SwampHacks XII. A real-time
platform that pulls scattered environmental hazard data into one risk picture
per utility job site: a 0 to 10 explainable hazard score, live lightning
alerts, a 6 PM next-day safety briefing, crew photo hazard reports, and a
supervisor map ranking sites by risk.

Judging is a live expo: judges walk up and use the app. A working demo
matters more than the writeup, and everyone should be able to explain their
own part.

## Stack

| Tool | Job in the app |
| --- | --- |
| Python + FastAPI | Backend API |
| Tiger Data (PostgreSQL + time-series) | Sites, readings, forecasts, scores, alerts, reports |
| Gemini (`gemini-3.8-flash`) | Ask-a-question, 6 PM briefing text, photo hazard tagging |
| Auth0 | Logins with two roles: `crew` and `supervisor` |
| DeepSpace | Real-time events only (alerts and new reports appear instantly) |
| Vultr | Hosting the API and the frontend |
| GoDaddy | Domain pointed at the deployed frontend |

## Team and ownership

| Person | GitHub | Role | Owns |
| --- | --- | --- | --- |
| Sid | `SidVal123` | Data + ML models | `get_data/`, `model/`, `db/` (except `db/hazard_report.sql`) |
| Alan | `fanggs` | API, Gemini, real-time alerts, deploy | `api/` (except Aryan's files below), `jobs/`, `page/realtime/`, the DeepSpace bridge (`planit-realtime`) |
| Aryan | `nimma-aryan` | Crew-report backend, supervisor dashboard | `api/schemas/hazard_report.py`, `api/services/hazard_report_service.py`, report and photo routes, `db/hazard_report.sql`, supervisor files in `page/`, shared styles |
| Isaiah | `IsaiahCN` | Crew screens, demo readiness | `page/crew/` |

What each role delivers:

- **Sid:** 60 real sites from EIA-860M, live weather and forecasts, historical
  NOAA and GBIF data, the database tables, validation after every load, and
  the two trained models. Done when every site has a real, explainable score.
- **Alan:** the API and its contract, the Gemini layer (ask, briefings, photo
  tagging), the lightning rule and real-time events, and the deploy. Done when
  a judge can open the domain on their phone and watch a lightning alert fire.
- **Aryan:** report and photo endpoints, report storage, Auth0 role checks on
  the API, the shared design system, and the supervisor dashboard. Done when
  a report submitted from a phone shows up on the supervisor map.
- **Isaiah:** the crew screens (login, alerts with countdown, report form,
  score breakdown, briefing), phone testing, link checks, and the Devpost
  draft. Done when a stranger can use the crew side without help.

Stick to your own files. If you need a small change in someone else's, tell
them first, keep it small, and pull right before and push right after.

## Git

1. Pull before you start working.
2. Commit small, with a message that says what changed.
3. Before pushing: commit, pull, then push.
4. Make sure it runs before you push.
5. Never commit `.env` or API keys.
6. Never use `git push --force`.
7. Merge conflict? Ask the person whose code it is.

## Changing a shared decision

`api/CONTRACT.md` and this guide are our base, not frozen. When something
doesn't fit:

1. Bring it up in the team chat: what you found and what it affects.
2. Agree on a fix. The owner of that area decides.
3. The owner updates the file and pushes.
4. The owner posts "updated, sync" in the chat.

## Issues

Problems in someone else's code go in a GitHub issue assigned to the owner,
not in the chat.

- **Title:** what's wrong, in a few words.
- **Body:** the file and line, what happens, what should happen, and a
  suggested fix.
- **Fixing it:** reference the issue in the commit message, like
  `fix alert time zone (fixes #12)`. GitHub closes the issue when that
  commit reaches `main`.
- **Not a bug?** Reply on the issue explaining why. The person who opened it
  closes it or brings it to the team chat.
- **Still broken after the fix?** Reopen the issue with a comment.

## Engineering rules

1. **The database produces the numbers.** Gemini can write a query or a
   sentence, but every temperature, distance, and score comes from a row or
   a trained model.
2. **Every score is explainable.** Never show a bare 0 to 10; show which
   factors pushed it and by how much.
3. **Record where data came from** on every row: source, URL, retrieved_at.
4. **Validate after every load.** An empty column that throws no error is
   worse than a crash.
5. **Missing is never zero.** A dead feed shows "no data", never "safe".
6. **Deploy the frontend, not just the API**, and click every link before
   the expo.

## Build order

Core first: 60 sites → live weather → hazard score → lightning alert → map.
Everything else is added once the core works.

## Scope

- 60 real U.S. power plants across 6 hazard regions, including an
  Everglades-area Florida plant, Mississippi River plants, and Western
  wildfire-area plants.
- Hazard score 0 to 10: a weather part (0 to 8, trained on NOAA Storm Events)
  plus a wildlife part (0 to 2, trained on GBIF sightings), shown as a baseline
  plus ups and downs.
- Live lightning from NOAA GOES satellites, with a labeled replay as the demo
  backup.
- Photos go through our API. DeepSpace handles real-time events only.
- Missing data always shows as "no data", never zero.

## Timeline (all times ET)

| When | Goal |
| --- | --- |
| Sat morning | 60 real sites on the map, live weather |
| Sat afternoon | Scores showing, lightning alert firing |
| Sat night | Trained models, login, crew reports, deploy |
| Sun 4 AM | Feature freeze, bug fixes only |
| **Sun 8 AM** | **Devpost submission due** |
| Sun 10 AM to 12 PM | Expo |
| Sun 2:30 PM | Closing ceremony, CAR 100 |

## Links

- Hacker Guide: https://guide.swamphacks.com/
- Devpost: https://swamphacks-xii.devpost.com/
- Sperry brief: https://docs.google.com/document/d/1lSneAISdt1fvl3DUAJB92kY8xbxe0MOy/edit
- MLH event page: https://www.mlh.com/events/swamphacks-xii
