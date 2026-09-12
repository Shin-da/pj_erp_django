from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def queue_login_sound(sender, request, user, **kwargs):
    """Flag the next page render to play the 'login' alert sound.

    Read (and cleared) by apps.core.context_processors.alert_sound.
    """
    request.session["pj_alert_sound"] = "login"
