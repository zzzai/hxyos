# HXYOS Frontdesk Workflow UI Audit

Audit date: 2026-07-05

Evidence:
- `00-home-desktop.png`
- `00-home-mobile.png`
- `01-desktop.png`
- `02-mobile.png`

Scope:
- `apps/admin-web/index.html`
- `apps/admin-web/frontdesk.html`
- Front-stage gateway and staff workflow for choosing a customer scenario, entering a live customer question, using a standard response, then practicing or submitting frontline feedback.

Strengths:
- The front stage no longer exposes backend governance terms.
- The home page is a task gateway instead of a generic knowledge dashboard.
- Frontdesk keeps fast preset questions and also retains a live question box.
- Desktop view keeps scenario selection, live input, answer, and actions visible in one working surface.
- Mobile view reflows into a single column and exposes the answer card in the first viewport.

UX Risks:
- The live question box is keyword routed in V1. It is useful as an entrance, not as a full semantic answer engine.
- The answer card has deliberate whitespace on desktop. This keeps the spoken line calm, but may feel sparse on very large monitors.
- The home mobile cards are readable but tall. If frontdesk becomes the only high-frequency entry, the home page should prioritize it more aggressively.

Accessibility Risks:
- Scenario buttons expose `aria-pressed`.
- Buttons and textarea have explicit `:focus-visible` treatment.
- The page avoids horizontal scroll in the checked 390px mobile viewport.

Recommendations:
- Connect the live question box to approved answer-card retrieval after the HXY answer API is stable.
- Keep the current front stage free of audit, approval, candidate, claim, and publishing language.
- If staff usage concentrates on frontdesk, make `frontdesk.html` the default mobile landing entry.
