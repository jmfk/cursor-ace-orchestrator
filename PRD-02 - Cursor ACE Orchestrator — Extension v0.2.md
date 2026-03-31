# PRD: Cursor ACE Orchestrator — Extension v0.2

## Meta Layer, Spec Agent & Living Specs

**Version:** 0.2
 **Status:** Draft
 **Datum:** 2026-03-31
 **Förutsätter:** PRD v0.1 (Ownership Registry, Context Builder, Write-back Pipeline, Executor)

------

## 1. Vad v0.2 tillför

PRD v0.1 löste det grundläggande problemet: agenter saknar minne och kodansvar. V0.2 lägger till tre distinkta kapaciteter:

**A. Dual-layer architecture** — ACE kan jobba *på sig självt* utan att blanda ihop meta-lärande med projekt-lärande.

**B. Spec Agent** — En agent som genererar specs i rätt format baserat på task-typ och historisk success rate. Specs är inte vattenfall-dokument — de är ett kommunikationsprotokoll som växer inkrementellt.

**C. Living Specs** — En spec-struktur med fyra separata lager (intent, constraint, implementation, verification) med olika livscykler och ägarskap.

------

## 2. Det centrala problemet: Self-hosting paradoxen

ACE är ett verktyg som byggs med sig självt. Det skapar en klassisk bootstrapping-konflikt:

- En `auth-agent` vet inte om den fixar auth i ett kundprojekt eller i ACE-repot
- Write-back kan skriva lärdomar om "hur man bygger auth" till samma plats som "hur ACE bör strukturera playbooks"
- Specs genererade för kundprojekt riskerar att mixas med ACE:s egna arkitektur-specs

Dessutom: spec-driven development har rykte om sig att vara vattenfall. Det är ett missförstånd som måste lösas arkitekturellt, inte bara retoriskt.

------

## 3. Lösning: Dual-layer architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          META LAYER                              │
│     (ACE working on itself — lives in ace-orchestrator repo)     │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  spec-agent  │  │  arch-agent  │  │  self-improvement-     │ │
│  │  (testar     │  │  (evolvar    │  │  agent (aggregerar     │ │
│  │   spec-      │  │   ACE:s egna │  │   cross-project        │ │
│  │   format)    │  │   struktur)  │  │   lärdomar)            │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                          │
│                    │  .ace-meta/      │  ← Separerat namespace   │
│                    │  (meta-learnings,│                          │
│                    │   format trials) │                          │
│                    └──────────────────┘                          │
└──────────────────────────────────────────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
┌───────────────────┐ ┌────────────────────┐ ┌───────────────────┐
│  PROJECT LAYER    │ │  PROJECT LAYER     │ │  PROJECT LAYER    │
│  (casting-app)    │ │  (rockit-crm)      │ │  (client-x)       │
│  .ace/            │ │  .ace/             │ │  .ace/            │
│  ownership.json   │ │  ownership.json    │ │  ownership.json   │
│  sessions/        │ │  sessions/         │ │  sessions/        │
│  specs/           │ │  specs/            │ │  specs/           │
└───────────────────┘ └────────────────────┘ └───────────────────┘
```

### Regel 1: Explicit mode switching

ACE är alltid i ett av två lägen. Läget sätts explicit — aldrig implicit.

```bash
# TARGET MODE (default) — jobbar på ett kundprojekt
ace run "fixa refresh token bug" --file src/auth/token.ts
# → Läser .ace/ i current repo
# → Skriver tillbaka till det projektets playbooks och specs

