# Changelog

All notable changes to this project are documented here.

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
