---
deal_id: 27
call_number: 2
day: 44
date: "2026-04-13"
rep: Aisha Okonkwo
account: Halcyon Retail
prospects: ["Greg Paulsen"]
deal_value: 45000
stage: Demo
outcome: lost
patterns: [3, 4]
---

# Call Transcript — Halcyon Retail, Technical Demo

**Date:** April 13, 2026
**Rep:** Aisha Okonkwo (CallCoach AI)
**Prospect:** Greg Paulsen, VP Sales, Halcyon Retail
**Duration:** 22 minutes

---

**Aisha:** Greg, thanks for meeting again. I checked on the Snowflake question — we don't have a native connector on our roadmap for this year. However, I want to show you our API architecture and how it would work with Fivetran or a custom ETL pipeline.

**Greg:** Go ahead.

**Aisha:** Sharing screen. [pause] So here's our API documentation portal. We have three main endpoints: call data, coaching data, and rep performance data. Each returns structured JSON. For your Snowflake pipeline, you'd use the bulk export endpoint — it supports pagination and date-range filtering so you can do daily or weekly data pulls.

**Greg:** What's the latency? If a call finishes at 2 PM, when is the data available via API?

**Aisha:** [typing] Coaching analysis completes within 15 minutes of call end. The data is available via API immediately after that. So roughly 15-minute latency.

**Greg:** RingLead claims real-time. They stream data to Snowflake as the call is happening.

**Aisha:** If they're doing real-time streaming, that is a differentiator. Our architecture processes calls post-completion, not in real-time. The trade-off is accuracy — post-call analysis is more accurate because the AI has the full context of the conversation.

**Greg:** Maybe. But for our analytics use case, freshness matters more than marginal accuracy improvements. We want real-time dashboards.

**Aisha:** I understand. [pause] Greg, let me be honest. If real-time data streaming to Snowflake is a requirement, we're not there yet. Our strength is coaching quality. If your primary criterion is data pipeline compatibility, RingLead is ahead of us on that axis.

**Greg:** I appreciate the honesty. Suki keeps pushing for CallCoach because of the coaching quality, and I don't doubt it's better. But I'm building a data infrastructure, not just buying a coaching tool. I need everything to connect.

**Aisha:** What if the coaching quality could offset the integration gap? Like, if our coaching drove 20% better call performance, would that matter more than real-time data streaming?

**Greg:** It's not an either-or for me. I want both. And right now, only one vendor offers both — even if their coaching is weaker.

**Aisha:** Fair enough. Is there anything else I can do here?

**Greg:** Send me a formal proposal with the quarterly pricing option. I'll compare it against RingLead's final proposal and make a decision next week.

**Aisha:** Will do. Thanks Greg.

**Greg:** Thanks.