# META MODE (explicit) — jobbar på ACE själv
ace meta run "förbättra reflection-prompten"
# → Läser .ace-meta/ i ACE-repot
# → Har tillgång till aggregerad cross-project data
# → Skriver tillbaka till ACE:s egna playbooks
```

### Regel 2: Separata namespaces, ingen korsning

```
.ace/         → current project (kunddata, projekt-specs, sessions)
.ace-meta/    → ACE self-reference (meta-learnings, experiments, aggregerade insights)
```

Korsning sker bara via explicit sync-kommando, aldrig automatiskt.

### Regel 3: Aggregering, inte rå-kopiering

Cross-project learnings syntetiseras till generella patterns av self-improvement-agenten. Projekt-specifika detaljer (kundnamn, specifika API-nycklar, domän-jargong) rensas bort innan aggregering.

------

## 4. Filstruktur (tillägg till v0.1)

```
ace-orchestrator/                    # ACE:s eget repo
│
├── .ace-meta/                       # Meta-layer (självrefererande)
│   ├── ownership.json               # Vem äger vilken del av ACE
│   ├── experiments/
│   │   ├── spec-formats/
│   │   │   ├── results.json         # Aggregerade experiment-resultat
│   │   │   └── active.json          # Pågående A/B-test
│   │   └── prompt-variants/
│   │       └── results.json
│   ├── cross-project/
│   │   └── aggregated-learnings.json
│   └── decisions/                   # ADRs för ACE själv
│       └── 001-dual-layer.md
│
├── .ace/                            # ACE som target-mode projekt
│   ├── ownership.json
│   └── specs/
│       └── spec-agent-feature/      # Spec för spec-agenten (meta!)
│
├── src/
│   ├── core/                        # (från v0.1)
│   ├── agents/
│   │   ├── spec_agent.py
│   │   └── self_improvement.py
│   └── meta/
│       ├── experiment_tracker.py
│       └── cross_project_analyzer.py
│
└── templates/
    └── spec-formats/
        ├── full-prd.md
        ├── minimal-spec.md
        ├── bdd-gherkin.md
        └── adr-driven.md
```

Projektens `.ace/`-struktur utökas med en `specs/`-mapp:

```
<project-root>/
└── .ace/
    ├── ownership.json               # (från v0.1)
    ├── sessions/                    # (från v0.1)
    ├── decisions/                   # (från v0.1)
    └── specs/
        └── <feature-slug>/
            ├── intent.md            # Human-written, stable
            ├── constraints.md       # Human-curated, semi-stable
            ├── implementation.md    # Agent-generated, fluid
            ├── verification.md      # Human-approved, executable
            └── meta.json            # Format valt, outcome, experiment-id
```

------

## 5. Living Specs — de fyra lagrena

Specs är inte vattenfall-dokument. De är ett kommunikationsprotokoll mellan människa och agent med fyra lager som har fundamentalt olika livscykler och ägarskap.

```
┌─────────────────────────────────────────────────────────────┐
│                    SPEC LIFECYCLE LAYERS                    │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  INTENT LAYER (stable)                                │  │
│  │  "Vad vill vi uppnå?"                                 │  │
│  │  Ägare: Human. Ändras sällan. Kräver explicit beslut. │  │
│  │  Format: User stories, mål, framgångskriterier        │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CONSTRAINT LAYER (semi-stable)                       │  │
│  │  "Vad får vi inte göra?"                              │  │
│  │  Ägare: Human + agent (agent föreslår, human approvar)│  │
│  │  Format: Security, performance, compatibility-regler  │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  IMPLEMENTATION LAYER (fluid)                         │  │
│  │  "Hur bygger vi det?"                                 │  │
│  │  Ägare: Agent. Genereras, itereras, kastas fritt.     │  │
│  │  Format: Teknisk approach, datamodell, API-kontrakt   │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  VERIFICATION LAYER (executable)                      │  │
│  │  "Hur vet vi att det fungerar?"                       │  │
│  │  Ägare: Agent föreslår, human approvar.               │  │
│  │  Format: Gherkin / acceptance criteria / test cases   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Varför detta inte är vattenfall

| Vattenfall-patologi                                | Living Specs-lösning                                        |
| -------------------------------------------------- | ----------------------------------------------------------- |
| Up-front speculation — allt planeras innan kodning | Minimal intent, implementation är emergent                  |
| Specs som kontrakt — avvikelse = failure           | Specs som briefing — agenten frågar när den fastnar         |
| Hög ändringskostnad                                | Agent-ägda lager kastas och regenereras fritt               |
| Sen feedback — review efter en hel fas             | Write-back efter varje task — spec uppdateras kontinuerligt |

**Nyckelinsikt:** Bara implementation layer är "vattenfalls-aktig" — och den är agent-ägd, vilket gör den billig att regenerera. Intent och constraints är stabila ankare, inte en komplett plan.

### Exempelstruktur: MFA-feature

