# ACE Agents Registry

## Active Agents
### Aegis (`auth-expert-01`)
- **Role**: auth
- **Email**: auth-expert-01@ace.local
- **Memory**: `.cursor/rules/auth.mdc`
- **Responsibilities**: Authentication, Authorization, Session Management

## Write-back Protocol
All agents must follow the write-back protocol:
- `[str-XXX] helpful=X harmful=Y :: <strategy>`
- `[mis-XXX] helpful=X harmful=Y :: <pitfall>`
- `[dec-XXX] :: <decision>`

## Recent Architectural Decisions
