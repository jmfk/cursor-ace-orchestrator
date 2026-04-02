# PRD: Cursor ACE Orchestrator

**Version:** 0.2  
**Status:** Draft  
**Datum:** 2026-04-01  
**Författare:** Johan / The Rockit Lab

---

## 1. Problemformulering

Coding agents som Cursor Agent CLI är statslösa per session. De har inget minne av tidigare beslut, känner inte till vem som "äger" vilken del av kodbasen, och får ingen kontextuell förståelse för arkitekturella intentioner om inte den injiceras explicit vid varje anrop.

Det saknas idag ett system som:

- tilldelar och bevarar ansvar per kodmodul över tid
- injicerar rätt minneslice vid rätt tillfälle (baserat på vad agenten ska göra)
- låter agenten skriva tillbaka lärdomar till sin egen kontext
- fungerar med Cursors native primitiver (`.mdc`, `AGENTS.md`) utan att kräva extern infra

Detta leder till att agenter uppför sig inkonsekvent, upprepar misstag, och tappar arkitekturellt sammanhang mellan sessioner.

---

## 2. Mål

Bygga ett tunt orchestration-lager — **Cursor ACE Orchestrator** — som ger coding agents långtidsminne och kodansvar genom att:

1. Använda `.cursor/rules/*.mdc` som agent-specifikt, modulärt minne
2. Använda `AGENTS.md` som cross-tool projektminne
3. Implementera en **write-back-loop** där agenten uppdaterar sin egen kontext efter varje task
4. Tillhandahålla ett **ownership registry** som mappar kodmoduler till dedikerade **Agent Teams**
5. Bygga en **context builder** som komponerar rätt kontext-slice per anrop
6. Implementera en **iterativ loop-motor (`ace loop`)** som kör agenten tills tester passerar (ROLF-style)
7. Möjliggöra **Multi-Agent Consensus** där agenter kan debattera arkitektoniska beslut innan de fastställs
8. Implementera ett **Internal Messaging System (Agent Mail)** för asynkron kommunikation mellan agenter
9. Använda **Standard Operating Procedures (SOPs)** för att styra agent-interaktioner och arbetsflöden
10. Implementera **Token Consumption Modes** (Low, Medium, High) för att kontrollera driftskostnader
11. Integrera **Google Stitch** för AI-driven UI/UX-design och mockup-generering

---

## 3. Begreppsmodell

