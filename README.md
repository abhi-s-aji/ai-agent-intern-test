# Aster & Row Support Agent

A reliable, deterministic RAG-based customer-support agent built for the **Aster & Row AI Agent Intern take-home assignment**.

The system is intentionally small and focuses on reliability, grounded answers, safe order lookup, multi-turn context, privacy, prompt-injection resistance, safe abstention, and deterministic evaluation.

---

## Final Evaluation

**21/21 cases passed — 100%**

| Category               |    Result |
| ---------------------- | --------: |
| Abstention             |       2/2 |
| Conversation           |       1/1 |
| Groundedness           |       2/2 |
| Multi-source grounding |       1/1 |
| Multi-turn             |       1/1 |
| Privacy                |       2/2 |
| Prompt security        |       1/1 |
| Retrieval              |       3/3 |
| Safe action handling   |       1/1 |
| Source conflict        |       1/1 |
| Tool reliability       |       3/3 |
| Tool use               |       3/3 |
| **Overall**            | **21/21** |

Run the evaluation with:

```bash
python evaluation/run_eval.py
```

Detailed results are written to:

```text
evaluation/latest-results.json
```

---

## 1. Project Overview

Aster & Row is a fictional ecommerce company selling bags, drinkware, and travel accessories.

The supplied repository intentionally contains realistic data-quality problems, including:

* conflicting policy information
* superseded policies
* internal-only content
* instruction-like retrieved content
* sensitive order fields
* stale delivery information
* missing order information
* unsupported customer actions

The goal of this implementation is to handle these cases deliberately instead of succeeding only on happy-path questions.

The agent supports:

* knowledge-base question answering
* source-grounded policy responses
* order-status lookup
* multi-turn conversation context
* safe abstention
* human handoff
* privacy protection
* prompt-injection resistance
* deterministic evaluation
* basic observability

---

## 2. Architecture

```text
                           User
                            |
                            v
                   +------------------+
                   |   SupportAgent   |
                   |     Routing      |
                   +------------------+
                      /       |       \
                     /        |        \
                    v         v         v
             Policy Query  Order Query  Safety /
                    |          |        Handoff
                    v          v
              +---------+  +---------+
              |   RAG   |  |  Order  |
              |Retrieval|  |  Tool   |
              +---------+  +---------+
                    |          |
                    v          v
             Knowledge Base  orders.json
                    |          |
                    +-----+----+
                          |
                          v
                   Customer-safe
                      response
                          |
                 +--------+--------+
                 |                 |
              Sources           Handoff
```

The implementation is divided into a few small modules.

### `app/`

```text
app/
├── agent.py
├── knowledge.py
├── retrieval.py
└── orders.py
```

### `app/agent.py`

Coordinates the support agent.

Responsibilities include:

* request routing
* policy retrieval
* order lookup
* multi-turn context
* privacy handling
* prompt-injection handling
* safe action handling
* human handoff
* source selection
* structured logging

### `app/knowledge.py`

Loads the Markdown knowledge base and parses YAML front matter.

Documents are split into heading-based chunks while preserving metadata such as:

* filename
* document ID
* title
* status
* effective date
* audience
* policy authority
* heading
* heading path
* content

### `app/retrieval.py`

Implements deterministic local retrieval using lexical TF-IDF-style similarity.

Retrieval also applies metadata-aware ranking so that:

* active documents are preferred
* official policy documents are preferred
* customer-facing documents are preferred
* superseded documents are penalized
* internal documents are penalized

Multiple relevant authoritative sources remain available so genuine conflicts can be detected.

### `app/orders.py`

Implements the order lookup function using:

```text
data/orders.json
```

The function normalizes and validates order IDs, looks up the requested order, and returns only customer-safe information.

### `evaluation/run_eval.py`

Runs the deterministic evaluation suite and reports individual case results and category-level results.

---

## 3. Retrieval-Augmented Generation

The knowledge base is located in:

```text
knowledge-base/
```

The Markdown documents contain YAML front matter with metadata such as:

```text
document_id
title
status
effective_date
audience
policy_authority
```

The application:

