# Changelog

All notable changes to this project are documented here.

---

## [0.3.8] — 2026-05-23

### Changed
- **Two-page layout strategy reworked** — when content cannot fit on one page, the export now uses a deliberate two-page split rather than continuing to shrink fonts:
  - **Page 1** (header + summary + skills + work experience) uses the *largest* font in the range 8–12 pt at which all experience entries still fit on page 1. The binary search maximises the font rather than minimising it, so page 1 fills the available space at normal or near-normal text sizes instead of being crammed at 8 pt.
  - **Page 2** (education + certifications + projects) always renders at the standard 10.5 pt base, regardless of the page 1 font, so the second page never looks disproportionately small or large.
  - A CSS `page-break-after: always` is applied to `.exp-section` to enforce the split. The page 2 font override is injected via a `{% if force_page_break %}` CSS block in the template, active only in two-page mode.
  - If experience itself is so long that it cannot fit on page 1 even at 8 pt, the layout falls back gracefully: the forced split is still applied and the page count is accepted.

### Testing
- Verified with an overflow dataset (original 6 experience entries + 4 certifications + 2 projects + 3 education entries) that spills past one page:
  - Page 1: SOMRIK BANERJEE header (two-row contact) · Professional Summary · Skills · Work Experience (all 6 entries).
  - Page 2: Education · Certifications · Projects — at standard 10.5 pt.
  - Phase 4 selected font: ~10.31 pt for page 1 (largest that kept all experience on page 1).
- Verified original single-page resume still produces exactly 1 page unchanged.

### Files changed
- `builder/views.py` — `download_pdf` refactored: `make_doc` and `best_fit` accept `force_page_break` and `page2_font` parameters; Phase 4 replaced with the fill-and-split strategy.
- `builder/templates/builder/resume_pdf.html` — `{% if force_page_break %}` CSS block added: `.exp-section { page-break-after: always }` and `.edu-section, .cert-section, .proj-section { font-size: {{ page2_font_size }}pt }`.

---

## [0.3.7] — 2026-05-23

### Added
- **Keyboard shortcuts** — three global shortcuts available from any tab:
  - `Ctrl+S` / `Cmd+S` — opens the Save modal.
  - `Ctrl+O` / `Cmd+O` — opens the file picker to load a `.resume` file.
  - `Ctrl+E` / `Cmd+E` — triggers PDF export and download.
  All three call `e.preventDefault()` to suppress the browser's native handler (save-page, open-file, etc.). `metaKey` is included alongside `ctrlKey` for macOS compatibility.

### Files changed
- `builder/templates/builder/index.html` — `keydown` event listener added before the init block.

---

## [0.3.6] — 2026-05-23

### Fixed
- **Contact header items still stacking vertically in PDF** — `display: inline-flex` was the root cause across multiple attempts. WeasyPrint does not reliably render `inline-flex` children in a block container as inline-level boxes; it treats them as block-level, giving each item its own full-width line. Replaced with `display: inline-block` on `.contact-item` and `display: inline-block` on `.contact-icon`, which WeasyPrint honours correctly. Items now flow left-to-right and wrap as atomic units. Verified via layout-preserved `pdftotext` extraction: row 1 contains phone · email · location on one line, row 2 contains LinkedIn · GitHub on one line.
- **Work Experience section displaced to page 2** — `page-break-inside: avoid` on `.exp-section` was telling WeasyPrint not to split the entire section. With the contact header consuming excessive vertical space (five stacked items ≈ 80pt), there was not enough room left on page 1 for the full Experience block, so WeasyPrint moved the whole section to page 2. The section-level rule has been removed; individual `.exp-entry` elements retain their own `page-break-inside: avoid` to prevent mid-entry splits.
- **Font floor lowered from 8.5 pt to 8.0 pt** — gives the binary search more range before falling back to margin reduction, reducing the likelihood of needing tighter margins for moderately long resumes.

### Files changed
- `builder/templates/builder/resume_pdf.html` — `.contact-item` changed to `display: inline-block`; `.contact-icon` changed to `display: inline-block` with `margin-right`; `.exp-section { page-break-inside: avoid }` removed.
- `builder/templates/builder/index.html` — matching preview CSS updated.
- `builder/views.py` — binary search font floor changed from `8.5` to `8.0` in all phases.

---

## [0.3.5] — 2026-05-23