```
┌─────────────────────────────────────────────────────────────┐
│                    CURSOR ACE ORCHESTRATOR                  │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  Ownership  │    │   Context    │    │   Write-back  │  │
│  │  Registry   │───▶│   Builder    │───▶│   Pipeline    │  │
│  └──────┬──────┘    └──────┬───────┘    └───────┬───────┘  │
│         │                  │                    │           │
│         ▼                  ▼                    ▼           │
│  ┌─────────────┐    ┌───────────────┐   ┌────────────────┐  │
│  │ Agent Teams │◀──▶│  Loop Engine  │◀──┤  .mdc / memory │  │
│  │ (SOP-driven)│    │ (ROLF Cycle) │   │    (store)     │  │
│  └──────┬──────┘    └───────┬───────┘   └────────────────┘  │
│         │                  │                               │
│         ▼                  ▼                               │
│  ┌─────────────┐    ┌───────────────┐   ┌────────────────┐  │
│  │ Agent Mail  │◀──▶│ cursor-agent  │◀──┤ Google Stitch  │  │
│  │ (Messaging) │    │  (executor)   │   │ (UI/UX Mockups)│  │
│  └─────────────┘    └───────────────┘   └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Nyckelbegrepp

**Google Stitch Integration** — Användning av Google Labs AI-native designverktyg för att generera UI-mockups och kod (Tailwind, Flutter, etc.) baserat på "Vibe Design"-prompts från ACE-agenter.

**Agent Role / Agent Team** — En dedikerad agent-persona som agerar som en "one-agent team" för en specifik subsystem, bibliotek eller komponentgrupp. Agenter kan expandera sitt ägarskap till relaterade moduler över tid.

**SOP (Standard Operating Procedure)** — Formella instruktioner som styr hur agenter utför specifika uppgifter (t.ex. `onboarding`, `pr-review`, `consensus-debate`). SOPs håller kommunikationen fokuserad och minskar token-waste.

**Token Consumption Mode** — En global inställning som styr agenternas beteende:

- **Low (Default)**: Minimal kontext, ingen asynkron debatt, fokus på enskilda tasks.
- **Medium**: Tillåter korta debatter, grundläggande QA-audits och prenumerationer.
- **High**: Full multi-agent debatt, omfattande QA, djup kontext-analys och proaktiva refactoring-förslag.

**Consensus Protocol** — En process där två eller flera agenter debatterar en ändring. Inspirerat av "Debate as Fact-Checking" för att minska hallucinationer och nå robusta beslut.

**Contextual Specialization** — Genom att dela upp kodbasen i subsystem minskar vi den totala mängden tokens per anrop, då varje agent endast läser relevant kontext.

**Agent Mail** — Ett internt meddelandesystem (likt e-post) där agenter kan skicka meddelanden, svara i trådar och bifoga filer/kontext till varandra. Detta möjliggör asynkron koordination och formell debatt.

**Memory Slice** — Den kontext en specifik agent behöver för en specifik task. Komponeras dynamiskt från ownership registry + relevant `.mdc` + session memory.

**Write-back** — Processen där agenten efter en avslutad task skriver lärdomar, beslut och uppdaterat ägarskap tillbaka till sin `.mdc`.

**Playbook** — Agentens ackumulerade kunskaps-dokument. Lever i `.cursor/rules/<role>.mdc`. Uppdateras inkrementellt, aldrig skrivs om från scratch.

**ROLF Loop (Reasoning, Action, Learning, Progress, Halt)** — En iterativ cykel där agenten:

1. **Reason:** Analyserar task och befintlig kontext.
2. **Action:** Utför kodändringar.
3. **Learning:** Kör tester och fångar fel/lärdomar.
4. **Progress:** Uppdaterar minnet (`.mdc`) med vad som fungerade/inte fungerade.
5. **Halt:** Avbryter när målet (tester) är uppnått eller max-iterationer nåtts.

---

## 4. Filstruktur

```
<repo-root>/
├── AGENTS.md                          # Cross-tool projektminne (global)
├── .cursor/
│   └── rules/
│       ├── _global.mdc                # alwaysApply: true — projektstandards
│       ├── auth.mdc                   # glob: src/auth/** — auth-agentens playbook
│       ├── api.mdc                    # glob: src/api/**  — api-agentens playbook
│       ├── database.mdc               # glob: src/db/**   — db-agentens playbook
│       └── ui.mdc                     # glob: src/components/** — ui-agentens playbook
│
├── .ace/                              # ACE Orchestrator metadata (gittracked)
│   ├── agents.yaml                    # Centralt register över alla agenter (namn, roll, mail, etc)
│   ├── ownership.yaml                 # Modul → agent-id mappning (YAML)
│   ├── mail/                          # Agent Mail (inbox/sent per agent)
│   │   └── <agent-id>/
│   │       ├── inbox/
│   │       └── sent/
│   ├── sessions/                      # Session-loggar (Markdown)
│   │   └── 2026-03-31T14-22.md
│   └── decisions/                     # ADR-liknande beslutsdokumentation
│       ├── 001-auth-jwt-strategy.md
│       └── 002-api-versioning.md
│
└── .ace-local/                        # Gitignorerad lokal state
    ├── active-session.yaml
    └── agent-cache/
