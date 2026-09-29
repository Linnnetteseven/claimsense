# Hakiki frontend

React, Vite and Tailwind app for claims officers. See the root `README.md` for setup and the API.

```bash
npm install
cp .env.example .env      # VITE_API_URL=http://localhost:8001
npm run dev               # http://localhost:5173
npm run lint && npm run build
```

`VITE_API_URL` is the only setting. It is built into the browser bundle, so it must never hold a secret.

## Screens

- **Landing** (`LandingPage`): queue snapshot, then into the workspace.
- **Queue** (`ClaimList`): claims by stage (To do, Ready, With SHA, Closed) with counts; search across all stages; masked SHA numbers; SHA state badges.
- **Workspace** (`ValidationPanel`): score, one `ErrorCard` per rule with explanation, fix steps, "Why SHA checks this", Apply fix / pick lists and inline editors; Demographics and Claim Info tabs (`ClaimDetails`) showing the real claim; FHIR preview; audit trail; department guide; hand-off to the hospital HIS.
- **Add claim** (`AddClaimModal`): new draft claim with code search.

## Where state lives

| Concern | Where |
|---|---|
| Claims list, stage, patches after each action | `hooks/useClaims.js` |
| Validate, correct, apply fix, restore, hand off | `hooks/useClaimValidation.js` |
| Selected claim, theme, `/` shortcut | `App.jsx` |
| Lifecycle stages (mirrors `backend/services/stages.py`) | `constants/stages.js` |
| Inline field editors and field-to-tab mapping | `constants/status.js`, `constants/claimFields.js` |
| API calls and error shape | `api/client.js` |

## Accessibility

Keyboard: `/` focuses search, Ctrl/Cmd+Enter validates or saves edits, Esc discards edits or closes the form. Code search boxes are ARIA comboboxes. Colours meet WCAG AA contrast in light and dark themes (focus rings included); avoid `slate-400` text on light backgrounds and `slate-500` text on dark ones.
