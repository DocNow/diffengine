import logging
import tweepy

from datetime import datetime

from diffengine.text import build_text
from exceptions.twitter import (
    AlreadyTweetedError,
    TwitterConfigNotFoundError,
    TokenNotFoundError,
    TwitterAchiveUrlNotFoundError,
    UpdateStatusError,
)


class TwitterHandler:
    consumer_key = None
    consumer_secret = None

    def __init__(self, consumer_key, consumer_secret):
        if not consumer_key or not consumer_secret:
            raise TwitterConfigNotFoundError()

        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.secure = True
        self.auth = auth

    def api(self, token):
        self.auth.set_access_token(token["access_token"], token["access_token_secret"])
        return tweepy.API(self.auth)

    def build_text(self, diff):
        text = diff.new.title
        if len(text) >= 225:
            text = text[0:225] + "…"
        text += " " + diff.url
        return text

    def create_thread(self, entry, first_version, token):
        try:
            twitter = self.api(token)
            status = twitter.update_status(entry.url)
            entry.tweet_status_id_str = status.id_str
            entry.save()

            # Save the entry status_id inside the first entryVersion
            first_version.tweet_status_id_str = status.id_str
            first_version.save()
            return status.id_str
        except Exception as e:
            raise UpdateStatusError(entry)

    def tweet_diff(self, diff, token=None, lang={}):
        if not token:
            raise TokenNotFoundError()
        elif diff.tweeted:
            raise AlreadyTweetedError(diff)
        elif not (diff.old.archive_url and diff.new.archive_url):
            raise TwitterAchiveUrlNotFoundError(diff)

        twitter = self.api(token)
        text = build_text(diff, lang)

        # Check if the thread exists
        thread_status_id_str = None
        if diff.old.entry.tweet_status_id_str == "":
            try:
                thread_status_id_str = self.create_thread(
                    diff.old.entry, diff.old, token
                )
                logging.info(
                    "created thread https://twitter.com/%s/status/%s"
                    % (self.auth.get_username(), thread_status_id_str)
                )
            except UpdateStatusError as e:
                logging.error(str(e))
        else:
            thread_status_id_str = diff.old.tweet_status_id_str

        try:
            status = twitter.update_with_media(
                diff.thumbnail_path,
                status=text,
                in_reply_to_status_id=thread_status_id_str,
            )
            logging.info(
                "tweeted diff https://twitter.com/%s/status/%s"
                % (self.auth.get_username(), status.id_str)
            )
            # Save the tweet status id inside the new version
            diff.new.tweet_status_id_str = status.id_str
            diff.new.save()
            # And save that the diff has been tweeted
            diff.tweeted = datetime.utcnow()
            diff.save()
        except Exception as e:
            logging.error("unable to tweet: %s", e)

    def delete_diff(self, diff, token=None):
        twitter = self.api(token)
        twitter.destroy_status(diff.old.tweet_status_id_str)
        twitter.destroy_status(diff.new.tweet_status_id_str)