```markdown
# intent.md (human-written, stable)
## Mål
Användare ska kunna aktivera tvåfaktorsautentisering.

## User Stories
- Som användare vill jag kunna aktivera MFA via en authenticator-app
- Som användare vill jag ha backup-koder om jag tappar min enhet
- Som admin vill jag kunna tvinga MFA för specifika roller

## Framgångskriterier
- MFA-aktivering tar < 3 minuter för slutanvändaren
- 0 nya auth-relaterade säkerhetsincidenter 90 dagar post-lansering
# constraints.md (human-curated, semi-stable)
## Säkerhet
- Inga TOTP-secrets i localStorage (absolut förbud)
- Graceful degradation om MFA-provider är nere (fallback: email OTP)
- Max 3 felaktiga försök innan lockout

## Tekniska constraints
- Kompatibelt med befintlig JWT-session-struktur
- Stödja TOTP (RFC 6238) och WebAuthn — ej SMS (avvecklas Q3)
- Bakåtkompatibel: befintliga sessions invalideras inte

## Uppdateringshistorik
- 2026-03-31: Lade till WebAuthn-krav (beslut: dec-007)
# implementation.md (agent-generated, fluid)
<!-- GENERERAD AV spec-agent 2026-03-31 — KAN KASTAS -->
<!-- Iteration 3 — uppdaterat efter Redis-timeout-problem -->

## Vald approach: TOTP-first med WebAuthn som opt-in

### Datamodell
...

### API-kontrakt
POST /api/auth/mfa/setup
POST /api/auth/mfa/verify
DELETE /api/auth/mfa

### Sekvensdiagram
...
# verification.md (agent-föreslagen, human-approved)
## Acceptance Criteria

Scenario: Användare aktiverar TOTP
  Givet att användaren är inloggad utan MFA
  När användaren navigerar till säkerhetsinställningar
  Och skannar QR-koden med sin authenticator-app
  Och anger den genererade koden
  Så ska MFA vara aktiverat på kontot
  Och användaren ska få 8 backup-koder

Scenario: MFA-provider är nere
  Givet att användaren har MFA aktiverat
  När MFA-tjänsten returnerar 503
  Så ska systemet falla tillbaka på email OTP
```

------

## 6. Spec Agent

Spec-agentens enda ansvar är att generera och iterera specs. Den jobbar på intent-nivå (ställer frågor, skapar struktur) och implementation-nivå (genererar approach) — aldrig på constraint-nivå utan human-godkännande.

### 6.1 Format-selektion med experimentell lärande

```json
// .ace-meta/experiments/spec-formats/results.json
{
  "experiments": [
    {
      "id": "exp-001",
      "format": "full-prd",
      "usage_count": 12,
      "success_rate": 0.67,
      "by_domain": { "auth": 0.60, "api": 0.72, "ui": 0.55 }
    },
    {
      "id": "exp-002",
      "format": "minimal-spec",
      "usage_count": 8,
      "success_rate": 0.82,
      "notes": "Bäst för väldefinierade features med tydlig scope"
    },
    {
      "id": "exp-003",
      "format": "bdd-gherkin",
      "usage_count": 3,
      "success_rate": 0.33,
      "notes": "Svårt för UI-komponenter, bra för backend-stateful-logik"
    }
  ],
  "exploration_budget": 0.20
}
```

**Format-selektion: epsilon-greedy logik**

```
1. Lös modul → domän (auth → backend, components → ui)
2. Hämta format-historik för domän
3. Beräkna expected value: success_rate × confidence_weight
4. Dra slumptal [0, 1]:
   - < exploration_budget  → välj lägst-testade formatet
   - >= exploration_budget → välj format med bäst expected value
5. Kräv N≥5 observationer per bucket innan selektion är meningsfull
   → Fallback: minimal-spec tills tillräcklig data finns
```

### 6.2 Spec-agent flöde

