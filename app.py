import os
import json
import re
import uuid
import secrets
import smtplib
from datetime import datetime
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()  # must run BEFORE importing analyzer

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, flash, abort, session,
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, User, Analysis, Resume
from file_parser import extract_text
from analyzer import analyze_resume

IS_VERCEL = bool(os.getenv("VERCEL"))

db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SESSION_COOKIE_SECURE"] = IS_VERCEL

if db_url.startswith("sqlite"):
    # your original SQLite setting (only valid for SQLite)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 15}}
else:
    # Postgres: `timeout` is not a valid option here and would crash the app
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB (Vercel limit is ~4.5 MB)
app.config["SUPPORT_EMAIL"] = os.getenv("SUPPORT_EMAIL", "")

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

UPLOAD_DIR = "/tmp/uploads" if IS_VERCEL else "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED = {".pdf", ".docx"}


# ---------- Google login setup ----------
GOOGLE_ENABLED = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))
oauth = OAuth(app)
if GOOGLE_ENABLED:
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# ---------- Contact messages table ----------
# Defined BEFORE db.create_all() so the table gets created in app.db.
class ContactMessage(db.Model):
    __tablename__ = "contact_message"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


@app.context_processor
def inject_globals():
    return {"now_year": datetime.utcnow().year, "google_enabled": GOOGLE_ENABLED}


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def safe_next(target):
    """Only allow redirects inside our own site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard")


# ---------- Password reset helpers ----------
def reset_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="password-reset")


def make_reset_token(user):
    # The end of the current password hash is stored in the token, so the
    # link stops working as soon as the password is changed (one-time use).
    return reset_serializer().dumps({"id": user.id, "h": user.password_hash[-10:]})


def read_reset_token(token, max_age=3600):
    try:
        data = reset_serializer().loads(token, max_age=max_age)
    except BadSignature:  # also covers expired tokens
        return None
    user = db.session.get(User, data.get("id"))
    if not user or user.password_hash[-10:] != data.get("h"):
        return None
    return user


def send_email(to_email, subject, body):
    """Send an email through SMTP. Returns True if it was sent."""
    server = os.getenv("MAIL_SERVER")
    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    if not (server and username and password):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("MAIL_FROM", username)
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(server, int(os.getenv("MAIL_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        app.logger.exception("Could not send email")
        return False


RESUME_TEMPLATES = [
    {"id": "classic", "name": "The Classic", "category": "Professional", "description": "A trusted, clear single-column layout."},
    {"id": "sidebar-left", "name": "The Column", "category": "Modern", "description": "A compact sidebar for skills and contact details."},
    {"id": "sidebar-right", "name": "The Balance", "category": "Modern", "description": "A calm two-column layout with room for experience."},
    {"id": "minimal", "name": "The Minimal", "category": "Simple", "description": "Quiet typography with generous breathing room."},
    {"id": "bold", "name": "The Statement", "category": "Creative", "description": "A confident header that makes your name memorable."},
    {"id": "compact", "name": "The Executive", "category": "Professional", "description": "More space for a career with depth."},
    {"id": "modern", "name": "The Modern", "category": "Modern", "description": "A clean contemporary layout with a strong hierarchy."},
    {"id": "creative", "name": "The Portfolio", "category": "Creative", "description": "A distinctive layout for design-led work."},
]

EXAMPLE_ROLES = {
    "software-engineer": {
        "title": "Software Engineer",
        "intro": "Show the systems you build, the problems you solve, and how your work helps real users.",
        "skills": ["Python", "JavaScript", "APIs", "Testing", "Cloud platforms"],
        "bullets": [
            "Built and maintained customer-facing features used across a growing product.",
            "Improved reliability by adding automated tests and monitoring to key services.",
            "Worked with product and design partners to turn customer needs into shipped software.",
        ],
    },
    "teacher": {
        "title": "Teacher",
        "intro": "Bring your teaching approach to life with examples of learning support, classroom leadership, and collaboration.",
        "skills": ["Lesson planning", "Classroom leadership", "Assessment", "Differentiation", "Family engagement"],
        "bullets": [
            "Designed accessible lesson plans aligned with curriculum goals and student needs.",
            "Used regular formative assessment to identify learning gaps and adjust instruction.",
            "Partnered with families and colleagues to support student progress.",
        ],
    },
    "nurse": {
        "title": "Registered Nurse",
        "intro": "Highlight compassionate care, sound clinical judgment, and the teams you work with every day.",
        "skills": ["Patient assessment", "Care planning", "EHR systems", "Medication safety", "Team communication"],
        "bullets": [
            "Delivered person-centered care while coordinating with a multidisciplinary clinical team.",
            "Documented assessments and care plans accurately in electronic health records.",
            "Educated patients and families on treatment plans and safe transitions of care.",
        ],
    },
}


# ---------- Public pages ----------
@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html", templates=RESUME_TEMPLATES[:4])


@app.route("/templates")
def template_gallery():
    return render_template("templates_gallery.html", templates=RESUME_TEMPLATES)


@app.route("/templates/use/<template_id>")
@login_required
def use_template(template_id):
    selected = next((item for item in RESUME_TEMPLATES if item["id"] == template_id), None)
    if selected is None:
        abort(404)
    r = Resume(
        user_id=current_user.id,
        title=f"{selected['name']} resume",
        data_json=json.dumps(default_resume(current_user.name, current_user.email, template_id)),
    )
    db.session.add(r)
    db.session.commit()
    return redirect(url_for("builder", resume_id=r.id))


@app.route("/examples")
def examples():
    return render_template("examples.html", examples=EXAMPLE_ROLES)


@app.route("/examples/<role_id>")
def example_detail(role_id):
    example = EXAMPLE_ROLES.get(role_id)
    if example is None:
        abort(404)
    return render_template("example_detail.html", example=example, role_id=role_id)


@app.route("/career-tips")
def career_tips():
    return render_template("career_tips.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    # Pre-fill name/email for logged-in users
    form = {
        "name": current_user.name if current_user.is_authenticated else "",
        "email": current_user.email if current_user.is_authenticated else "",
        "message": "",
    }

    if request.method == "POST":
        # Honeypot: real people never see or fill this hidden field
        if request.form.get("website"):
            return redirect(url_for("contact"))

        form = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "message": request.form.get("message", "").strip(),
        }

        email_domain = form["email"].split("@")[-1]
        if not form["name"] or len(form["name"]) > 80:
            flash("Please enter your name (up to 80 characters).")
        elif "@" not in form["email"] or "." not in email_domain or len(form["email"]) > 120:
            flash("Please enter a valid email address.")
        elif len(form["message"]) < 10:
            flash("Your message is a bit short. Please write at least 10 characters.")
        elif len(form["message"]) > 2000:
            flash("Your message is too long. Please keep it under 2000 characters.")
        else:
            try:
                db.session.add(ContactMessage(**form))
                db.session.commit()
                flash("Thanks! Your message has been sent. We'll get back to you soon.", "success")
                return redirect(url_for("contact"))
            except Exception:
                db.session.rollback()
                app.logger.exception("Could not save contact message")
                flash("Sorry, something went wrong. Please try again.")

    return render_template(
        "contact.html",
        support_email=app.config["SUPPORT_EMAIL"],
        form=form,
    )


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(safe_next(request.args.get("next")))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or "@" not in email:
            flash("Please enter your name and a valid email.")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered. Try logging in.")
        else:
            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(safe_next(request.args.get("next")))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(safe_next(request.args.get("next")))
        flash("Wrong email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))


# ---------- Login with Google ----------
@app.route("/auth/google")
def google_login():
    if not GOOGLE_ENABLED:
        abort(404)
    session["oauth_next"] = safe_next(request.args.get("next"))
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():
    if not GOOGLE_ENABLED:
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        app.logger.exception("Google sign-in failed")
        flash("Google sign-in was cancelled or failed. Please try again.")
        return redirect(url_for("login"))

    info = token.get("userinfo") or {}
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        flash("Your Google account has no verified email, so we couldn't sign you in.")
        return redirect(url_for("login"))

    user = User.query.filter_by(email=email).first()
    if user is None:
        name = (info.get("name") or email.split("@")[0]).strip()[:80]
        user = User(
            name=name,
            email=email,
            # Random password: Google users never type it, but the column stays filled
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(session.pop("oauth_next", url_for("dashboard")))


# ---------- Forgot / reset password ----------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("account"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first() if email else None
        if user:
            link = url_for("reset_password", token=make_reset_token(user), _external=True)
            body = (
                f"Hi {user.name},\n\n"
                "We received a request to reset your Resumsky password.\n"
                f"Use this link within 1 hour:\n\n{link}\n\n"
                "If you didn't ask for this, you can ignore this email."
            )
            sent = send_email(user.email, "Reset your Resumsky password", body)
            if not sent and app.debug:
                # Local testing without email set up: show the link in the terminal
                print(f"\n=== PASSWORD RESET LINK (dev only) ===\n{link}\n", flush=True)
        # Same message whether or not the email exists, so nobody can guess accounts
        flash("If an account exists for that email, we've sent a reset link.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = read_reset_token(token)
    if user is None:
        flash("That reset link is invalid or has expired. Please request a new one.")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.")
        elif password != confirm:
            flash("The two passwords don't match.")
        else:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash("Your password has been changed. You can log in now.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


# ---------- Logged-in pages ----------
@app.route("/dashboard")
@login_required
def dashboard():
    items = (
        Analysis.query.filter_by(user_id=current_user.id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    best = max((a.score for a in items), default=None)
    return render_template(
        "dashboard.html", recent=items[:3], total=len(items), best=best
    )


@app.route("/history")
@login_required
def history():
    items = (
        Analysis.query.filter_by(user_id=current_user.id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    return render_template("history.html", items=items)


@app.route("/report/<int:analysis_id>")
@login_required
def report(analysis_id):
    a = db.session.get(Analysis, analysis_id)
    if not a or a.user_id != current_user.id:
        abort(404)  # users can only see their own reports
    return render_template("report.html", a=a, d=a.data)


@app.route("/report/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_report(analysis_id):
    a = db.session.get(Analysis, analysis_id)
    if not a or a.user_id != current_user.id:
        abort(404)
    db.session.delete(a)
    db.session.commit()
    flash("Report deleted.", "success")
    return redirect(url_for("history"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()
            if not name or len(name) > 80:
                flash("Please enter a name up to 80 characters.")
            else:
                current_user.name = name
                db.session.commit()
                flash("Your profile has been updated.", "success")
        elif action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            if not check_password_hash(current_user.password_hash, current_password):
                flash("Your current password is incorrect.")
            elif len(new_password) < 8:
                flash("Your new password must be at least 8 characters.")
            else:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash("Your password has been changed.", "success")
        elif action == "delete":
            password = request.form.get("delete_password", "")
            if not check_password_hash(current_user.password_hash, password):
                flash("Your password is incorrect. Your account was not deleted.")
            else:
                user = current_user._get_current_object()
                logout_user()
                db.session.delete(user)
                db.session.commit()
                flash("Your account and saved data have been deleted.", "success")
                return redirect(url_for("landing"))
        else:
            abort(400)
    return render_template("account.html")


@app.route("/job-match", methods=["GET", "POST"])
@login_required
def job_match():
    items = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.updated_at.desc()).all()
    result = None
    if request.method == "POST":
        resume_id = request.form.get("resume_id", type=int)
        role = request.form.get("role", "").strip()[:120]
        job_description = request.form.get("job_description", "").strip()[:6000]
        resume = get_own_resume(resume_id) if resume_id else None
        text = resume_to_text(resume.data) if resume else ""
        if not resume:
            flash("Choose one of your saved resumes to continue.")
        elif not text.strip():
            flash("Add some resume details before running a job match.")
        elif not role:
            flash("Enter a target job title.")
        else:
            try:
                result = analyze_resume(text, role, job_description)
                result["overall_score"] = max(0, min(100, result["overall_score"]))
                analysis = Analysis(
                    user_id=current_user.id,
                    filename=f"Job match: {resume.title}"[:200],
                    role=role,
                    score=result["overall_score"],
                    result_json=json.dumps(result),
                )
                db.session.add(analysis)
                db.session.commit()
                return redirect(url_for("report", analysis_id=analysis.id))
            except Exception:
                db.session.rollback()
                app.logger.exception("Job match analysis failed")
                flash("The job match could not be completed. Please try again.")
    return render_template("job_match.html", resumes=items, result=result)


# ---------- The AI endpoint ----------
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    file = request.files.get("resume")
    role = request.form.get("role", "").strip()[:120]

    if not file or file.filename == "":
        return jsonify(error="Please upload a file."), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED:
        return jsonify(error="Only PDF or DOCX files are allowed."), 400

    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    file.save(path)

    try:
        text = extract_text(path)
        feedback = analyze_resume(text, role)
        feedback["overall_score"] = max(0, min(100, feedback["overall_score"]))

        a = Analysis(
            user_id=current_user.id,
            filename=file.filename[:200],
            role=role,
            score=feedback["overall_score"],
            result_json=json.dumps(feedback),
        )
        db.session.add(a)
        db.session.commit()
        return jsonify(redirect=url_for("report", analysis_id=a.id))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        app.logger.exception(e)
        return jsonify(error="Something went wrong. Try again."), 500
    finally:
        if os.path.exists(path):
            os.remove(path)  # resumes are private, never keep the file


# ---------- Resume builder ----------
def default_resume(name="", email="", template="classic"):
    return {
        "template": template,
        "accent": "#0F766E",
        "font": "Lato",
        "font_size": 10,
        "spacing": "normal",
        "name": name, "title": "", "email": email,
        "phone": "", "location": "", "links": "",
        "summary": "",
        "experience": [{"role": "", "company": "", "location": "",
                        "start": "", "end": "", "bullets": ""}],
        "education": [{"degree": "", "school": "", "start": "", "end": ""}],
        "projects": [],
        "skills": "",
        "custom_sections": [],
        "section_order": ["summary", "experience", "education", "projects", "skills", "custom_sections"],
        "photo": "",
    }


def resume_to_text(data):
    lines = [str(data.get(key, "")) for key in ("name", "title", "email", "phone", "location", "links", "summary")]
    for experience in data.get("experience", []):
        lines.extend(str(experience.get(key, "")) for key in ("role", "company", "location", "start", "end", "bullets"))
    for education in data.get("education", []):
        lines.extend(str(education.get(key, "")) for key in ("degree", "school", "start", "end"))
    for project in data.get("projects", []):
        lines.extend(str(project.get(key, "")) for key in ("name", "link", "description"))
    for section in data.get("custom_sections", []):
        lines.extend(str(section.get(key, "")) for key in ("title", "content"))
    lines.append(str(data.get("skills", "")))
    return "\n".join(line for line in lines if line)


def get_own_resume(resume_id):
    r = db.session.get(Resume, resume_id)
    if not r or r.user_id != current_user.id:
        abort(404)  # users can only open their own resumes
    return r


@app.route("/resumes")
@login_required
def resumes():
    items = (
        Resume.query.filter_by(user_id=current_user.id)
        .order_by(Resume.updated_at.desc())
        .all()
    )
    return render_template("resumes.html", items=items)


@app.route("/resumes/new", methods=["POST"])
@login_required
def new_resume():
    r = Resume(
        user_id=current_user.id,
        title="Untitled resume",
        data_json=json.dumps(default_resume(current_user.name, current_user.email)),
    )
    db.session.add(r)
    db.session.commit()
    return redirect(url_for("builder", resume_id=r.id))


@app.route("/builder/<int:resume_id>")
@login_required
def builder(resume_id):
    return render_template("builder.html", r=get_own_resume(resume_id), templates=RESUME_TEMPLATES)


@app.route("/builder/<int:resume_id>/save", methods=["POST"])
@login_required
def save_resume(resume_id):
    r = get_own_resume(resume_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return jsonify(error="Bad data"), 400

    raw = json.dumps(payload["data"])
    if len(raw) > 200_000:
        return jsonify(error="Resume is too large"), 413

    data = payload["data"]
    template_id = data.get("template")
    if not isinstance(template_id, str) or template_id not in {item["id"] for item in RESUME_TEMPLATES}:
        data["template"] = "classic"
    if not isinstance(data.get("accent"), str) or data["accent"] not in {"#1E3A5F", "#0F766E", "#7F1D1D", "#374151", "#166534"}:
        data["accent"] = "#0F766E"
    data["font"] = data.get("font") if isinstance(data.get("font"), str) and data["font"] in {"Lato", "Source Sans", "Merriweather"} else "Lato"
    data["font_size"] = data.get("font_size") if type(data.get("font_size")) is int and data["font_size"] in {9, 10, 11, 12} else 10
    data["spacing"] = data.get("spacing") if isinstance(data.get("spacing"), str) and data["spacing"] in {"compact", "normal", "relaxed"} else "normal"
    for key in ("experience", "education", "projects", "custom_sections"):
        value = data.setdefault(key, [])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            return jsonify(error=f"Invalid {key.replace('_', ' ')} data."), 400
    order = data.get("section_order", ["summary", "experience", "education", "projects", "skills", "custom_sections"])
    valid_sections = {"summary", "experience", "education", "projects", "skills", "custom_sections"}
    if not isinstance(order, list) or any(not isinstance(item, str) or item not in valid_sections for item in order):
        return jsonify(error="Invalid section order."), 400
    data["section_order"] = list(dict.fromkeys(order))
    photo = data.get("photo", "")
    if not isinstance(photo, str) or len(photo) > 140_000 or (photo and not re.fullmatch(r"data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]*={0,2}", photo)):
        return jsonify(error="Invalid profile image."), 400
    raw = json.dumps(data)
    if len(raw) > 200_000:
        return jsonify(error="Resume is too large"), 413

    r.title = (str(payload.get("title", "")).strip() or "Untitled resume")[:120]
    r.data_json = raw
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ok=True)


@app.route("/builder/<int:resume_id>/helper", methods=["POST"])
@login_required
def builder_helper(resume_id):
    resume = get_own_resume(resume_id)
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    content = str(payload.get("content", "")).strip()[:3000]
    role = str(payload.get("role", "")).strip()[:120]
    if action not in {"bullet", "summary", "skills"}:
        return jsonify(error="Choose a supported writing helper."), 400
    if not content and action != "skills":
        return jsonify(error="Add some context first."), 400
    try:
        from analyzer import write_resume_content
        text = write_resume_content(action, content, role)
        return jsonify(text=text)
    except Exception:
        app.logger.exception("Resume writing helper failed for resume %s", resume.id)
        return jsonify(error="The writing helper is unavailable. Please try again."), 503


@app.route("/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete_resume(resume_id):
    db.session.delete(get_own_resume(resume_id))
    db.session.commit()
    flash("Resume deleted.", "success")
    return redirect(url_for("resumes"))


@app.errorhandler(413)
def too_large(e):
    return jsonify(error="File is too large. Maximum size is 4 MB."), 413


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)