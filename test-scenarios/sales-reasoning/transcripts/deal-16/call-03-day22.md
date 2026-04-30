---
deal_id: 16
call_number: 3
day: 22
date: "2026-03-22"
rep: Marcus Chen
account: Apex Pharma
prospects: ["Yuki Tanaka"]
deal_value: 130000
stage: Security
outcome: active
patterns: [5]
---

# Call Transcript — Apex Pharma, Security Review Call

**Date:** March 22, 2026
**Rep:** Marcus Chen (CallCoach AI)
**Prospect:** Yuki Tanaka, InfoSec Lead, Apex Pharma
**Duration:** 25 minutes

---

**Marcus:** Yuki, thanks for making time. I understand you've started reviewing our security documentation. I wanted to see if there are any questions I can answer directly.

**Yuki:** Yes. I've reviewed your SOC2 Type II report and the questionnaire responses. The SOC2 looks solid. I have specific questions about three areas.

**Marcus:** Go ahead.

**Yuki:** First — call recording storage. Where physically are the recordings stored, and what's the retention and deletion policy?

**Marcus:** Recordings are stored in AWS US-East-1. Standard retention is three years. Customers can configure shorter retention or request on-demand deletion. On contract termination, all data is deleted within 30 days and we provide a certificate of deletion.

**Yuki:** Good. Second — your AI processing pipeline. When call audio is transcribed and analyzed by your AI, where does that processing happen? Is it on your infrastructure or are you sending data to a third-party AI provider?

**Marcus:** It's processed on our infrastructure. We use self-hosted models — we don't send call data to OpenAI or any third-party API. That's a deliberate design decision for exactly this reason.

**Yuki:** That's important. We would not approve a vendor that sends our data to a third-party AI provider. Third — HIPAA. Danielle mentioned our reps sometimes discuss patient information on calls. How does your system handle PHI?

**Marcus:** We have a PHI detection and redaction module. It runs in real-time during transcription and automatically redacts patient names, dates of birth, medical record numbers, and other identifiers before the transcript enters our analytics pipeline. We can provide a BAA — Business Associate Agreement — as part of the contract.

**Yuki:** I need to review the BAA and the redaction methodology. Can you send me technical documentation on the redaction system — specifically the detection accuracy and any known limitations?

**Marcus:** I'll have that over by end of day tomorrow.

**Yuki:** Fine. I also want to note — our standard security review process is 45 to 60 days from receipt of all documentation. I have two other vendor reviews ahead of yours in the queue. I'll get to the detailed assessment once I've cleared those.

**Marcus:** Understood. Is there anything I can do to make your review easier when you do get to it?

**Yuki:** Send comprehensive documentation upfront. Every time I have to send follow-up questions, it adds a week. If your documentation is thorough, the review goes faster.

**Marcus:** We'll be thorough. Thanks Yuki.

**Yuki:** Thank you.
