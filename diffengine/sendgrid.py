import logging

from datetime import datetime
from sendgrid import Mail, Bcc, SendGridAPIClient

from diffengine.exceptions.sendgrid import (
    AlreadyEmailedError,
    SendgridConfigNotFoundError,
    SendgridArchiveUrlNotFoundError,
)


class SendgridHandler:
    api_token = None
    sender = None
    recipients = None

    def __init__(self, config):

        if not all(["api_token" in config, "sender" in config, "recipients" in config]):
            logging.warning(
                "No global config found for sendgrid, expecting config set for each feed"
            )

        self.api_token = config.get("api_token")
        self.sender = config.get("sender")
        self.recipients = self.build_recipients(config.get("recipients"))

    def mailer(self, api_token):
        return SendGridAPIClient(api_token)

    def build_recipients(self, recipients):
        if recipients:
            return [Bcc(x.strip()) for x in recipients.split(",")]

    def build_subject(self, diff):
        return diff.old.title

    def build_html_body(self, diff):
        body = None
        with open(diff.html_path) as html_file:
            body = html_file.read()

        return body

    def publish_diff(self, diff, feed_config):
        if diff.emailed:
            raise AlreadyEmailedError(diff.id)
        elif not (diff.old.archive_url and diff.new.archive_url):
            raise SendgridArchiveUrlNotFoundError()

        api_token = feed_config.get("api_token", self.api_token)
        sender = feed_config.get("sender", self.sender)

        recipients = None
        if feed_config.get("recipients"):
            recipients = self.build_recipients(feed_config.get("recipients"))
        else:
            recipients = self.recipients
        if not all([api_token, sender, recipients]):
            raise SendgridConfigNotFoundError

        subject = self.build_subject(diff)
        message = Mail(
            from_email=sender, subject=subject, html_content=self.build_html_body(diff)
        )
        message.bcc = recipients
        try:
            self.mailer(api_token).send(message)
            diff.emailed = datetime.utcnow()
            logging.info("emailed %s", subject)
            diff.save()
        except Exception as e:
            logging.error("unable to email: %s", e)
