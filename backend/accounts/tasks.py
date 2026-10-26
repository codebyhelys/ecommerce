from celery import shared_task


@shared_task(
    name="accounts.send_password_reset_email",
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_password_reset_email_task(user_id):
    from .emails import deliver_password_reset_email

    deliver_password_reset_email(user_id)
