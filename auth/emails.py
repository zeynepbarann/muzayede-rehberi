#!/usr/bin/env python3
"""The sign-in settings and the emails people receive (Firebase project art1622-web).

Run:  python auth/emails.py
It uses your gcloud sign-in (no key file), sets email sign-in to password only (no sign-in links) and the sites allowed
to sign in, and writes the two emails to auth/verify-email.html and auth/reset-email.html.
On the free plan Firebase only accepts email designs pasted in its console (Authentication > Templates); the action URL
there is set to https://1622art.com/ so the buttons open the site, which finishes the step.
Firebase fills in %LINK% and %EMAIL%.
"""
import json, os, subprocess, urllib.request

PROJECT = "art1622-web"
SITE = "https://1622art.com/"
DOMAINS = ["localhost", "art1622-web.firebaseapp.com", "art1622-web.web.app", "1622art.com", "www.1622art.com", "zeynepbarann.github.io"]


def page(title, lead, button, note):
    """One email: white page, serif heading, a thin gold line and a single black button. Inline styles only, as mail apps need."""
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:0;background:#f6f5f2">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f5f2;padding:24px 10px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:520px;background:#ffffff;border:1px solid #ecebe7;table-layout:fixed">
<tr><td style="padding:30px 26px 0;font:500 26px/1 Georgia,'Times New Roman',serif;color:#111110;letter-spacing:-0.5px">16/22</td></tr>
<tr><td style="padding:10px 26px 0"><div style="width:44px;height:2px;background:#b08d3c"></div></td></tr>
<tr><td style="padding:24px 26px 0;font:400 28px/1.2 Georgia,'Times New Roman',serif;color:#111110">{title}</td></tr>
<tr><td style="padding:14px 26px 0;font:400 16px/1.6 Helvetica,Arial,sans-serif;color:#3a3936">{lead}</td></tr>
<tr><td style="padding:26px 26px 0"><a href="%LINK%" style="display:inline-block;padding:16px 30px;background:#111110;color:#ffffff;text-decoration:none;font:600 15px/1 Helvetica,Arial,sans-serif;letter-spacing:0.3px">{button}</a></td></tr>
<tr><td style="padding:22px 26px 0;font:400 13px/1.6 Helvetica,Arial,sans-serif;color:#6b6963">{note}<br>Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın:<br><a href="%LINK%" style="color:#6b6963;word-break:break-all">%LINK%</a></td></tr>
<tr><td style="padding:26px 26px 30px;font:400 12px/1.6 Helvetica,Arial,sans-serif;color:#9a978f;border-top:1px solid #ecebe7">16/22 Müzayede Rehberi · <a href="{SITE}" style="color:#9a978f">1622art.com</a><br>Bu e-postayı %EMAIL% adresiyle 16/22'de bir işlem yapıldığı için aldınız.</td></tr>
</table></td></tr></table></body></html>"""


VERIFY = page("E-posta adresinizi doğrulayın",
              "16/22'ye hoş geldiniz. Hesabınızı tamamlamak için aşağıdaki düğmeye dokunun. Böylece favori sanatçılarınız ve kaydettiğiniz eserler, giriş yaptığınız her cihazda sizi bekler.",
              "E-postamı doğrula",
              "Bu hesabı siz oluşturmadıysanız bu e-postayı yok sayabilirsiniz.")
RESET = page("Şifrenizi yenileyin",
             "16/22 hesabınız için şifre yenileme isteği aldık. Yeni bir şifre belirlemek için aşağıdaki düğmeye dokunun. Bağlantı bir saat geçerlidir.",
             "Yeni şifre belirle",
             "Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz; şifreniz değişmez.")


def main():
    gcloud = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Cloud SDK", "google-cloud-sdk", "bin", "gcloud.cmd")
    token = subprocess.run([gcloud if os.path.exists(gcloud) else "gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()
    body = {"signIn": {"email": {"enabled": True, "passwordRequired": True}}, "authorizedDomains": DOMAINS}
    req = urllib.request.Request(f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config?updateMask=signIn.email,authorizedDomains", data=json.dumps(body).encode(), method="PATCH",
                                 headers={"Authorization": "Bearer " + token, "x-goog-user-project": PROJECT, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req))
    print("email:", d["signIn"]["email"], "| domains:", ", ".join(d["authorizedDomains"]))
    here = os.path.dirname(os.path.abspath(__file__))
    for name, html in (("verify-email.html", VERIFY), ("reset-email.html", RESET)):
        with open(os.path.join(here, name), "w", encoding="utf8") as f:
            f.write(html)
    print("wrote auth/verify-email.html and auth/reset-email.html")


if __name__ == "__main__":
    main()
