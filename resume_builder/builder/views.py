from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
import weasyprint


def parse_resume_data(post):
    """Parse POST data into structured resume dict."""

    def get_list(prefix, fields):
        entries = []
        index = 0
        while True:
            key = f"{prefix}-{index}-{fields[0]}"
            if key not in post:
                break
            entry = {field: post.get(f"{prefix}-{index}-{field}", "").strip() for field in fields}
            if any(entry.values()):
                entries.append(entry)
            index += 1
        return entries

    exp_fields = ["company", "start_month", "start_year", "end_month", "end_year", "is_present", "location", "description"]
    experiences = []
    idx = 0
    while f"exp-{idx}-company" in post:
        entry = {f: post.get(f"exp-{idx}-{f}", "").strip() for f in exp_fields}
        entry["is_present"] = post.get(f"exp-{idx}-is_present") == "on"
        entry["bullets"] = [b.strip() for b in entry["description"].splitlines() if b.strip()]
        if any(entry[k] for k in ["company", "description"]):
            experiences.append(entry)
        idx += 1

    educations = get_list("edu", ["institution", "degree", "field", "graduation_month", "graduation_year"])
    certifications = get_list("cert", ["name", "issuer", "date"])
    projects = get_list("proj", ["name", "tech", "description"])
    for proj in projects:
        desc = proj.get("description", "")
        proj["bullets"] = [b.strip() for b in desc.splitlines() if b.strip()]

    return {
        "personal": {
            "name": post.get("name", "").strip(),
            "phone": post.get("phone", "").strip(),
            "email": post.get("email", "").strip(),
            "linkedin": post.get("linkedin", "").strip(),
            "location": post.get("location", "").strip(),
        },
        "summary": post.get("summary", "").strip(),
        "experiences": experiences,
        "educations": educations,
        "certifications": [c for c in certifications if c.get("name")],
        "projects": [p for p in projects if p.get("name")],
    }


def index(request):
    return render(request, "builder/index.html")


@require_http_methods(["POST"])
def preview(request):
    data = parse_resume_data(request.POST)
    return render(request, "builder/preview.html", {"resume": data})


@require_http_methods(["POST"])
def download_pdf(request):
    data = parse_resume_data(request.POST)
    html_string = render(request, "builder/resume_pdf.html", {"resume": data}).content.decode("utf-8")
    pdf = weasyprint.HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
    name = data["personal"]["name"] or "resume"
    filename = f"{name.replace(' ', '_')}_Resume.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