### Added
- **Dynamic margin adjustment** — PDF export now tries three margin levels before reducing font size: 0.75 in (default) → 0.60 in → 0.50 in. Font size is binary-searched in the range 8.5–10.5 pt at each margin level, so font never drops below 8.5 pt before margins are tightened.
- **Two-page fallback** — if content cannot fit on one page even at 8.5 pt / 0.5 in margins, the export accepts up to two pages rather than forcing an unreadably small font. A hard cap of two pages is enforced; anything beyond two pages is rendered at 8.5 pt / 0.5 in and left to flow naturally.
- **Experience section kept on page 1** — the Work Experience section is marked with `page-break-inside: avoid` (class `exp-section`) so WeasyPrint will not split it across pages. Education, Certifications, and Projects sections (`edu-section`, `cert-section`, `proj-section`) carry `page-break-before: auto`, allowing them to flow freely to page 2 when needed.

### Files changed
- `builder/views.py` — `download_pdf` refactored into a three-phase margin-then-font strategy with `binary_search_font` helper; `make_doc` now accepts a `margin` parameter passed to the template.
- `builder/templates/builder/resume_pdf.html` — `@page margin` now uses `{{ page_margin }}` template variable (defaults to `0.75in`); `.exp-section`, `.edu-section`, `.cert-section`, `.proj-section` page-break rules added.
- `builder/templates/builder/resume_content.html` — section `div` elements given semantic classes: `exp-section`, `edu-section`, `cert-section`, `proj-section`.

---

## [0.3.4.1] — 2026-05-23

### Fixed
- **Contact header layout still broken in PDF** — even with `white-space: nowrap`, WeasyPrint was stacking each `.contact-item` on its own line because `display: flex` on `.contact-row` causes WeasyPrint to treat `inline-flex` children as block-level flex items (each taking full row width). Replaced flex layout on `.contact-row` with plain block layout and `text-align: center` on `.resume-contact`, so `.contact-item` elements render as true inline boxes that flow left-to-right and wrap as whole units — exactly how browsers render it. Added `margin: 0 0.45em` to `.contact-item` to restore horizontal spacing previously provided by flex `gap`.

### Files changed
- `builder/templates/builder/resume_pdf.html` — `.resume-contact` changed from flex-column to `text-align: center`; `.contact-row` changed from `display: flex` to plain block with `margin-bottom`; `.contact-item` given `margin: 0 0.45em`.
- `builder/templates/builder/index.html` — matching preview CSS updated for consistency.

---

## [0.3.4] — 2026-05-23

### Fixed
- **Broken contact header in PDF export** — contact items (phone number, location, LinkedIn URL, GitHub URL) were splitting mid-content in WeasyPrint: "+91" / "8017310607" on separate lines, "Hyderabad," / "India" split at the comma, and URLs breaking at `/` characters. Root cause: `white-space: nowrap` was missing from `.contact-item`, so WeasyPrint (which does not apply browser-style lenient wrapping) broke text at every space or URL delimiter within each item. Added `white-space: nowrap` to keep each contact item atomic — it either fits on the current flex row as a whole or moves to the next row as a whole.

### Files changed
- `builder/templates/builder/resume_pdf.html` — `white-space: nowrap` added to `.contact-item`.
- `builder/templates/builder/index.html` — `white-space: nowrap` added to `.contact-item` in the preview CSS for consistency.

---

## [0.3.3] — 2026-05-23

### Added
- **Project link field** — each Project entry now has a "Project Link" URL input. The URL renders on its own line below the project name/tech row in the resume, styled as a small clickable link (`.ref-link`). Included in save/load and PDF export.
- **Certification link field** — each Certification entry now has a "Credential / Verify URL" input. The URL renders below the certification name/issuer/date line. Included in save/load and PDF export.
- **README.md** — project documentation added at the repository root, covering feature overview, requirements, setup instructions, project structure, URL reference, and the `.resume` file format.

### Changed
- **Resume header contact layout** — phone, email, and location are now guaranteed to appear on the first line; LinkedIn and GitHub are always on a second line below. Implemented by splitting `.resume-contact` into two `.contact-row` divs (column flex) instead of a single wrapping flex row. The second row is omitted entirely if neither LinkedIn nor GitHub is provided.

### Files changed
- `builder/views.py` — `get_list` calls for certifications and projects updated to include `"link"` in their field lists.
- `builder/templates/builder/resume_content.html` — contact section restructured into two `.contact-row` divs; `.ref-link` div added to cert and project entries.
- `builder/templates/builder/resume_pdf.html` — `.resume-contact` changed to `flex-direction: column`; `.contact-row` and `.ref-link` CSS rules added.
- `builder/templates/builder/index.html` — `.resume-contact` and `.contact-row` preview CSS updated; `.ref-link` CSS added; `addEntry('cert')` and `addEntry('proj')` updated with link URL inputs; `populateForm` updated for `cert.link` and `proj.link`.
- `README.md` — created.

