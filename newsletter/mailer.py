"""
이메일 발송 모듈 - MJML 템플릿 → 이메일 전용 HTML 변환 후 발송
"""
import smtplib, os, base64, uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
from email.utils import formataddr
from jinja2 import Environment, FileSystemLoader
import mjml

TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))

def render_email_html(data: dict, image_cid: str = "", logo_cid: str = "") -> str:
    """MJML 템플릿 → Jinja2 렌더링 → MJML 컴파일 → 이메일용 HTML"""
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    # 1. MJML 템플릿에 Jinja2 변수 주입
    mjml_tmpl = env.get_template("template.mjml")
    rendered_mjml = mjml_tmpl.render(**data, schedule_image_cid=image_cid, logo_cid=logo_cid)

    # 2. MJML → HTML 컴파일
    result = mjml.mjml_to_html(rendered_mjml)
    if result.errors:
        raise RuntimeError(f"MJML 컴파일 오류: {result.errors}")
    return result.html

def send_newsletter(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,          # 웹 미리보기용 (사용 안 함, 호환성 유지)
    smtp_host: str = None,
    smtp_port: int = None,
    smtp_user: str = None,
    smtp_pass: str = None,
    template_data: dict = None,
    image_path: str = "",
    logo_path: str = "",
) -> dict:
    host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
    user = smtp_user or os.getenv("SMTP_USER", "")
    pwd  = smtp_pass or os.getenv("SMTP_PASS", "")

    # 포트 25 (사내 릴레이)는 인증 없이도 허용
    if not user and port != 25:
        return {"ok": False, "error": "SMTP 계정 정보 없음"}

    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"]    = formataddr((str(Header("광동제약", "utf-8")), user))
        msg["To"]      = to_email

        # 이미지 CID 처리
        image_cid = ""
        logo_cid = ""
        img_mime = None
        logo_mime = None
        if image_path and os.path.exists(image_path):
            image_cid = f"scheduleimg_{uuid.uuid4().hex[:8]}"
            with open(image_path, "rb") as f:
                img_data = f.read()
            ext = os.path.splitext(image_path)[-1].lower().replace(".", "")
            ext = "jpeg" if ext == "jpg" else ext
            img_mime = MIMEImage(img_data, _subtype=ext)
            img_mime.add_header("Content-ID", f"<{image_cid}>")
            img_mime.add_header("Content-Disposition", "inline")

        # 로고 CID 처리
        if logo_path and os.path.exists(logo_path):
            logo_cid = f"logoimg_{uuid.uuid4().hex[:8]}"
            with open(logo_path, "rb") as f:
                logo_data = f.read()
            logo_mime = MIMEImage(logo_data, _subtype="png")
            logo_mime.add_header("Content-ID", f"<{logo_cid}>")
            logo_mime.add_header("Content-Disposition", "inline")

        # 이메일 전용 HTML 렌더링
        if template_data:
            email_html = render_email_html(template_data, image_cid, logo_cid)
        else:
            email_html = html_body  # 폴백

        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(email_html, "html", "utf-8"))
        msg.attach(alt_part)

        if img_mime:
            msg.attach(img_mime)
        if logo_mime:
            msg.attach(logo_mime)

        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            # 포트 587: STARTTLS + 인증 / 포트 25: 인증 없이 직접 릴레이
            if port == 587:
                server.starttls()
                server.login(user, pwd)
            elif user and pwd:
                server.login(user, pwd)
            server.sendmail(user or "noreply", [to_email], msg.as_string())

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