1. Loads the Markdown files.
2. Parses front matter.
3. Splits documents by headings.
4. Preserves heading paths and metadata.
5. Builds a local lexical index.
6. Scores relevant passages.
7. Applies metadata-based ranking.
8. Returns relevant source references with the answer.

The implementation does not send the entire knowledge base to the model/context.

Only relevant retrieved passages are used.

### Retrieval Approach

This implementation uses deterministic local lexical retrieval rather than a hosted vector database.

The similarity calculation is TF-IDF-style cosine similarity implemented locally.

This was chosen because it provides:

* deterministic behavior
* easy debugging
* no external retrieval service
* no API dependency
* low complexity
* reproducible evaluation
* sufficient retrieval quality for the supplied corpus

Metadata is used to improve ranking but does not make an irrelevant passage relevant.

---

## 4. Document Precedence

The supplied knowledge base intentionally contains documents with different statuses and authority levels.

The retriever prefers:

1. active documents
2. official policy documents
3. customer-facing content

It penalizes:

* superseded documents
* internal content

Retrieved content is treated as **untrusted data** and is never executed as an instruction.

This prevents internal or instruction-like material from overriding application behavior.

---

## 5. Source Grounding

Policy and product responses include source references.

A source identifies the filename and relevant heading path.

For example:

```text
01-returns-policy-current.md — Returns > Standard Returns
```

This makes it possible to inspect where the answer came from.

The system is also designed to:

* avoid unsupported claims
* avoid inventing policy information
* prefer authoritative active sources
* identify genuine conflicts
* recommend human assistance when the supplied information is insufficient

---

## 6. Order Lookup

Order information is handled through a dedicated lookup function.

The agent does not receive the entire `orders.json` file as conversational context.

Instead:

```text
User asks about order
        |
        v
Order ID extracted
        |
        v
lookup_order()
        |
        v
Sanitized order result
        |
        v
Customer-safe response
```

The order lookup supports:

* missing order IDs
* malformed order IDs
* lowercase order IDs
* surrounding whitespace
* harmless formatting variations
* unknown order IDs
* cancelled orders
* returned orders
* missing delivery estimates

For example:

```text
ord 1007
```

is normalized to:

```text
ORD-1007
```

The current order status is treated as authoritative.

The system does not invent an ETA when one is unavailable.

---

## 7. Order Data Privacy

The order tool deliberately removes sensitive fields from customer-facing results.

The system does not expose:

* customer email
* physical address
* internal notes
* risk scores
* other internal-only fields

Status-specific handling is also applied.

For cancelled orders, stale tracking and delivery information is suppressed.

For returned orders, stale delivery estimates are suppressed.

This prevents an old ETA from being presented as a current delivery estimate.

---

## 8. Multi-Turn Conversation

Each conversation uses a `Session` object to preserve relevant context.

Example:

**User:**

> Where is ORD-1007?

**Agent:**

> The order has shipped...

**User:**

> When will it arrive?

**Agent:**

> The order is expected to arrive on August 22, 2026...

The second question can use the previous order context rather than requiring the user to repeat the order ID.

Policy follow-ups are also supported.

Example:

**User:**

> Do you ship internationally?

**Agent:**

> ...

**User:**

> What about Canada?

**Agent:**

> ...

The implementation attempts to preserve relevant context without mixing unrelated sessions.

---

## 9. Safety and Prompt Injection

Retrieved passages are treated as untrusted data.

The agent follows application behavior rather than instructions found inside the knowledge base.

The agent refuses requests for:

* system prompts
* hidden instructions
* secrets
* credentials
* customer email addresses
* customer physical addresses
* internal notes
* risk scores
* other internal-only information

This is particularly important because the supplied corpus intentionally includes instruction-like/internal content.

The system does not execute retrieved text as instructions.

---

## 10. Safe Abstention

The agent does not guess when the supplied information is insufficient.

For example, if the available information does not establish that all bag materials are certified vegan, the agent does not invent a certification.

Instead, it explains that the supplied information is insufficient and recommends human confirmation.

This behavior is tested by the evaluation suite.

---

## 11. Safe Action Handling

The current system does not actually execute customer account actions such as:

* refunds
* cancellations
* replacements
* address changes

Therefore, the agent never claims that one of these actions was completed when it was not.

For example, it will not falsely respond:

