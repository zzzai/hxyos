# 荷小悦菜单 Open Design Contract

This file is the local design contract for `docs/wellness-menu/`.

## Source

- Open Design: `https://github.com/nexu-io/open-design`
- Primary reference: Open Design `design-systems/wechat/DESIGN.md`
- Secondary reference: Open Design `design-systems/clean/DESIGN.md`
- Mobile interaction reference: Open Design `design-templates/mobile-app/SKILL.md`

We use Open Design as a reference system and token contract. We do not install or vendor the full project.

不把 open-design 仓库整体 vendoring 到 `htops`。原因：Open Design is a design workbench with many packages, plugins, skills, and a Node 24 / pnpm 10 runtime. The wellness menu only needs a stable local design language and a small set of tokens.

## Design Read

Reading this as: a China mobile service-ordering interface for in-store wellness guests and hundred-store operators, with a calm WeChat Mini Program service language, leaning toward Open Design WeChat tokens plus Clean Design System spacing discipline.

## Token Rules

- `--od-accent` is the interaction accent. It follows the WeChat Design System primary green `#07c160`.
- `--brand` is the 荷小悦 jade adaptation used for brand surfaces and less urgent emphasis.
- Large backgrounds stay white or very light grey-green.
- Price and amount text may use one warm accent only, because money needs fast recognition.
- Use the 4px/8px spacing rhythm. Avoid one-off offsets.
- Corner radii are constrained: cards 12-16px, buttons/pills 999px, compact options 10-12px.
- Shadows must be low and green-tinted. Do not use heavy black shadows.

## Customer Menu Rules

- First screen is the usable menu, not a landing page.
- Left navigation remains category-first: 清, 泡, 调, 补, 养.
- Recommended projects are a conversion aid, not an ad block. They must show reason, scenario, and price.
- Item rows must support quick scanning: image, name, tags, short benefit, price, fixed "选择" command.
- The detail page opens as a page-level service selector. Left swipe returns to the previous page.
- The confirm button is fixed at the bottom and must not move while scrolling options.
- Option buttons must not resize when selected. Active state changes color/shadow only.
- History orders open as a full page, not a drawer.

## Therapeutic V2

The next customer menu layer should feel like a calm in-store guide, not a commodity shelf.

- Add a light "today's state" selector before recommendations: shoulder/neck tightness, sleep recovery, cold feet, long sitting, take-away care, and unsure.
- Recommendations should be re-ranked by selected state while keeping the full catalog available.
- Recommendation copy should say what feeling or scenario the item fits, not only list functions.
- Detail pages must show a selected-plan summary after the customer chooses options.
- Motion should feel like breathing: subtle surface glow, gentle active-state feedback, no bounce and no layout shift.
- AI guidance should stay lightweight: "not sure what to choose" can lead the customer to a short state selector before a deeper assistant exists.

## Expert V4

The senior redesign principle is solution-first, not atmosphere-first.

- Do not use vague copy such as "tonight relaxation recommendation" unless it changes a concrete decision.
- Do not hide common states inside a horizontal selector. The common states should be visible together so guests can compare quickly.
- The first screen should map state -> main service -> optional strengthening -> take-away product. This makes "清泡调补养" a usable bundle system, not five isolated categories.
- Recommendation copy should use concrete operation language: "按状态选方案", "主项目", "可加项", "适合人群", "带走养护".
- Recommendation cards should be equal service choices, not a decorative oversized first card. Conversion comes from fit and clarity, not visual dominance.
- The layout rhythm is: visible solution matrix -> matching project list -> full category menu.
- Beauty should come from better information hierarchy, quiet jade surfaces, white space, proportion, and restrained contrast.

## Five Elements Product Science V5

The HXY menu can use Chinese wellness concepts, but it must not look like superstition or medical diagnosis.

