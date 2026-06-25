# HXY Operating Brain Taste Redesign

## Design Read

This is an internal operating AI product for the HXY team, not a generic knowledge base admin page and not a landing page. The visual language should be premium-light, calm, low-saturation, and business-result first.

## Product Principle

The center chat is the product. It should help the user ask a business question and receive one usable answer first. Sources, scoring, risk, correction, and answer-card actions remain available, but they should not compete with the answer.

## Layout

- Center: primary chat surface, quick business entries, scenario selector, messages, composer.
- Left: lightweight operating status rail. Knowledge metrics stay visible. API, upload, review, and file-location controls are collapsed into disclosure groups.
- Right: Inspector. Hidden by default. It opens only after the user clicks answer detail, and it contains quality, evidence, correction, and answer-card actions.
- Mobile: chat appears first. Status and Inspector become fixed drawers that can be opened from the chat header.

## Visual System

- Theme: one light theme across the page.
- Accent: one muted HXY green accent.
- Surfaces: soft off-white panels, low-contrast borders, tinted shadows.
- Shape: 18px panels, 14px controls, pill buttons.
- Motion: only small state transitions and button feedback. No decorative animation.

## Information Rules

- Main answers show only the usable answer plus two actions: detail and correction.
- No default source, chunk, OCR, file path, score, or technical metadata in the chat card.
- Review tasks and upload controls remain available, but they live in the status rail.
- Repeated questions are handled by backend dedupe and should not create repeated review pressure in the UI.

## Testing

Frontend tests should assert:

- page scroll remains locked and chat history scrolls;
- main answer card stays concise;
- status controls are disclosure groups;
- Inspector is hidden by default and opens from detail;
- mobile has status and Inspector drawer controls.