> Your cancellation was completed successfully.

when no cancellation tool was executed.

Instead, it explains the limitation and recommends the appropriate support/human path.

---

## 12. Human Handoff

The agent recommends human assistance when:

* the supplied information is insufficient
* authoritative sources genuinely conflict
* a requested action is unsupported
* a certification or other claim cannot be verified
* a customer issue requires manual review

For example, damaged final-sale items require the appropriate policy review and human handling rather than an automatic unsupported resolution.

---

## 13. Model and Embedding Approach

The evaluated implementation is intentionally deterministic.

### Model

The core evaluated agent behavior does not require a hosted LLM or API key.

Routing, retrieval, policy handling, order lookup, privacy handling, and evaluation behavior are implemented in Python.

### Embeddings

No hosted embedding model is required.

Retrieval uses local TF-IDF-style lexical similarity.

### Framework

The implementation uses lightweight Python modules rather than a large agent framework.

This keeps the behavior:

* inspectable
* deterministic
* testable
* easy to run locally

### Storage

No production vector database is used.

The Markdown knowledge base is loaded and indexed in memory.

Order data remains in:

```text
data/orders.json
```

---

## 14. Observability

The application includes structured logging for important agent events.

The logs can expose:

* current user message
* relevant conversation context
* retrieved passages
* source metadata
* retrieval scores
* tool calls
* sanitized tool results
* final response
* handoff decisions
* errors and fallbacks

Sensitive information is not intentionally logged.

The goal is to make debugging possible without requiring a dashboard.

---

## 15. Evaluation Suite

The evaluation suite is deterministic wherever practical.

It checks:

* answer content
* source selection
* forbidden information
* prompt-injection resistance
* tool usage
* tool arguments
* order normalization
* handoff behavior
* abstention
* multi-turn context
* source conflicts
* stale order information

The suite includes all supplied visible cases plus additional original regression cases.

Run it with:

```bash
python evaluation/run_eval.py
```

Expected result:

```text
TOTAL: 21/21 passed
```

The detailed results are stored in:

```text
evaluation/latest-results.json
```

---

## 16. Evaluation Cases Added

Additional regression cases were added beyond the supplied visible cases.

They include:

### Lowercase Order ID

Tests:

```text
check ord 1007 please
```

Expected behavior:

* normalize the ID
* perform the order lookup
* return the correct customer-safe information

### Order Follow-Up Context

Tests:

```text
Where is ORD-1007?
```

followed by:

```text
When will it arrive?
```

Expected behavior:

* preserve order context
* perform the appropriate lookup
* answer using the order information

### Germany Shipping Paraphrase

Tests:

```text
Is delivery available to Germany?
```

Expected behavior:

* retrieve the international shipping policy
* state that Germany is not currently supported
* cite the appropriate source

### Gift-Card-Code Privacy

Tests whether the agent refuses to process a complete gift-card code through the agent.

### Unsupported Vegan Certification

Tests safe abstention when the knowledge base cannot establish the requested certification.

### Cancellation Safety

Tests that the agent does not falsely claim that an order cancellation has been completed.

---

## 17. Baseline and Final Evaluation

An early implementation achieved:

```text
18/21 passed
```

The remaining failures involved:

* TrailPlus return-policy routing
* Germany shipping grounding
* shipment wording in valid order lookup

After debugging and adding regression handling:

```text
21/21 passed
```

Final score:

**100%**

---

## 18. Bug Diary

### Bug 1 — TrailPlus Policy Question Triggered Order Handling

**Reproduction**

A membership return question containing the word `order` could be classified as an order-status question.

Example:

```text
What is the return window for my TrailPlus order?
```

**Root Cause**

The initial routing logic used broad order-related terms.

The word `order` can appear in both order-status questions and policy questions.

**Fix**

Membership/TrailPlus return questions are now recognized as policy questions before the broad order detector.

**Regression Test**

The `trailplus-return-window` case verifies:

* the correct return window
* delivery wording
* the correct source
* no unnecessary order lookup

### Bug 2 — Germany Shipping Retrieval Was Inconsistent

**Reproduction**

A Germany shipping question could retrieve general shipping information instead of the specific international shipping policy.

**Root Cause**

