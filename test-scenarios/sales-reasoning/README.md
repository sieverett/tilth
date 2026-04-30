# Sales Reasoning Agent — Test Scenario

Test data and ground truth for validating the tilth reasoning agent against
a realistic sales org scenario.

## The company

**CallCoach AI** — enterprise software that provides AI-assisted real-time
coaching for sales reps. They sell to other sales organizations.

## The scenario

8 SDRs, 22 accounts, 27 deals, ~140 call transcripts over 60 days.
The data contains 7 hidden patterns the reasoning agent should discover.

## Success criteria

For each pattern, the agent must:
1. Detect it (surface the pattern)
2. Connect it to the OKR ($2.4M Q2 revenue target)
3. Suggest something actionable (a sales leader could act on it tomorrow)

## Files

- `personas.md` — rep personas, account profiles, prospect personas, deal arcs
- `ground-truth.md` — exactly what the agent should find (scoring key)
- `transcripts/` — generated call transcripts (to be created)
