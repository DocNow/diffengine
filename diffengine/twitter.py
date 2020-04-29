import logging
import tweepy

from datetime import datetime


def build_text(diff):
    text = diff.new.title
    if len(text) >= 225:
        text = text[0:225] + "…"
    text += " " + diff.url

    return text


class Twitter:
    consumer_key = None
    consumer_secret = None

    def __init__(self, config):
        twitter_config = config.get("twitter", None)
        if twitter_config is None:
            logging.debug("twitter not configured")
            return
        elif (
            not twitter_config["consumer_key"] or not twitter_config["consumer_secret"]
        ):
            logging.debug("consumer key/secret not set up for feed")
            return

        self.consumer_key = twitter_config["consumer_key"]
        self.consumer_secret = twitter_config["consumer_secret"]

        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_key)
        auth.secure = True
        self.auth = auth

    def api(self, token):
        self.auth.set_access_token(token["access_token"], token["access_token_secret"])
        return tweepy.API(self.auth)

    def tweet_thread(self, entry, first_version, token):
        if not token:
            logging.debug("access token/secret not set up for feed")
            return
        elif entry.tweet_status_id_str:
            logging.warning("entry %s has already been tweeted", entry.id)
            return

        twitter = self.api(token)
        status = twitter.update_status(entry.url)
        entry.tweet_status_id_str = status.id_str
        entry.save()

        # Save the entry status_id inside the first entryVersion
        first_version.tweet_status_id_str = status.id_str
        first_version.save()
        return status.id_str

    def tweet_diff(self, diff, token):
        if not token:
            logging.debug("access token/secret not set up for feed")
            return
        elif diff.tweeted:
            logging.warning("diff %s has already been tweeted", diff.id)
            return
        elif not (diff.old.archive_url and diff.new.archive_url):
            logging.warning("not tweeting without archive urls")
            return

        twitter = self.api(token)
        text = build_text(diff)

        # Check if the thread exists
        thread_status_id_str = None
        if diff.old.entry.tweet_status_id_str is None:
            try:
                thread_status_id_str = self.tweet_thread(
                    diff.old.entry, diff.old, token
                )
                logging.info(
                    "created thread https://twitter/%s/status/%s"
                    % (self.auth.get_username(), thread_status_id_str)
                )
            except Exception as e:
                logging.error(
                    "could not create thread on entry %s" % diff.old.entry.url, e
                )
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