---

## [0.3.2] — 2026-05-23

### Fixed
- **500 Internal Server Error on preview** — `resume_content.html` had 5 `{% with %}` blocks but 6 `{% endwith %}` tags, causing a `TemplateSyntaxError` on every preview request. Removed the extra `{% endwith %}`.
- **Fragile SVG macro approach replaced** — the `{% with var='<svg ...>' %}` macro technique for icon variables was removed entirely. Each contact icon is now inlined directly at its point of use, eliminating the tag-mismatch class of bug permanently.
- **Skills section guard for old save files** — wrapped the Skills section in an additional `{% if resume.skills %}` check so that resumes loaded from pre-0.3.1 `.resume` files (which have no `skills` key in their JSON) render cleanly without error rather than hitting a `NoneType` attribute access.

### Notes
- Resumes saved with v0.3.0 or earlier load and preview correctly; Skills, GitHub, and Designation fields simply remain blank since they were not present in older save files.

### Files changed
- `builder/templates/builder/resume_content.html` — removed `{% with %}` icon macro block and trailing `{% endwith %}` tags; SVG icons inlined per contact field; added `{% if resume.skills %}` outer guard around Skills section.

---

## [0.3.1] — 2026-05-23

### Added
- **Contact icons in resume header** — small inline SVG icons appear before each contact field (phone, email, location, LinkedIn, GitHub). Icons use `fill="currentColor"` and scale with the surrounding text via `em` sizing.
- **GitHub profile field** — added to Personal Details in the form and rendered in the resume header with a GitHub icon. Stored in the `.resume` save file under `personal.github`.
- **Job Title / Designation field for Work Experience** — each experience entry now has a Designation input. On the resume it renders on the line below the company name, left-aligned with the work location right-aligned beside it (`exp-subheader` row). Stored in the `.resume` save file and restored on load.
- **Skills section** — new form section (placed between Professional Summary and Work Experience) with two plain-text comma-separated inputs: Primary Skills and Secondary Skills. Renders on the resume as a two-row labelled block under a Skills heading. Included in PDF scaling and `.resume` save/load.

### Changed
- Personal Details form reorganised: Base Location moved up to share a row with Primary Email; LinkedIn and GitHub now share the row below.
- Experience form entry reorganised: Row 1 is now Company Name | Job Title / Designation; Work Location moved to its own full-width row beneath.

### Files changed
- `builder/views.py` — `parse_resume_data` updated with `designation` in `exp_fields`, `github` in personal dict, `skills` dict added; `save_resume` persists `skills`.
- `builder/templates/builder/resume_content.html` — inline SVG icons added to all contact fields; `github` contact item added; `exp-subheader` block with designation and location; Skills section added between Summary and Experience.
- `builder/templates/builder/resume_pdf.html` — CSS added for `.contact-icon`, `.contact-item`, `.exp-subheader`, `.exp-designation`, `.skills-row`, `.skills-label`, `.skills-list`.
- `builder/templates/builder/index.html` — GitHub input added to Personal Details; Skills section card added; experience `addEntry` updated with Designation field and reorganised rows; `populateForm` updated for `github`, `designation`, `skills_primary`, `skills_secondary`; matching CSS added to preview resume styles.

---

## [0.3.0] — 2026-05-23

### Added
- **Auto-fit to one page (PDF)** — `download_pdf` now renders the resume at the default 10.5pt base font size and, if the output exceeds one page, performs a binary search (up to 7 iterations, ~0.05pt precision) between 7pt and 10.5pt to find the largest font size that keeps all content on a single letter-size page. All measurements and spacing use `em` units in the PDF template so the entire layout — name, section headings, body text, bullets, and inter-section spacing — scales proportionally with the base font size.
- **Auto-fit to one page (preview)** — After the AJAX preview is injected, `fitToPage()` waits for the browser to finish layout (double `requestAnimationFrame`), measures `offsetHeight` against a 1056px target (11 in × 96 dpi), and applies a CSS `transform: scale()` with a compensating negative `marginBottom` to collapse empty space. A yellow banner appears below the toolbar when scaling is active, showing the percentage and noting that the PDF will auto-adjust to match.
- **Merriweather for header text** — Resume name and section titles now use the Merriweather serif font (loaded via Google Fonts in both the browser preview and WeasyPrint PDF render).
- **Calibri / Lato for body text** — Body text uses `Calibri` where available (Windows / macOS), with `Lato` (Google Fonts) as a cross-platform fallback, followed by `Liberation Sans` and `Arial`.

