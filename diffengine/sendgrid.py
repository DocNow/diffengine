import logging

from datetime import datetime
from sendgrid import Mail, SendGridAPIClient

from exceptions.sendgrid import (
    AlreadyEmailedError,
    ConfigNotFoundError,
    AchiveUrlNotFoundError
)


class SendgridHandler:
    api_token = None
    sender = None
    receivers = None

    def __init__(self, config):

        if not all(["api_token" in config, "sender" in config,
                    "receivers" in config]):
            raise ConfigNotFoundError()

        self.api_token = config["api_token"]
        self.sender = config["sender"]
        self.receivers = config["receivers"]

    def mailer(self):
        return SendGridAPIClient(self.api_token)

    def build_subject(self, diff):
        return diff.old.title

    def build_hmtl_body(self, diff):
        body = None
        with open(diff.html_path) as html_file:
            body = html_file.read()

        return body

    def publish_diff(self, diff):
        if diff.emailed:
            raise AlreadyEmailedError(diff.id)
        elif not (diff.old.archive_url and diff.new.archive_url):
            raise AchiveUrlNotFoundError()

        subject = self.build_subject(diff)
        message = Mail(
            from_email=self.sender,
            to_emails=self.receivers,
            subject=subject,
            html_content=self.build_html_body(diff)
        )

        try:
            self.mailer.send(message)
            diff.emailed = datetime.utcnow()
            logging.info("emailed %s", subject)
            diff.save()
        except Exception as e:
            logging.error("unable to email: %s", e)
