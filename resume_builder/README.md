# Resume Builder

A locally-hosted Django web application that lets you build, preview, save, and export a professional, ATS-friendly resume — entirely in your browser, with no data sent to any third-party service.

---

## Features

### Form sections
| Section | Fields |
|---|---|
| **Personal Details** | Full name, phone, email, base location, LinkedIn URL, GitHub URL |
| **Professional Summary** | Free-text summary paragraph |
| **Skills** | Primary skills (comma-separated), Secondary skills (comma-separated) |
| **Work Experience** | Company, job title/designation, start date, end date or "Currently Here", work location, description (each line becomes a bullet point) — repeatable |
| **Education** | Institution, degree, field of study, graduation year — repeatable |
| **Certifications** *(optional)* | Name, issuing organisation, date, credential/verify URL — repeatable |
| **Projects** *(optional)* | Name, technologies used, project URL, description bullets — repeatable |

### Edit / Preview tabs
Switch between the **Edit** tab (the form) and the **Preview** tab at any time. The Preview tab renders a live, accurate representation of the final resume using the same HTML/CSS as the PDF export. If the content exceeds one page, the preview is scaled down visually.

### Auto-fit to one page
When exporting to PDF, the server automatically binary-searches for the largest font size (between 7 pt and 10.5 pt) that keeps all content on a single letter-size page. All font sizes, spacing, and margins scale proportionally because the PDF template uses `em` units throughout.

### Save & Load (`.resume` files)
- **Save** — click the **Save** button in the top bar to open a dialog where you choose a directory and filename. The resume is written to disk as a structured JSON file with the `.resume` extension.
- **Load** — click the **Load** button to open a file picker. Selecting a `.resume` file instantly restores all fields in the form, including dynamic entries (experience, education, etc.).
- Files saved with older versions of the app load cleanly; fields that did not exist in older versions are simply left blank.

### Export PDF
While on the **Preview** tab, click **Export PDF** to download an ATS-friendly PDF. The file is named `FirstName_LastName_Resume.pdf` automatically.

### Typography
- **Headers** (resume name, section titles): Merriweather serif, loaded via Google Fonts
- **Body text**: Calibri (Windows/macOS), falling back to Lato (Google Fonts) on Linux

---

## Requirements

- Python 3.9+
- Django 6.x
- WeasyPrint (for PDF generation)

Install dependencies:

```bash
pip install django weasyprint
```

---

## Running the app

```bash
cd resume_builder
python manage.py migrate
python manage.py runserver
```

Then open **http://127.0.0.1:8000/** in your browser.

---

## Project structure

```
resume_builder/
├── builder/
│   ├── views.py                  # Form parsing, preview, save, PDF export
│   ├── urls.py                   # URL routing
│   └── templates/builder/
│       ├── index.html            # Single-page app (Edit + Preview tabs)
│       ├── resume_content.html   # Shared resume HTML (preview + PDF)
│       └── resume_pdf.html       # PDF-only wrapper with em-based CSS
├── resume_builder/
│   ├── settings.py
│   └── urls.py
└── manage.py
```

---

## URL reference

| URL | Method | Purpose |
|---|---|---|
| `/` | GET | Main page (form + preview tabs) |
| `/preview/` | POST | Returns resume HTML fragment for AJAX preview |
| `/save/` | POST | Writes `.resume` JSON file to a chosen directory |
| `/download/` | POST | Generates and streams the PDF |

---

## `.resume` file format

Save files are plain JSON and can be edited by hand or version-controlled:

```json
{
  "version": "1.0",
  "personal": {
    "name": "Jane Doe",
    "phone": "+1 555 000 0000",
    "email": "jane@example.com",
    "linkedin": "https://linkedin.com/in/janedoe",
    "github": "https://github.com/janedoe",
    "location": "San Francisco, CA"
  },
  "summary": "Experienced software engineer...",
  "skills": {
    "primary": "Python, Django, PostgreSQL",
    "secondary": "React, Docker, AWS"
  },
  "experiences": [
    {
      "company": "Acme Corp",
      "designation": "Senior Software Engineer",
      "start_month": "01",
      "start_year": "2020",
      "end_month": "",
      "end_year": "",
      "is_present": true,
      "location": "San Francisco, CA",
      "description": "Led backend services\nImproved performance by 40%"
    }
  ],
  "educations": [...],
  "certifications": [...],
  "projects": [...]
}
```
