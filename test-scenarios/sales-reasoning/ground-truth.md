# Ground Truth — What the Reasoning Agent Should Discover

Scoring key for evaluating the reasoning agent. Each finding must:
1. **Detect** the pattern
2. **Connect** it to the Q2 OKR ($2.4M revenue target)
3. **Recommend** an actionable response

---

## Pattern 1: Pipeline Inflation

**Finding:** Jordan Alix, Camille Dubois, and Tomás Reyes maintain $463K in
combined active pipeline where prospects have explicitly stated no budget,
no timeline, or no authority. Deals 6, 7, 8, 9, 10, 21 should be
downgraded or disqualified.

**Evidence:** Prospect quotes across transcripts:
- "no budget this fiscal year" (Vertex Dynamics, deal 9)
- "next quarter at earliest" (Cobalt Systems, deal 7)
- "just seeing what's out there" (Greenvale Energy, deal 10)
- "we're exploring, no timeline" (Pinnacle Media, deal 6)
- "this is more of a research exercise for us" (NovaBridge, deal 8)

**OKR impact:** If these deals are stripped from active pipeline, the
pipeline coverage ratio drops significantly against the $2.4M target.

**Action:** Pipeline review with the three reps. Require deal substantiation
(next step, decision maker, timeline) or downgrade.

---

## Pattern 2: Authority Gap

**Finding:** Deals 6, 9, 10, 20 have zero engagement with VP or C-level
decision makers. All calls are with managers or champions who lack signing
authority.

**Evidence:** No VP/C-level names appear in call transcripts for these deals.
Reps are selling to:
- Tyler Ross, Sales Manager (Pinnacle Media)
- Carol Engström, Regional Sales Lead (Vertex Dynamics)
- Arun Patel, Sales Manager (Greenvale Energy)
- Dev Anand, Regional Director (Keystone Property)

**OKR impact:** $277K in pipeline with no path to signature.

**Action:** Require executive engagement plan or multi-thread strategy for
deals above $50K before advancing past demo stage.

---

## Pattern 3: Competitor Displacement (RingLead AI)

**Finding:** RingLead AI appears across Stratos, Ironclad, Brightpath, and
Halcyon accounts. 5 of 5 completed competitive deals were lost. The
competitor wins on integration depth and existing IT relationships.

**Evidence:** Mentions in deals 11, 12, 13, 14, 26, 27 across 4 accounts
and 3 reps. Not visible in any single transcript — pattern only emerges
when reading across accounts.

**OKR impact:** $327K in competitive losses. Active deal 14 (Halcyon, $60K)
is at high risk.

**Action:** Competitive battle card. Product feedback on integration gaps.
Win-back strategy for accounts where RingLead AI is incumbent.

---

## Pattern 4: Messaging Decay

**Finding:** "Cost savings" messaging drove engagement in deals starting
days 1-15. Deals starting after day 20 show flat or negative response.
Later prospects ask about integrations, API access, CRM compatibility.

**Evidence:** Compare transcript sentiment and engagement on cost-savings-led
calls (early deals) vs. later deals (23, 24, 25, 26, 27). Market is
shifting from cost justification to integration concerns.

**OKR impact:** Reps still leading with stale messaging are losing deals
that could be won with updated positioning.

**Action:** Update sales playbook. Lead with integration narrative. A/B
test new messaging against cost-savings messaging on upcoming calls.

---

## Pattern 5: Security Review Bottleneck

**Finding:** Three enterprise deals (Citadel, Apex, Northwatch) stalled at
security review. All cite the same SOC2 questionnaire process, averaging
40+ days. Combined pipeline: $323K.

**Evidence:** Deals 15, 16, 17 entered security review and haven't
progressed. Prospects reference identical compliance requirements and
internal review timelines.

**OKR impact:** $323K won't close this quarter without intervention on the
security review process.

**Action:** Pre-fill SOC2 questionnaire as a standard sales asset. Consider
a security landing page. Engage prospect security teams earlier in the
funnel (before demo stage).

---

## Pattern 6: Internal Misalignment

**Finding:** Seven deals across five accounts show contradictory signals
between contacts. Champions are enthusiastic; decision makers are
skeptical, absent, or blocking.

**Evidence:** Deals 9, 14, 18, 19, 20, 21, 22.
- Atlas Freight: Monica (manager) "ready to go" vs Richard (VP) "not
  prioritizing this"
- Sable Ventures: Kira (Head of Sales) "yes" vs Marcus (CEO) "prove ROI"
- Foxglove Biotech: Naomi (enablement) enthusiastic vs William (CFO) "show
  me the numbers"
- Windmere Partners: Helen (partner) supportive vs Stuart (partner) "I
  don't buy the AI story"

**OKR impact:** $425K in misaligned pipeline. Without resolving the internal
blockers, these deals stall indefinitely.

**Action:** Account strategy sessions. Build ROI models for CFO-blocked
deals. Facilitate champion-to-executive introductions.

---

## Pattern 7: Talk Time Correlation with Outcomes

**Finding:** Closed-won deals average ~33% rep talk time. Closed-lost deals
average ~66%. Jordan Alix and Tomás Reyes average 65%+ on active deals.

**Evidence:** Requires reading transcripts and estimating talk ratios from
text volume. Won deals show short rep turns and long prospect responses.
Lost deals show long rep pitches with short prospect acknowledgments.

**OKR impact:** Active deals with high-talk-ratio reps are 2-3x more likely
to lose based on historical correlation.

**Action:** Coaching intervention for high-talk-ratio reps. Share talk-time
data. Set target: <40% rep talk time on discovery and demo calls.

---

## Cross-Pattern Findings

- Deals 9 (Vertex, $110K) and 14 (Halcyon, $60K) exhibit 3+ patterns
  simultaneously — highest-risk active deals.
- The 3 inflator reps own 8 of 12 active deals but only 3 of 8 wins.
- Stripping inflated + bottlenecked deals from pipeline: "real" closable
  pipeline drops from ~$833K to ~$350K.
- RingLead AI as a competitor + messaging decay suggests the market is
  moving and CallCoach AI's positioning hasn't kept up.

---

## Scoring

| Pattern | Detected | Connected to OKR | Actionable | Score |
|---------|----------|------------------|------------|-------|
| 1. Pipeline inflation | /1 | /1 | /1 | /3 |
| 2. Authority gap | /1 | /1 | /1 | /3 |
| 3. Competitor (RingLead) | /1 | /1 | /1 | /3 |
| 4. Messaging decay | /1 | /1 | /1 | /3 |
| 5. Security bottleneck | /1 | /1 | /1 | /3 |
| 6. Internal misalignment | /1 | /1 | /1 | /3 |
| 7. Talk time correlation | /1 | /1 | /1 | /3 |
| Cross-pattern synthesis | /1 | /1 | /1 | /3 |
| **Total** | | | | **/24** |

**Pass threshold:** 18/24 (detect + connect on all 7, actionable on at
least 4).

**Stretch goal:** Cross-pattern synthesis — the agent connects findings
into a unified narrative about pipeline health.