- Keep the public product system as `清、泡、调、补、养`.
- Add a first-layer interpretation system: five elements + organ systems + meridian/acupoint direction + product route.
- Use body-data language carefully: "体质数据参考", "症状偏好", "养生导购", not disease diagnosis or treatment claims.
- Every solution card should answer four concrete questions:
  - Which state is this for?
  - Which organ/element concept does it map to?
  - Which meridian/body area should service focus on?
  - Which `清泡调补养` product bundle should the guest choose?
- Huayuhua-style principle: make the category name memorable, repeatable, and buyable. The slogan-level structure is "一人一方，清泡调补养".
- The customer first screen should not display data-proof blocks such as "body data reference" or "product science landing". Data supports the system in the background; the customer sees a clean formula and product route.
- Reduce symptom-heavy copy in the menu entry. Use five-elements formula names and calm body-state language. Avoid making the menu feel like a disease checklist.
- The formula layer is `木、火、土、金、水、自定义`; every formula must contain a complete `清、泡、调、补、养` product route.

## Project System V6

The project list should turn the formula system into clear store operations.

- Use the external project table only as a pricing and service-flow reference, not as final copy.
- Preserve `清、泡、调、补、养` as the customer-facing category system.
- The operational ladder is:
  - `草本泡脚 25分钟`: entry experience.
  - `草本泡脚加钟`: entry experience plus foot or local add-on.
  - `草本足道 60分钟`: main foot-care project.
  - `荷小推 60分钟`: main tuina project.
  - `悦SPA 60分钟`: higher-ticket wellness care.
  - `采耳 / 拔罐 / 刮痧 20分钟`: short add-on projects.
- Every service project should expose service flow, original price, current price, member price, commission, and `清泡调补养` product composition in the catalog data, even if the customer UI renders only the relevant parts.

## Brand Background V7

Source background:

- `knowledge/hxy/normalized/brand/evergreen/荷小悦-品牌全案-华与华三角形框架-菜单UI背景.md`

The menu should absorb the brand plan as operating context, not as long-form copy.

- Strategic read: HXY is not a generic foot-massage menu. It should feel like a clean, affordable, professional community herbal foot-soak brand.
- Core category signal: `草本泡脚` is the entrance; `清、泡、调、补、养` is the buyable product path.
- Brand assets available for restrained use: lotus green, lotus-leaf bucket, steam, Bubble IP, and the feeling words `暖、松、轻、静、稳`.
- Do not turn the first screen into a brand manifesto, treatment guide, or diagnostic form.
- Do not use `方/选方案` as an independent first-level navigation entry. Five-elements choices belong inside product options such as tea direction, foot-soak liquid, essential-oil direction, and custom preference.
- Trust claims such as research institute, intangible heritage formula, authentic medicinal origin, or large-scale body data must stay in background planning unless the project has traceable evidence and legal review.
- Product hierarchy should be visible through item structure: entry experience, main foot-care service, tuina/SPA upgrade, light food, and take-away wellness goods.
- Public UI copy should favor operational and sensory words: clean, warm, relaxed, light, quiet, stable, daily, take away, selected part, service flow.
- Avoid disease, diagnosis, treatment, cure, quantified efficacy, or symptom checklist language in customer-facing menu surfaces.

## Admin And Hundred-Store Rules

- Catalog content remains data-driven through the wellness API.
- Store-specific catalog overrides must not be hard-coded into `order.html`.
- Operators edit project metadata in the admin page; customer UI only renders published catalog data.
- Future store count changes should not require copying HTML files per store.

## Accessibility And Interaction

- Tap targets should be at least 44px high unless the element is purely informational.
- All interactive controls need `:focus-visible`.
- Motion is limited to 150-280ms and must not create layout jumps.
- `prefers-reduced-motion` should disable animated transitions.

## Anti-Patterns

- Do not import the full Open Design repo into the production static menu.
- Do not introduce purple/blue AI gradients, decorative blobs, or generic landing-page composition.
- Do not use unrelated UI systems on the same page.
- Do not add search unless catalog size or user behavior proves it is needed.
- Do not hide operational meaning behind decorative copy.