### Changed
- `resume_pdf.html` CSS rewritten to use `em` units throughout so all sizes and spacing scale proportionally when `base_font_size` changes. Previously used absolute `pt` values.
- `download_pdf` view refactored from a single `write_pdf()` call to a two-phase render/binary-search flow using WeasyPrint's `HTML.render()` and `Document.write_pdf()`.

### Files changed
- `builder/views.py` — `download_pdf` replaced with binary-search font-fitting logic.
- `builder/templates/builder/resume_pdf.html` — CSS converted to `em`-based sizing; `{{ base_font_size }}` template variable added; Merriweather and Calibri/Lato font stacks applied.
- `builder/templates/builder/index.html` — Google Fonts `<link>` tags added; preview resume CSS updated with Merriweather and Calibri/Lato stacks; `fitToPage()` function added; `loadPreview()` updated to call `fitToPage()` after layout settles; `.scale-notice` CSS added.

---

## [0.2.1] — 2026-05-23

### Changed
- Education section: removed the Graduation Month field; only Graduation Year is collected and displayed on the resume.

### Files changed
- `builder/templates/builder/index.html` — removed graduation month select from `addEntry('edu')` and `populateForm`.
- `builder/views.py` — removed `graduation_month` from the education field list in `parse_resume_data`.
- `builder/templates/builder/resume_content.html` — education date range now renders year only.

---

## [0.2.0] — 2026-05-23

### Added
- **Edit / Preview tab bar** — sticky two-tab navigation replaces the bottom "Preview Resume" button. Switching to the Preview tab triggers an AJAX render; switching back to Edit preserves all form state.
- **Save button** — top-bar button opens a modal to choose a directory and filename; Django writes the resume data to a `.resume` file (structured JSON) at the specified path. The directory is created automatically if it does not exist. Filename defaults to the applicant's name and the `.resume` extension is appended automatically.
- **Load button** — top-bar button opens a native file picker filtered to `.resume` files. The JSON is read client-side and all form fields (including dynamic entries, select menus, and the "Currently Working Here" checkbox) are restored.
- **Export PDF button** — appears in the top bar only when the Preview tab is active. Uses the Fetch API to POST to `/download/` and streams the generated PDF as a browser download without leaving the page.
- **Toast notifications** — non-blocking slide-up messages (success / error / info) confirm save, load, and PDF export outcomes.
- **`/save/` endpoint** (`POST`) — accepts form data plus `save_directory` and `save_filename`, writes a versioned `.resume` JSON file, and returns a JSON response with the resolved filepath or a descriptive error.
- **`/preview/` endpoint refactored** — now returns only the resume HTML fragment (no full page wrapper) for AJAX injection into the preview pane.
- **`home_dir` context variable** — passed to the template so the Save modal pre-fills the directory field with the current user's home directory.

### Changed
- `index.html` fully redesigned as a single-page application with a sticky top bar, tab bar, Edit pane, and Preview pane.
- `views.py`: renamed `preview` view to `preview_fragment`; added `save_resume` view; `index` view now passes `home_dir` to the template.
- `urls.py`: updated route for `preview/` to point to `preview_fragment`; added `save/` route.

### Removed
- `preview.html` — superseded by the in-page AJAX preview pane.
- Bottom "Preview Resume" submit button from the edit form.

---

## [0.1.0] — 2026-05-23

### Added
- Initial Django project (`resume_builder`) and app (`builder`).
- **Form page** (`/`) with six collapsible sections:
  - Personal Details: name, phone, primary email, LinkedIn URL, base location.
  - Professional Summary: free-text textarea.
  - Work Experience (dynamic, repeatable): company name, start month/year, end month/year or "Currently Working Here" toggle, work location, description (each line rendered as a bullet point).
  - Education (dynamic, repeatable): institution, degree, field of study, graduation month/year.
  - Certifications (optional, dynamic): name, issuing organisation, date obtained.
  - Projects (optional, dynamic): name, technologies used, description bullets.
- **Preview page** (`/preview/`) — full-page ATS-friendly resume rendered from POST data, with a sticky toolbar containing a "Download PDF" button.
- **PDF download** (`/download/`) — WeasyPrint renders the resume as a letter-size PDF with Arial font, clean single-column layout, bold section headings, and no graphics; downloaded as `FirstName_LastName_Resume.pdf`.
- Shared `resume_content.html` partial used by both the browser preview and the PDF template.
- `resume_pdf.html` — standalone PDF template with `@page` margin rules for WeasyPrint.
- Dynamic form entries managed entirely client-side (add / remove buttons, present-toggle disables end-date fields).
- Django session middleware and SQLite database configured (sessions only; no user data is persisted in the database).
