# Changelog

All notable changes to this project are documented here.

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
