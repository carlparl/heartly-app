from django.conf import settings
from django.core.mail import send_mail

from .models import EmailVerificationCode


def send_email_verification_code(user):
    verification, raw_code = EmailVerificationCode.create_for_user(user)

    subject = "Your Heartly verification code"

    message = (
        f"Your Heartly verification code is: {raw_code}\n\n"
        "This code expires in 10 minutes.\n"
        "If you did not request this code, you can ignore this email."
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            "Heartly <noreply@heartly.local>",
        ),
        recipient_list=[user.email],
        fail_silently=False,
    )

    return verification