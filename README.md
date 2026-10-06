# Resumsky

Resumsky is a Flask resume builder and AI-assisted resume reviewer. It includes a template gallery, an editable resume preview, saved drafts, job matching, review history, and account controls.

## Run locally

Use Python 3.10 or newer. From this directory, create and activate a virtual environment, then install the application dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install Flask Flask-Login Flask-SQLAlchemy python-dotenv pypdf python-docx langchain-openai pydantic
```

Set the environment variables used by the application before starting it:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-value"
$env:GROQ_API_KEY = "your-groq-api-key"
$env:SUPPORT_EMAIL = "your-support-address@example.com"
python app.py
```

Open `http://127.0.0.1:5000`. `GROQ_API_KEY` is required for resume analysis, job matching, and the writing helpers. `SUPPORT_EMAIL` is optional; when unset, the Contact page explains that no support inbox is configured. Do not commit secrets or production credentials.

## Features

- Eight resume templates with category filters and printable previews.
- Guided resume editor with contact, experience, education, skills, summary, and finish steps.
- Autosaved resumes, custom sections and projects, accent colors, font and spacing controls, and optional small profile photo.
- Browser print dialog for saving a resume as PDF.
- AI suggestions for summaries, bullets, and role-related skills.
- Resume review and job-match reports, including prioritized feedback and ATS checks.
- Resume examples, career tips, FAQ, contact, privacy, and terms pages.
- Account profile/password settings and deletion of an account with its saved resumes and reports.
- Light/dark appearance and responsive navigation.

## Data and limitations

Builder resumes and review reports are stored in the configured SQLite database (`instance/app.db`) until removed by the account holder. Original PDF and DOCX files uploaded for review are deleted after processing. Extracted resume text and Job Match inputs are sent to the configured AI provider. Review suggestions are generated estimates and should be checked for accuracy before use.

DOCX export, cover-letter building, and production deployment configuration are not included. The privacy and terms pages describe this project in plain language and are not legal advice; review them for your jurisdiction and deployment before operating a public service.