```

### `.ace/agents.yaml` — Agent Registry

Detta dokument definierar alla agenter i systemet, oavsett om de skapats manuellt av användaren eller autonomt av ACE.

```yaml
version: "1"
agents:
  - id: auth-expert-01
    name: "Aegis"
    role: auth-agent
    email: aegis@ace.local
    created_by: user
    created_at: "2026-03-15"
    responsibilities:
      - src/auth
      - src/middleware/auth.ts
    memory_file: .cursor/rules/auth.mdc
    status: active

  - id: ui-styler-02
    name: "Vogue"
    role: ui-agent
    email: vogue@ace.local
    created_by: autonomous
    created_at: "2026-04-01"
    responsibilities:
      - src/components/shared
    memory_file: .cursor/rules/ui.mdc
    status: active
```

### `.ace/ownership.yaml` — format

```yaml
version: "1"
modules:
  src/auth:
    agent_id: auth-expert-01
    owned_since: "2026-03-15"
    last_active: "2026-03-31"
  src/api/v2:
    agent_id: api-master-01
    owned_since: "2026-03-20"
    last_active: "2026-03-30"
unowned:
  - src/utils
  - scripts
```

---

## 5. `.mdc` Playbook-format

Varje agent-roll har en `.mdc`-fil som är dess levande playbook. Den är strukturerad med sektioner som uppdateras inkrementellt.

```markdown
---
description: "Auth-agentens playbook: JWT, sessions, RBAC, middleware"
globs: "src/auth/**"
alwaysApply: false
---

# Auth Agent Playbook

## Ägarskap
- Primärt ansvar: `src/auth/`
- Beroenden: `src/db/users`, `src/api/middleware`
- Senast uppdaterad: 2026-03-31

## Arkitekturella beslut
<!-- [dec-001] helpful=4 harmful=0 :: JWT refresh tokens lagras i httpOnly cookies, inte localStorage -->
<!-- [dec-002] helpful=3 harmful=0 :: RBAC-roller definieras i db, cachas i Redis med 5min TTL -->

## Strategier & patterns
<!-- [str-001] helpful=5 harmful=0 :: Alltid validera token på middleware-nivå innan route-handler -->
<!-- [str-002] helpful=2 harmful=1 :: Undvik att kasta auth-fel direkt — returnera standardiserat AuthError-objekt -->

## Kända fallgropar
<!-- [mis-001] helpful=6 harmful=0 :: Token expiry-kontroll måste ta hänsyn till timezone på servern (UTC alltid) -->

## Stack-kontext
- Auth library: `@auth/nextjs` v5
- Session store: Redis via Upstash
- Password hashing: argon2id

## Pågående arbete
- [ ] Implementera MFA-flow (påbörjad 2026-03-28)
```

Formatet med `[id] helpful=X harmful=Y :: content` är inspirerat av ace-agent/ace — det gör att write-back-pipeline kan öka/minska räknare baserat på om en strategi ledde till framgång eller fel.

---

## 6. Systemkomponenter

### 6.1 Ownership Registry

**Ansvar:** Hålla koll på vilken agentroll som äger vilken kodmodul.

**CLI-interface:**

```bash
ace own src/auth --agent auth-expert-01      # Tilldela ägarskap till specifik agent
ace who src/auth/middleware.ts              # Fråga vem som äger en fil
ace list-owners                             # Lista alla ägarskap
ace unown src/utils                         # Ta bort ägarskap
```

**Intern logik:**

- Löser ägarskap via longest-prefix-match på filsökväg
- En fil kan bara ha en primär ägare
- Beroenden (en agent läser kod ägd av annan) loggas men konfliktar inte

### 6.2 Context Builder

**Ansvar:** Komponera den exakta kontext-slicen för ett specifikt agent-anrop.

**Input:**

- Target file(s) eller task description
- Explicit agent-roll (optional — kan infereras från ownership)
- Task type: `implement`, `review`, `debug`, `refactor`, `plan`

**Output:** Injicerbar kontext-sträng som prepends till cursor-agent-prompten

**Kompositionslogik:**

```
context = [
  global_rules,           # _global.mdc alltid
  agent_playbook,         # <role>.mdc för matchande modul
  recent_decisions,       # Senaste 3 ADRs relaterade till modulen
  session_continuity,     # Senaste sessionen för denna roll (om < 7 dagar)
  task_framing,           # Strukturerat prompt-prefix per task type
]
```

**Task type framing:**

```
implement  → "Du implementerar ny funktionalitet i <modul>. Följ playbook-strategierna.
              Skriv tillbaka nya lärdomar i write-back-sektionen."