```
┌──────────────────────────────────────────────────────────────┐
│                     SPEC AGENT FLOW                          │
│                                                              │
│  1. Input: "Jag vill ha MFA-stöd för auth"                   │
│     ↓                                                        │
│  2. Context analysis:                                        │
│     - Modul: auth (backend-tung)                             │
│     - Task type: new feature, medium-high komplexitet        │
│     ↓                                                        │
│  3. Format selection (epsilon-greedy):                       │
│     - Historik: "bdd-gherkin" 85% success för backend        │
│     - Exploration budget: 20% → chans att prova nytt format  │
│     → Väljer: bdd-gherkin (80%) ELLER minimal-spec (20%)     │
│     ↓                                                        │
│  4. Clarification round (max 3 frågor om oklar scope):       │
│     Väntar på svar innan implementation.md genereras         │
│     ↓                                                        │
│  5. Genererar spec:                                          │
│     - intent.md: draft (human skriver över)                  │
│     - constraints.md: förslag (kräver human-approval)        │
│     - implementation.md: full draft (agent-ägt)              │
│     - verification.md: förslag (kräver human-approval)       │
│     ↓                                                        │
│  6. Implementation agent tar över                            │
│     ↓                                                        │
│  7. Outcome-feedback:                                        │
│     success / partial (N förtydliganden) / failure           │
│     ↓                                                        │
│  8. Experiment tracker + write-back uppdateras               │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 Anti-vattenfall: minimal spec, inkrementell tillväxt

```
┌──────────────────────────────────────────────────────────────┐
│                  ANTI-WATERFALL SPEC LOOP                    │
│                                                              │
│  1. Human: "Jag vill ha MFA-stöd"                            │
│     ↓                                                        │
│  2. Spec-agent: Genererar MINIMAL spec (intent + constraints) │
│     → Ingen implementation.md ännu                           │
│     ↓                                                        │
│  3. Implementation-agent: Försöker bygga med minimal spec    │
│     ↓                                                        │
│  4a. Success → spec var tillräcklig                          │
│      → "minimal räckte för detta scope" loggas               │
│                                                              │
│  4b. Blocker → agent frågar spec-agent om förtydligande      │
│      → implementation.md uppdateras, fortsätter              │
│                                                              │
│  4c. Failure → write-back: "constraint saknas kring X"       │
│      → Constraint föreslås, human approvar, ny iteration     │
│                                                              │
│  Spec växer INKREMENTELLT baserat på faktiska behov,         │
│  inte spekulativ planering.                                  │
└──────────────────────────────────────────────────────────────┘
```

------

## 7. Self-improvement Agent

Körs schemalagt (weekly) eller manuellt via `ace meta analyze`. Aggregerar cross-project data och föreslår uppdateringar av ACE:s egna templates.

```
┌──────────────────────────────────────────────────────────────┐
│                   SELF-IMPROVEMENT AGENT                     │
│                                                              │
│  Input:                                                      │
│  - Session logs från alla projekt (.ace/sessions/)           │
│  - Helpful/harmful räknare från alla playbooks               │
│  - Spec experiment outcomes                                  │
│                                                              │
│  Processar:                                                  │
│  - Rensa projekt-specifik info (PII, kundnamn, etc)          │
│  - Identifiera strategier konsekvent helpful (>4 helpful, 0) │
│  - Identifiera fallgropar som upprepas cross-projekt         │
│  - Identifiera spec-format som konsekvent underpresterar     │
│                                                              │
│  Output:                                                     │
│  - Förslag på nya globala strategier → .ace-meta/            │
│  - Uppdateringar av ACE:s egna templates                     │
│  - Spec-format att deprekera eller förbättra                 │
│                                                              │
│  Kör: ace meta analyze (manuellt) / weekly cron              │
└──────────────────────────────────────────────────────────────┘
```

### Aggregerat lärande-format

```json
// .ace-meta/cross-project/aggregated-learnings.json
{
  "generated": "2026-03-31",
  "source_projects": 3,
  "source_sessions": 47,
  "global_strategies": [
    {
      "id": "g-str-001",
      "helpful": 12,
      "harmful": 1,
      "content": "Validera alltid på middleware-nivå, inte i route-handlers",
      "origin_domains": ["auth", "api"],
      "confidence": "high"
    }
  ],
  "global_pitfalls": [
    {
      "id": "g-mis-001",
      "helpful": 8,
      "harmful": 0,
      "content": "Timezone-hantering i token-expiry orsakar intermittenta fel i produktion",
      "origin_domains": ["auth"],
      "confidence": "high"
    }
  ],
  "spec_insights": [
    {
      "insight": "minimal-spec fungerar bättre än full-prd för features med tydlig scope men komplex implementation",
      "evidence_count": 7
    }
  ]
}
```

------

## 8. CLI-tillägg (v0.2)

```bash
# --- META MODE ---
ace meta run "<prompt>"                           # Agent i meta-mode
ace meta analyze                                  # Self-improvement (cross-project)
ace meta experiment status                        # Pågående experiment
ace meta insights                                 # Aggregerade lärdomar
ace meta sync-templates                           # Uppdatera templates från insights

# --- SPEC AGENT ---
ace spec create "<feature>" --module <module>     # Auto-väljer format
ace spec create "<feature>" --format bdd          # Explicit format
ace spec create "<feature>" --minimal             # Tvinga minimal spec

ace spec show <spec-id>
ace spec iterate <spec-id>                        # Regenerera implementation layer
ace spec feedback <spec-id> --outcome success
ace spec feedback <spec-id> --outcome partial --notes "behövde förtydliga edge cases"
ace spec feedback <spec-id> --outcome failure --notes "scope för brett"

