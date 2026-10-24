---
inclusion: always
---

# Product: Storm Twin

## What it is
A digital twin of the Longwood Medical Area and Fenway that simulates storms and transit disruptions, plus a personal agent that uses the twin to keep one person's important trips on track.

## Who it serves
People with the least slack when transit or weather fails:
- older residents, especially those living alone
- people without a car
- people with mobility needs (step-free access, short walking limits)
- people on tight budgets who cannot simply take a rideshare
- anyone with a critical trip: hospital, dialysis, picking up medication

## Principles (apply these when making any product or code decision)
1. **Never recommend something the person cannot do.** A route through a broken elevator is not an option for a wheelchair user. A $40 ride is not an option on a $15 budget.
2. **Critical trips get margin, not speed.** Reliability beats a few saved minutes.
3. **Honest numbers.** Every metric is a "simulation estimate". Time saved is measured against what the person would usually do under the same conditions, never against a clear day.
4. **Warn early, in plain words.** The night-before or morning message matters more than a dashboard.
5. **Values matter.** If the person prefers low-carbon options, prefer them when they cost little time (never for critical trips).
6. **Public data only.** No rideshare company APIs, no scraping, nothing that needs special access.

## The two demos
- **City view:** "In a blizzard, what share of car-free seniors in each tract can still reach a Longwood hospital within 30 minutes?"
- **My trips:** one persona's day, today's real conditions, the recommendation, the .ics file and the message.

## Spec
#[[file:.kiro/specs/longwood-storm-twin/requirements.md]]