review     → "Du granskar kod i <modul>. Identifiera avvikelser från playbook-strategier.
              Lägg till eventuella nya fallgropar i write-back-sektionen."

debug      → "Du debuggar ett problem i <modul>. Om grundorsaken avslöjar ett nytt
              mönster, dokumentera det som [mis-XXX] i write-back."
```

### 6.3 Write-back Pipeline

**Ansvar:** Ta agentens output och extrahera lärdomar som skrivs tillbaka till playbooken.

**Flöde:**

```
1. Agent slutför task
2. Orchestrator kör reflection-prompt mot agent-output
3. Reflection extraherar:
   - Nya strategier [str-XXX]
   - Nya fallgropar [mis-XXX]  
   - Beslut som bör bli ADRs [dec-XXX]
   - Uppdateringar av helpful/harmful-räknare
4. Orchestrator applicerar delta-update på relevant .mdc
5. Session loggas till .ace/sessions/
```

**Reflection-prompt (intern):**

```
Du har precis slutfört följande task i <modul>:
<task_summary>

Resultatet var: <success|failure|partial>

Granska din process och identifiera:
1. Strategier som fungerade väl → formatera som [str-XXX] helpful=1 harmful=0 :: <strategi>
2. Strategier som ledde till problem → formatera som [str-XXX] helpful=0 harmful=1 :: <strategi>  
3. Fallgropar du stötte på → formatera som [mis-XXX] helpful=1 harmful=0 :: <fallgrop>
4. Beslut som bör dokumenteras → formatera som [dec-XXX] :: <beslut och motivering>

Svara ENDAST med en JSON-array av delta-updates.
```

**Delta-update format:**

```json
[
  {
    "type": "new_strategy",
    "id": "str-003",
    "helpful": 1,
    "harmful": 0,
    "content": "Alltid initiera Redis-klienten lazy för att undvika cold-start problem",
    "section": "Strategier & patterns"
  },
  {
    "type": "increment_helpful",
    "id": "str-001",
    "delta": 1
  }
]
```

### 6.4 Executor

**Ansvar:** Köra cursor-agent med rätt kontext och fånga output.

```bash
# Intern exekveringslogik
context=$(ace build-context --file $target_file --task-type $task_type)
result=$(cursor-agent -p --force "$context\n\n$user_prompt" \
  --output-format stream-json 2>&1)
ace writeback --role $role --result "$result" --success $exit_code
```

**Wrapper CLI:**

```bash
# Användaren kör
ace run "implementera refresh token rotation" --file src/auth/token.ts

