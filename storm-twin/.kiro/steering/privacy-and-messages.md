---
inclusion: always
---

# Privacy and user-facing language

## Privacy
- Store a trip's destination as a place label and coordinates only. Never ask for or store why someone is going (no diagnoses, no medication names).
- Logs contain ids, counts and timings only: no names, addresses or destinations.
- Demos, fixtures and screenshots use synthetic personas only.
- Do not commit `.env`, API keys or real user data. `MBTA_API_KEY` is read from the environment.

## Messages to residents
Write for an older reader on a phone.
- At most 320 characters. Plain words, no jargon ("shuttle bus replaces the train" not "SHUTTLE effect on Green-E").
- Order: what changed → when to leave → how → time saved.
- Always include a clock time ("Leave by 9:05").
- Never recommend an option the planner marked infeasible for this person.
- Rideshare prices are always "about $X–$Y", never a single quoted price.
- No alarmist language. Calm, specific, kind.

Good: "Snow is slowing the E train and the Brigham Circle elevator is out. For your 10:00 at Brigham, leave by 8:55 and take the 39 bus from your corner. About 25 min faster than your usual way today."

Bad: "ALERT: Green-E SHUTTLE active, severity 7. Re-route recommended."