ace spec list
ace spec archive <spec-id>

# --- CONSTRAINT MANAGEMENT ---
ace constraint add --spec <spec-id> "<constraint>"
ace constraint suggest --spec <spec-id>           # Agent föreslår baserat på playbook
ace constraint approve <constraint-id>
```

------

## 9. Milstolpar (uppdaterade)

### M0 — Grund (v0.1)

- [ ] `ace init`, ownership registry, context builder, `.mdc`-templates
- [ ] **TDD Setup:** Integrera Vitest/Pytest och definiera test-patterns.

### M1 — Executor & Loop (v0.1/v0.2)

- [ ] `ace run`, session-logging, headless workarounds.
- [ ] **RALPH Loop:** Implementera `ace loop` med automatiserad test-verifiering.
- [ ] **Installation & Deployment Test:** Automatiserade tester för ACE-installation.

### M2 — Write-back & Principles (v0.1)

- [ ] Reflection-prompt, delta-updates, `helpful/harmful`-räknare.
- [ ] **YAGNI/DRY Enforcement:** Lints och agent-instruktioner för att motverka överimplementering.

### M3 — Living Specs (v0.2)

- [ ] `ace spec create` — genererar de fyra lagrena
- [ ] `specs/`-mapp i `.ace/`
- [ ] Human-approval flow för constraints och verification
- [ ] `ace spec feedback` — outcome-registrering
- [ ] `meta.json` per spec

### M4 — Experiment Tracker (v0.2)

- [ ] Format-bibliotek med 3 initiala format
- [ ] Experiment-tracking per spec med outcome
- [ ] Epsilon-greedy format-selektion (fallback: minimal-spec tills N≥5)
- [ ] `ace meta experiment status`

### M5 — Dual-layer & Meta mode (v0.2)

- [ ] `.ace-meta/`-struktur
- [ ] `ace meta run` — explicit meta-mode, hårt separerat
- [ ] `ace meta analyze` — self-improvement agent
- [ ] Anonymisering av cross-project data

### M6 — Self-improvement loop (v0.2)

- [ ] Cross-project aggregering med confidence threshold
- [ ] Global strategy extraction
- [ ] `ace meta sync-templates` med human review-steg
- [ ] Weekly scheduled analysis

------

## 10. Risker och begränsningar

| Risk                                        | Sannolikhet  | Påverkan   | Mitigering                                                   |
| ------------------------------------------- | ------------ | ---------- | ------------------------------------------------------------ |
| Meta-mode och target-mode blandas           | Medium       | Hög        | Explicit flagga, `.ace-meta` är aldrig default               |
| Spec-agent genererar BDUF-specs             | Medium       | Medium     | Minimal-spec som default, full-prd kräver explicit `--format` |
| Experiment-tracker data för tunn            | Hög initialt | Låg        | Fallback: minimal-spec tills N≥5 per bucket                  |
| Cross-project analyzer exponerar kunddata   | Låg          | Mycket hög | Anonymisering + opt-in per projekt                           |
| Self-improvement propagerar dåliga patterns | Låg          | Hög        | Confidence threshold, human review innan sync                |
| Spec-lager driftar isär                     | Medium       | Medium     | Spec-agent kontrollerar konsekvens vid varje iteration       |

------

## 11. Designprinciper för v0.2

**Specs är briefings, inte blueprints.** En spec är det minimum en agent behöver för att starta — den växer baserat på vad agenten faktiskt stöter på.

**Lager har olika ägarskap.** Intent ägs av människan. Implementation ägs av agenten. Constraint och verification är kollaborativa. Att blanda ägarskap är den vanligaste orsaken till spec-rot.

**Exploration är inbyggt.** Format-selektion utan exploration leder till lokal optimering. 20% slumpmässig exploration förhindrar att systemet fastnar i ett suboptimalt equilibrium.

**Meta-mode är privilegierat.** ACE-repot är verktygets hjärna. Misstag i meta-mode kan propageras till alla projekt. Det kräver explicit aktivering och human review vid sync.

**Aggregering, inte kopiering.** Cross-project learning är värdefull bara om den är tillräckligt abstrakt för generell tillämpning. Rå-kopiering av projekt-specifika strategier skapar brus.

------

*Nästa steg: Implementera M3 (Living Specs) parallellt med M2 (Write-back) — de delar samma reflection-pipeline och kan byggas i ett svep.*	