# Systemet gör:
# 1. Löser roll: auth-agent (via ownership registry)
# 2. Bygger context slice
# 3. Köra cursor-agent med injicerad kontext
# 4. Köra write-back pipeline
# 5. Uppdaterar .ace/sessions/ och .cursor/rules/auth.mdc
```

### 6.5 Loop Engine (ROLF Motor)

**Ansvar:** Hantera den iterativa processen där agenten försöker lösa en task genom flera försök.

**Flöde per iteration:**

1. **Context Refresh:** Hämta senaste `.mdc` (inklusive lärdomar från föregående iteration).
2. **Execute:** Kör `cursor-agent` med den uppdaterade kontexten.
3. **Verify:** Kör de relevanta testerna (TDD).
4. **Analyze:** Om tester misslyckas, kör reflection-prompt för att förstå *varför* och uppdatera minnet med den nya fallgropen.
5. **Repeat:** Gå till steg 1 om tester misslyckas och `max_iterations` inte är nådd.

**CLI-interface:**

```bash
ace loop "Fixa buggen i token rotation" --test "npm test auth" --max 5
```

### 6.6 Multi-Agent Consensus & Teams

**Ansvar:** Hantera interaktioner mellan olika subsystem-agenter när ändringar korsar ägarskapsgränser.

**Agent Creation & Registry:**

- Agenter kan skapas **manuellt** av användaren (`ace agent create`) eller **autonomt** av systemet när en ny modul eller ett bibliotek identifieras.
- Varje agent får ett unikt namn, en dedikerad e-postadress (för Agent Mail) och en egen långtidsminnes-fil (`.mdc`).
- Alla agenter och deras metadata (id, namn, roll, ansvarsområden) dokumenteras centralt i `.ace/agents.yaml`.

**SOP:er (Standard Operating Procedures):**

- **Onboarding/Handover**: När en agent byts ut eller skapas, genereras en `onboarding.md` som sammanfattar subsystemets status och tekniska skulder.
- **PR Review**: Agenter utför automatiskt reviews på varandras ändringar. En `ui-agent` kan granska en `api-agent`s ändringar om de påverkar frontend-kontraktet.
- **Subsystem Health Monitoring**: Agenter kör periodiska "audits" för att hitta brott mot DRY/YAGNI eller prestandaproblem.
- **Dependency Awareness**: Agenter prenumererar på ändringar i subsystem de beror på via Agent Mail.
- **Shared "Coffee Break" Context**: Ett sätt för agenter att dela generella lärdomar (cross-pollination) via en delad `.ace/shared-learnings.mdc`.

**Multi-Agent Debate & Consensus:**

- Inspirerat av "Debate as Fact-Checking" för att minska hallucinationer.
- Agenter utbyter formella förslag via Agent Mail.
- En neutral `arch-agent` (eller LLM-referee) utvärderar tråden.
- **Token Management**: Debatt-längd och djup styrs av det valda Token Consumption Mode (L/M/H).

**Logik för Agent Teams:**

- Varje subsystem (t.ex. `lib/ui-components`, `services/payment`) tilldelas en dedikerad agent.
- En agent kan "lära sig" och ta ansvar för närliggande moduler om det finns en logisk koppling (t.ex. `auth-agent` tar även ansvar för `session-management`).
- Ägarskapshistorik lagras i `.ace/ownership.yaml` för att bevara expertis.

**Agent Mail (Internal Messaging):**

- Agenter kommunicerar via ett trådat e-post-liknande system lagrat i `.ace/mail/`.
- Varje agent har en `inbox/` och `sent/` mapp (Markdown-filer).
- Stöd för **Attachments**: Agenter kan bifoga kodsnuttar, loggar eller spec-filer till sina meddelanden.
- **Threading**: Meddelanden grupperas via `thread_id` för att bevara kontext i debatter.

**Consensus-flöde:**

1. **Conflict Detection:** Om en task i `src/api` kräver ändringar i `src/db`, flaggar systemet att både `api-agent` och `db-agent` är involverade.
2. **Debate (Agent Mail):** Agenter skickar "Architectural Proposals" till varandras inboxar.
3. **Consensus Check:** En neutral `arch-agent` (eller LLM-referee) utvärderar tråden för att se om båda parter är nöjda.
4. **Human Escalation:** Om debatten går >3 rundor utan konsensus, skickas en notis till användaren: `ace consensus resolve <decision-id>`.

### 6.7 UI/UX Orchestration (Google Stitch)

**Ansvar:** Integrera Google Stitch för att generera mockups och UI-kod som en del av utvecklingsflödet.

**Arbetsflöde:**

1. **Vibe Prompting:** En `ui-agent` genererar en "Vibe Design"-beskrivning baserat på `intent.md` och `constraints.md`.
2. **Mockup Generation:** ACE anropar Google Stitch API (eller instruerar användaren att öppna en genererad länk) för att skapa mockups.
3. **Code Extraction:** Agenten extraherar Tailwind/Flutter-kod från Stitch och sparar den i `implementation.md` eller direkt i källkoden.
4. **Visual Verification:** E2E-tester (Playwright) validerar att den implementerade koden matchar Stitch-mockupen.

**CLI-interface:**

```bash
ace ui mockup "Skapa en dashboard för admin" --agent ui-expert-01
ace ui sync <stitch-canvas-url>              # Importera kod från Stitch
```

---

## 7. AGENTS.md som globalt minne

`AGENTS.md` i projektroten fungerar som cross-tool projektminne — den läses av Cursor, Claude Code, Copilot, med flera.

**Struktur:**

```markdown
# AGENTS.md — <Projektnamn>

