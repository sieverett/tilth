# Threat model

What we're defending against, in priority order. Read before writing
security-relevant code.

## In scope

### T1: Compromised service exfiltrates data via the read path

**Risk:** A service with the client library is compromised. Attacker tries
to read other namespaces' data.

**Mitigation:**
- The library is write-only. No read code path exists in services that import it.
- The query gateway has a separate read-policy table; most services aren't in it.
- Read requests must come through the query gateway or MCP server, both of
  which enforce namespace filtering based on verified caller identity.
- Qdrant is not network-reachable from service containers; only gateways
  can talk to it.

**Residual risk:** A service that's *also* a legitimate reader could be made
to retrieve and exfiltrate within its own namespaces.

### T2: Compromised service poisons the store with malicious content

**Risk:** Attacker writes content designed to manipulate downstream agents
(prompt injection in retrieved data, instructions to call other tools).

**Mitigation:**
- The ingest gateway records `source` (verified caller identity) and
  `content_hash` on every write. Poisoned content is traceable and
  tamper-detectable.
- Query results wrap content in `<retrieved_document>` tags with provenance,
  so agent system prompts can anchor it as untrusted data.
- Closing `</retrieved_document>` tags in stored text are escaped to prevent
  injection of fake document boundaries.
- High-impact agent tool calls require user confirmation regardless of what
  retrieved content says (agent-host concern, documented in READING.md).

**Residual risk:** Sophisticated injection that evades wrapping. Defense in
depth via agent system prompt guidance is the answer; perfect prevention
isn't possible.

### T3: Accidental PII or secret leakage into the store

**Risk:** A developer logs `f"user data: {user.dict()}"` and customer PII
ends up indexed and searchable across the org.

**Mitigation:**
- Presidio scrubbing on every write catches emails, cards, SSNs, IPs,
  phone numbers, IBANs. Configured for English with `en_core_web_lg` spaCy
  model, pinned in the Dockerfile.
- Documentation explicitly tells teams what not to send.
- A takedown procedure exists for when scrubbing misses something.

**Residual risk:** Novel PII patterns Presidio doesn't recognize, non-English
PII, custom identifiers that aren't standard PII but are still sensitive.
Presidio's NER-based detection has documented false negative rates of 5-15%
even for supported entities. Education and review remain the primary defense.

### T4: Credential sprawl

**Risk:** Vector store credentials in 200 services. Rotation is impossible.

**Mitigation:**
- Only the gateways have Qdrant credentials.
- The client library uses workload identity (`TILTH_IDENTITY`), never a
  static API key to the vector store.
- Rotation touches two services, not 200.

### T5: Cross-tenant or cross-team data exposure via reads

**Risk:** A reader authorized for one namespace queries broadly and gets
results from other namespaces.

**Mitigation:**
- Namespace ACLs enforced server-side, unconditionally appended to every query.
- The reader cannot pass `namespace=*` or omit the filter.
- `top_k` is capped to prevent bulk exfiltration.
- All reads are audit-logged (structured JSON to stdout) with caller, query
  hash, namespaces, and result count.

### T6: DOS via flooding writes or reads

**Risk:** A buggy or malicious service generates a huge volume of writes
or reads, saturating the gateway or Qdrant.

**Mitigation:**
- Per-caller rate limits on both gateways.
- The client library's bounded queue with overflow drop prevents in-process
  unbounded growth.
- Embedding batching at the gateway amortizes cost.
- The batch writer's internal queue is bounded (max 10,000 items) to prevent
  unbounded memory growth under sustained load.

### T7: Denial of wallet via embedding API abuse

**Risk:** A flood of writes generates unbounded OpenAI embedding API costs.
Rate limiting caps requests but not embedding tokens.

**Mitigation:**
- Per-caller rate limits on the ingest gateway cap request volume.
- Text size limit (32KB) bounds per-request token cost.
- Batching amortizes per-call overhead but doesn't reduce total tokens.

**Residual risk:** A sustained flood at rate-limit capacity still generates
significant cost. For v1, monitoring and alerting on embedding API spend is
the answer. Hard cost caps require integration with the billing provider.

### T8: Embedding inversion

**Risk:** Published attacks can reconstruct text from embeddings with
meaningful fidelity. Embeddings of PII-scrubbed text that had scrubbing
false negatives are a direct data exposure path.

**Mitigation:**
- PII scrubbing reduces but doesn't eliminate this risk.
- Qdrant access is restricted to gateways only.

**Residual risk:** For highly sensitive data, the answer is "don't put it
here." This is documented in the README. Embedding inversion is not a
practical v1 concern but should be revisited if the store holds regulated data.

## Out of scope (for v1)

- **Insider threats from platform team members.** People with gateway access
  can read everything. Audit logs are the detective control.
- **Network-level attacks.** Trust the underlying network.
- **Compliance frameworks.** SOC2, HIPAA, GDPR-specific controls are
  separate work.
- **Cryptographic record signing.** Content hash provides tamper detection
  at the application layer. Full signing (HMAC or asymmetric) is a future
  enhancement.

## Principles

1. **Identity comes from the transport, not the body.** Anything the client
   says about itself is a claim, not a fact. Verified identity comes from
   mTLS, OAuth, or workload identity.

2. **Allowlists over blocklists.** Metadata keys, filter keys, namespaces —
   all enumerate what's permitted. Adding a key requires a code change.

3. **Defense in depth.** No single mitigation is sufficient. Wrapping +
   system prompt + tool gating; scrubbing + namespace + audit; rate limit
   + auth + ACL.

4. **Fail closed on the read side, fail open on the write side.** Reads
   that can't verify ACLs return 403. Writes that can't reach the gateway
   are dropped silently — losing log records is better than crashing services.

5. **Errors are sanitized before reaching the client.** Stack traces and
   internal URLs stay in server logs. Clients get a status code and a
   short message.