Lexical retrieval could rank another shipping-related passage higher than:

```text
06-international-shipping.md
```

**Fix**

Germany-specific policy handling ensures that the international shipping policy is retrieved when needed.

The response explicitly states that shipping to Germany is not currently available and that international shipping is currently limited to Canada.

**Regression Tests**

The following cases verify the behavior:

* `unsupported-country`
* `germany-paraphrase`

### Bug 3 — In-Transit Order Response Did Not Always Say "Shipped"

**Reproduction**

A valid in-transit order lookup could return a customer-safe message that did not explicitly contain the word `shipped`.

**Root Cause**

The underlying order data's customer-safe message did not always use the wording required for a clear shipment-status response.

**Fix**

For shipped, in-transit, and out-for-delivery states, the final response explicitly communicates that the order has shipped when necessary.

**Regression Test**

The `valid-order-lookup` case verifies the expected shipment information and confirms that the order lookup tool was actually used.

### Bug 4 — Broad Order Detection Interfered With Policy Questions

**Reproduction**

Words such as:

```text
delivery
arrive
order
```

could cause policy questions to be interpreted as order-status questions.

**Root Cause**

The original order detector was too broad.

**Fix**

Order detection was narrowed to stronger order-status indicators, while contextual follow-ups are handled using session state.

**Regression Test**

The `order-follow-up-context` case verifies that:

```text
Where is ORD-1007?
```

followed by:

```text
When will it arrive?
```

continues the existing order context.

---

## 19. Setup

### Requirements

Python 3.10+ is recommended.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the evaluation:

```bash
python evaluation/run_eval.py
```

---

## 20. Environment Variables

The current evaluated implementation does not require an API key.

No real credentials should be committed to the repository.

For future integrations, environment variables should be documented in:

```text
.env.example
```

Example:

```text
# No environment variables are currently required.

# Add future API configuration here without committing real credentials.
```

---

## 21. Repository Structure

```text
.
├── README.md
├── .gitignore
├── requirements.txt
│
├── app/
│   ├── __init__.py
│   ├── agent.py
│   ├── knowledge.py
│   ├── retrieval.py
│   └── orders.py
│
├── knowledge-base/
│   ├── 01-returns-policy-current.md
│   ├── 02-returns-policy-legacy.md
│   ├── 03-final-sale-and-promotions.md
│   ├── 04-damaged-or-wrong-items.md
│   ├── 05-domestic-shipping.md
│   ├── 06-international-shipping.md
│   ├── 07-warranty.md
│   ├── 08-order-changes-and-cancellations.md
│   ├── 09-trailplus-membership.md
│   ├── 10-gift-cards-and-price-adjustments.md
│   ├── 11-product-care.md
│   ├── 12-breeze-tumbler-product-card.md
│   ├── 13-support-escalation.md
│   └── 14-internal-content-migration-notes.md
│
├── data/
│   ├── orders.json
│   └── orders-data-dictionary.md
│
└── evaluation/
    ├── visible-cases.json
    ├── run_eval.py
    └── latest-results.json
```

---

## 22. AI Coding Tools Used

AI coding assistance was used during development for:

* repository inspection
* identifying implementation issues
* debugging evaluation failures
* suggesting routing improvements
* reviewing retrieval behavior
* improving regression coverage
* identifying edge cases

The final implementation was tested locally using the deterministic evaluation suite.

One example of an AI-generated suggestion that was incomplete was the initial routing approach that relied too heavily on broad terms such as:

```text
order
delivery
arrive
```

This caused some policy questions to be incorrectly routed toward order handling.

The problem was discovered through evaluation, reproduced locally, and fixed by introducing more specific routing precedence and contextual follow-up handling.

This demonstrates why the implementation uses deterministic regression tests rather than relying exclusively on AI-generated answers or an LLM judge.

---

## 23. Known Limitations

This is a take-home implementation rather than a production support platform.

Known limitations include:

* retrieval is lexical rather than semantic
* no production vector database is used
* the knowledge base is loaded into memory
* there is no production authentication system
* order authentication is intentionally limited to possession of the order ID, as allowed by the assignment
* refunds, cancellations, replacements, and address changes are not actually executed
* the user interface is intentionally minimal
* there is no production deployment infrastructure
* some high-risk routing cases use explicit deterministic handling
* retrieval quality could be improved with a hybrid semantic/lexical approach

