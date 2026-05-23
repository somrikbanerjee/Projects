import json
import os
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
import weasyprint


def parse_resume_data(post):
    exp_fields = [
        "company", "designation", "start_month", "start_year",
        "end_month", "end_year", "is_present", "location", "description",
    ]
    experiences = []
    idx = 0
    while f"exp-{idx}-company" in post:
        entry = {f: post.get(f"exp-{idx}-{f}", "").strip() for f in exp_fields}
        entry["is_present"] = post.get(f"exp-{idx}-is_present") == "on"
        entry["bullets"] = [b.strip() for b in entry["description"].splitlines() if b.strip()]
        if entry.get("company") or entry.get("description"):
            experiences.append(entry)
        idx += 1

    def get_list(prefix, fields):
        items, i = [], 0
        while f"{prefix}-{i}-{fields[0]}" in post:
            item = {f: post.get(f"{prefix}-{i}-{f}", "").strip() for f in fields}
            if any(item.values()):
                items.append(item)
            i += 1
        return items

    educations = get_list("edu", ["institution", "degree", "field", "graduation_year"])
    certifications = get_list("cert", ["name", "issuer", "date", "link"])
    projects = get_list("proj", ["name", "tech", "link", "description"])
    for proj in projects:
        proj["bullets"] = [b.strip() for b in proj.get("description", "").splitlines() if b.strip()]

    return {
        "personal": {
            "name": post.get("name", "").strip(),
            "phone": post.get("phone", "").strip(),
            "email": post.get("email", "").strip(),
            "linkedin": post.get("linkedin", "").strip(),
            "github": post.get("github", "").strip(),
            "location": post.get("location", "").strip(),
        },
        "summary": post.get("summary", "").strip(),
        "skills": {
            "primary": post.get("skills_primary", "").strip(),
            "secondary": post.get("skills_secondary", "").strip(),
        },
        "experiences": experiences,
        "educations": educations,
        "certifications": [c for c in certifications if c.get("name")],
        "projects": [p for p in projects if p.get("name")],
    }


def index(request):
    return render(request, "builder/index.html", {"home_dir": os.path.expanduser("~")})


@require_http_methods(["POST"])
def preview_fragment(request):
    """Returns just the resume HTML fragment for AJAX injection."""
    data = parse_resume_data(request.POST)
    return render(request, "builder/resume_content.html", {"resume": data})


@require_http_methods(["POST"])
def save_resume(request):
    data = parse_resume_data(request.POST)
    directory = request.POST.get("save_directory", "").strip()
    filename = request.POST.get("save_filename", "").strip()

    if not directory:
        return JsonResponse({"error": "Directory path is required"}, status=400)

    if not filename:
        name = data["personal"]["name"] or "resume"
        filename = name.replace(" ", "_") + ".resume"
    if not filename.endswith(".resume"):
        filename += ".resume"

    filepath = os.path.join(directory, filename)

    try:
        os.makedirs(directory, exist_ok=True)
        save_data = {
            "version": "1.0",
            "personal": data["personal"],
            "summary": data["summary"],
            "skills": data["skills"],
            "experiences": [
                {k: v for k, v in exp.items() if k != "bullets"}
                for exp in data["experiences"]
            ],
            "educations": data["educations"],
            "certifications": data["certifications"],
            "projects": [
                {k: v for k, v in proj.items() if k != "bullets"}
                for proj in data["projects"]
            ],
        }
        with open(filepath, "w") as f:
            json.dump(save_data, f, indent=2)
        return JsonResponse({"success": True, "filepath": filepath})
    except PermissionError:
        return JsonResponse({"error": f"Permission denied: {filepath}"}, status=403)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["POST"])
def download_pdf(request):
    data = parse_resume_data(request.POST)
    base_url = request.build_absolute_uri("/")

    def make_doc(font_size):
        html = render(request, "builder/resume_pdf.html", {
            "resume": data,
            "base_font_size": f"{font_size:.2f}",
        }).content.decode("utf-8")
        return weasyprint.HTML(string=html, base_url=base_url).render()

    # Start at the default size; binary-search down if content overflows one page.
    doc = make_doc(10.5)
    if len(doc.pages) > 1:
        lo, hi = 7.0, 10.5
        for _ in range(7):          # 7 steps → ≤0.05 pt precision
            mid = (lo + hi) / 2
            candidate = make_doc(mid)
            if len(candidate.pages) <= 1:
                doc = candidate
                lo = mid            # fits — try larger
            else:
                hi = mid            # overflows — try smaller
            if hi - lo < 0.08:
                break

    pdf = doc.write_pdf()
    name = data["personal"]["name"] or "resume"
    filename = f"{name.replace(' ', '_')}_Resume.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