## Projektöversikt
<Kort beskrivning, stack, syfte>

## Agentroller och ansvar
| Roll | Ansvarar för | Rule file |
|---|---|---|
| auth-agent | `src/auth/` | `.cursor/rules/auth.mdc` |
| api-agent | `src/api/` | `.cursor/rules/api.mdc` |
| db-agent | `src/db/` | `.cursor/rules/database.mdc` |

## Globala standards (alla agenter)
- TypeScript strict mode alltid
- Inga `any`-typer utan explicit kommentar
- Tester skrivs parallellt med implementation

## Arkitekturella beslut (senaste 5)
- [2026-03-31] Valde JWT + Redis sessions över stateless JWT
- [2026-03-20] API v2 är REST, v3 planeras som GraphQL
- ...

## För agenter: Write-back-protokoll
När du slutfört en task, skriv [WRITE-BACK] i ditt svar följt av
lärdomar i JSON-format. Orchestratorn parsar detta och uppdaterar
din playbook.
```

---

## 8. CLI-specifikation

```bash
# Setup
ace init                                    # Initiera .ace/ i projektet
ace agent create --name Aegis --role auth   # Skapa en namngiven agent
ace agent list                              # Visa alla agenter från agents.yaml
ace config tokens --mode medium             # Sätt token consumption mode (low/medium/high)

# Ägarskap
ace own <path> --agent <agent-id>           # Tilldela modul till specifik agent
ace who <file>
ace list-owners

# Kör agent
ace run "<prompt>" --file <target>          # Auto-resolve agent
ace run "<prompt>" --agent <agent-id>       # Explicit agent
ace run "<prompt>" --task-type review       # Explicit task type

# Iterativ loop (ROLF)
ace loop "<prompt>" --test <test_cmd>       # Kör tills testet passerar
ace loop "<prompt>" --max 5                 # Begränsa iterationer

# Meddelanden (Agent Mail)
ace mail inbox                              # Visa inbox för aktiv agent
ace mail send --to <agent-id> --subject "API change" --body "..."
ace mail reply <msg-id>

# UI/UX (Google Stitch)
ace ui mockup "<prompt>"                    # Generera mockup via Stitch
ace ui sync <url>                           # Synka kod från Stitch canvas

# SOP & QA
ace agent onboard <agent-id>                # Kör onboarding-SOP
ace agent audit <agent-id>                  # Kör QA-audit på subsystem
ace agent review <pr-id>                    # Kör cross-agent PR review

# Minne
ace memory show --agent <agent-id>          # Visa playbook
ace memory history --agent <agent-id>       # Visa sessions
ace memory prune --agent <agent-id>         # Ta bort inaktuellt (halvårsvis)

# Beslut (ADR)
ace decision add "Valde argon2id för password hashing"
ace decision list