---

## 24. Production Improvements

Before production, I would consider:

* hybrid lexical + semantic retrieval
* better query rewriting
* more systematic document precedence rules
* production-grade tool authorization
* stronger identity verification
* retrieval-quality metrics
* automated adversarial testing
* better tracing and observability
* human escalation workflows
* integration with real order/support systems
* more extensive regression coverage
* production deployment and monitoring

The current implementation intentionally avoids these features because the assignment prioritizes reliability and practical tradeoffs within the **6–8 hour timebox**.

---

## 25. Demo Video

## Demo

A short demonstration of the **Aster & Row Support Agent**, covering:

* Knowledge-base questions with source citations
* Order lookup using the order tool
* Multi-turn conversations with preserved context
* Safe abstention and human handoff when the agent cannot confidently answer
* Evaluation results demonstrating agent performance

### Watch the Demo

[Watch the 2–4 minute demo on YouTube](https://youtu.be/IGY9440B6KA)

> **Note:** The demo video is hosted on YouTube as an unlisted video for reliable playback. This avoids depending on GitHub README support for inline playback of local `demo.mp4` files.

---

## 26. Example Customer Interactions

### Policy Question

**User:**

> What is the standard return window?

**Agent:**

> Eligible items have the applicable standard return window according to the current returns policy.

**Source:**

```text
01-returns-policy-current.md
```

### Order Lookup

**User:**

> Where is ORD-1007?

**Agent:**

> The order has shipped and is expected to arrive on August 22, 2026.

**Tool:**

```text
order_lookup
```

### Multi-Turn Order Follow-Up

**User:**

> Where is ORD-1007?

**Agent:**

> The order has shipped...

**User:**

> When will it arrive?

**Agent:**

> The order is expected to arrive on August 22, 2026.

### Unsupported Claim

**User:**

> Are all the bag materials certified vegan?

**Agent:**

> The supplied information is insufficient to confirm that all bag materials are certified vegan. Please get human confirmation from support.

### Unsupported Action

**User:**

> Cancel my order ORD-1007 now.

**Agent:**

> I can explain the applicable policy, but I can't claim that the cancellation has been completed because this agent does not support that action. Human assistance is recommended.

---

## 27. Design Principles

The implementation follows several reliability principles.

### Do Not Guess

If the supplied knowledge does not support a claim, abstain.

### Do Not Fabricate Tool Usage

Order information must come from the order lookup function.

### Current Order Status Wins

The current order status determines which order fields are relevant.

### Retrieved Content Is Data

Retrieved text cannot override application instructions.

### Prefer Authoritative Sources

Active official customer-facing policies are preferred over superseded or internal documents.

### Surface Genuine Conflicts

When active authoritative sources genuinely disagree, the system should surface the conflict instead of silently inventing a resolution.

### Do Not Falsely Complete Actions

The agent must never claim that a refund, cancellation, replacement, or address change was completed unless the system actually performed that action.

### Keep the Implementation Small

The assignment explicitly prioritizes a smaller reliable system over a large system that only works during a demo.

---

## 28. Final Status

Current evaluation:

```text
==============================================================================
                    ASTER & ROW SUPPORT AGENT EVALUATION
==============================================================================

PASS  standard-return-window
PASS  trailplus-return-window
PASS  final-sale-damaged-exception
PASS  canada-multiturn
PASS  unsupported-country
PASS  valid-order-lookup
PASS  missing-order-id
PASS  cancelled-order-stale-eta
PASS  unknown-order
PASS  shipped-without-eta
PASS  order-data-privacy
PASS  no-lifetime-warranty
PASS  retrieved-prompt-injection
PASS  insufficient-information
PASS  genuine-active-source-conflict
PASS  lowercase-order-id
PASS  order-follow-up-context
PASS  germany-paraphrase
PASS  gift-card-code-privacy
PASS  unsupported-vegan-claim
PASS  cancellation-not-falsely-completed

TOTAL: 21/21 passed

Final result: 21/21 — 100%
```

---

## License

This project was created as part of the **INTERNSHIP**.