# Debug
ace context show --file src/auth/token.ts  # Visa vad som skulle injiceras
```

---

## 9. Teknisk stack (föreslagen)


| Komponent        | Val                                        | Motivering                                         |
| ---------------- | ------------------------------------------ | -------------------------------------------------- |
| CLI-ramverk      | Python + Typer                             | Snabb iteration, bra argparsing                    |
| Filoperationer   | Pathlib + ruamel.yaml                      | YAML-preserving för .mdc frontmatter               |
| LLM (reflection) | Claude claude-sonnet-4-6 via Anthropic API | Bättre instruction-following för structured output |
| Executor         | cursor-agent (headless)                    | Codebase-tools inbyggda                            |
| Session-lagring  | Markdown-filer i .ace/sessions/            | Enkelt, läsbart, gittrackbart                      |
| Config           | .ace/config.yaml                           |                                                    |


**Alternativ executor:** Om cursor-agent headless fortsätter vara instabilt — byt till Claude Code CLI (`claude -p`) som executor. Context-builder och write-back-pipeline är identiska.

---

## 10. Milstolpar

### M0 — Grund (v0.1)

- `ace init` — skapar `.ace/`-struktur
- `ace own` / `ace who` — ownership registry (JSON + CLI)
- Manuell context builder (CLI: `ace context show`)
- Grundläggande `.mdc`-templates per roll
- **TDD Setup:** Integrera Vitest/Pytest och definiera test-patterns för ACE-komponenter

### M1 — Executor-integration (v0.2)

- `ace run` — kör cursor-agent med injicerad kontext
- Session-logging till `.ace/sessions/`
- `--output-format stream-json` parsing och error handling
- Headless-stabilitet workarounds (timeout, retry)
- **Installation & Deployment Test:** Automatiserade tester för `ace install` och deployment-flöden

### M2 — Write-back (v0.3)

- Reflection-prompt mot Claude API
- Delta-update parser
- Inkrementell `.mdc`-uppdatering (bevarar struktur)
- `helpful/harmful`-räknare
- **DX/AX Testing:** Validera att agentens reflektioner och write-backs förbättrar framtida DX/AX

### M3 — Memory management (v0.4)

- `ace memory prune` — ta bort inaktuella entries (harmful > helpful)
- ADR-skapande från decisions
- Session-continuity (hämta senaste sessionen per roll)
- `ace memory history`
- **UI/UX Testing:** Om ACE introducerar UI-komponenter, applicera Playwright/Cypress för E2E-tester

### M4 — Multi-agent, SOPs & Consensus (v0.5)

- Parallell exekvering av oberoende roller
- **Agent Teams & SOPs**: Implementera onboarding, PR-review och audit-SOPs.
- **Agent Mail & Subscriptions**: Implementera prenumerationslogik för subsystem-ändringar.
- **Consensus & Debate**: Implementera debatt-logik med LLM-referee.
- **Token Manager**: Implementera L/M/H modes för att styra kontext och debatt-djup.
- **Human-in-the-loop Escalation**: CLI-stöd för att lösa agent-konflikter.
- **System-wide Integration Tests**: Verifiera multi-agent koordination och minnes-konsistens.

---

## 11. Teststrategi & Best Practices (TDD)

ACE Orchestrator följer en strikt **Test-Driven Development (TDD)** approach för att säkerställa stabilitet, DX och AX.

### 11.1 Testnivåer


| Testtyp                | Verktyg                | Fokus                                                                       |
| ---------------------- | ---------------------- | --------------------------------------------------------------------------- |
| **Unit Tests**         | Vitest / Pytest        | Logik i Context Builder, Ownership Registry, Delta-parsers.                 |
| **Integration Tests**  | Vitest / Pytest        | Samspel mellan Registry, Context Builder och File System.                   |
| **E2E / System Tests** | Playwright / CLI-test  | Hela `ace run` flödet från prompt till write-back.                          |
| **Installation Tests** | Custom Scripts         | Verifiera att `pip install` / `npm install` fungerar på ren miljö (Docker). |
| **Deployment Tests**   | CI/CD (GitHub Actions) | Verifiera att ACE kan deployas och köras i en CI-miljö.                     |


### 11.2 Upplevelsebaserad Testning (DX & AX)

**Developer Experience (DX):**

- **CLI Ergonomics:** Tester som mäter antal keystrokes och tydlighet i felmeddelanden.
- **Documentation Coverage:** Automatiserad kontroll att alla CLI-kommandon är dokumenterade i `AGENTS.md` och `--help`.

**Agentic Experience (AX):**

- **Context Relevance Score:** Tester som utvärderar om den injicerade kontexten faktiskt hjälper agenten (mäts via success-rate i `ace run`).
- **Write-back Accuracy:** Verifiera att agentens lärdomar är korrekta och inte introducerar hallucinationer i `.mdc`.
- **Memory Coherence:** Tester som kollar att agenten inte "glömmer" tidigare beslut över flera sessioner.

### 11.3 UI/UX Testing

- **Visual Regression:** Om ACE får ett web-gränssnitt, använd Playwright för att fånga layout-skift och visuella buggar.
- **Accessibility (A11y):** Automatiska tester för WCAG-kompatibilitet i alla UI-komponenter.

### 11.4 Best Practices för Testning

- **Red-Green-Refactor:** Ingen kod skrivs utan ett misslyckat test.
- **YAGNI (You Ain't Gonna Need It):** Implementera endast det som krävs för att klara det aktuella testet. Undvik "future-proofing" som ökar komplexiteten.
- **DRY (Don't Repeat Yourself):** Identifiera och extrahera gemensamma mönster (t.ex. filhantering, LLM-anrop) till delade utilities så fort de används på mer än ett ställe.
- **Mocking:** Mocka LLM-anrop (Claude API) för att spara kostnad och tid under unit-tester.
- **Snapshot Testing:** Använd snapshots för att verifiera genererad kontext och `.mdc` delta-updates.
- **CI/CD Enforcement:** Inga PRs mergas utan 100% test-pass och täckning på kritiska moduler.

### 11.5 Kodgranskning & Arkitektur (YAGNI/DRY Enforcement)

- **Complexity Lints:** Använd verktyg för att flagga hög cyklomatisk komplexitet (tecken på brott mot YAGNI).
- **Duplication Checks:** Kör automatiserade verktyg (t.ex. `jscpd` eller liknande) i CI för att upptäcka kodduplicering.
- **Agentic Review:** ACE-agenter instrueras att specifikt leta efter DRY-möjligheter och YAGNI-överträdelser under `review` tasks.

---

## 12. Risker och begränsningar


| Risk                                | Sannolikhet | Påverkan | Mitigering                                                      |
| ----------------------------------- | ----------- | -------- | --------------------------------------------------------------- |
| cursor-agent headless hänger        | Hög         | Hög      | Timeout + retry, fallback till Claude Code CLI                  |
| Playbook växer sig för stor         | Medium      | Medium   | `ace memory prune`, token-budget per .mdc                       |
| Write-back skriver fel kontext      | Medium      | Hög      | Human-in-the-loop flagga, diff-preview innan commit             |
| Glob-konflikter i .mdc              | Låg         | Medium   | Valideringskommando vid `ace init`                              |
| Agenten ignorerar injicerad kontext | Medium      | Hög      | Explicit taggning i prompt: `[PLAYBOOK START]...[PLAYBOOK END]` |


---

## 12. Framtida riktningar

Vektoriserat minne** — Ersätt flat `.mdc` med embedding-sökning för stora playbooks. Liknar `creg`-arkitekturen.

**Agentic feedback loop** — Agenten flaggar automatiskt när en task lyckas/misslyckas baserat på test-output, inte bara subjektiv reflektion. Kopplar write-back till CI/CD.

**ROLF-integration** — ACE Orchestrator kan fungera som memory-lager under ett ROLF-loop system där Cursor Agent är executor.

---

*Nästa steg: Bygg M0 — ownership registry + mdc-templates. Estimat: 1–2 dagar.*