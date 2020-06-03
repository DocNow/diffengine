#!/usr/bin/env python
# -*- coding: utf-8 -*-

# maybe this module should be broken up into multiple files, or maybe not ...

UA = "diffengine/0.2.7 (+https://github.com/docnow/diffengine)"

import os
import re
import sys
import time
import yaml
import bleach
import codecs
import jinja2
import shutil
import tweepy
import logging
import argparse
import requests
import htmldiff2
import feedparser
import readability
import unicodedata

from datetime import datetime
from diffengine.exceptions.webdriver import UnknownWebdriverError
from diffengine.exceptions.sendgrid import SendgridConfigNotFoundError, SendgridError
from diffengine.exceptions.twitter import TwitterConfigNotFoundError, TwitterError
from diffengine.text import to_utf8, matches
from diffengine.sendgrid import SendgridHandler
from diffengine.twitter import TwitterHandler
from envyaml import EnvYAML
from peewee import (
    DatabaseProxy,
    CharField,
    DateTimeField,
    OperationalError,
    ForeignKeyField,
    Model,
    SqliteDatabase,
    TextField,
)
from playhouse.db_url import connect
from playhouse.migrate import SqliteMigrator, migrate
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

home = None
config = {}
database = DatabaseProxy()
browser = None


class BaseModel(Model):
    class Meta:
        database = database


class Feed(BaseModel):
    url = TextField(primary_key=True)
    name = TextField()
    created = DateTimeField(default=datetime.utcnow)

    @property
    def entries(self):
        return (
            Entry.select()
            .join(FeedEntry)
            .join(Feed)
            .where(Feed.url == self.url)
            .order_by(Entry.created.desc())
        )

    def get_latest(self):
        """
        Gets the feed and creates new entries for new content. The number
        of new entries created will be returned.
        """
        logging.info("fetching feed: %s", self.url)
        try:
            resp = _get(self.url)
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logging.error("unable to fetch feed %s: %s", self.url, str(e))
            return 0
        count = 0
        for e in feed.entries:
            # note: look up with url only, because there may be
            # overlap bewteen feeds, especially when a large newspaper
            # has multiple feeds
            entry, created = Entry.get_or_create(url=e.link)
            if created:
                FeedEntry.create(entry=entry, feed=self)
                logging.info("found new entry: %s", e.link)
                count += 1
            elif len(entry.feeds.where(Feed.url == self.url)) == 0:
                FeedEntry.create(entry=entry, feed=self)
                logging.debug("found entry from another feed: %s", e.link)
                count += 1

        return count


class Entry(BaseModel):
    url = TextField()
    created = DateTimeField(default=datetime.utcnow)
    checked = DateTimeField(default=datetime.utcnow)
    tweet_status_id_str = CharField(null=False, default="")

    @property
    def feeds(self):
        return Feed.select().join(FeedEntry).join(Entry).where(Entry.id == self.id)

    @property
    def stale(self):
        """
        A heuristic for checking new content very often, and checking
        older content less frequently. If an entry is deemed stale then
        it is worth checking again to see if the content has changed.
        """

        # never been checked before it's obviously stale
        if not self.checked:
            return True

        # time since the entry was created
        hotness = (datetime.utcnow() - self.created).seconds
        if hotness == 0:
            return True

        # time since the entry was last checked
        staleness = (datetime.utcnow() - self.checked).seconds

        # ratio of staleness to hotness
        r = staleness / float(hotness)

        # TODO: allow this magic number to be configured per feed?
        if r >= 0.2:
            logging.debug("%s is stale (r=%f)", self.url, r)
            return True

        logging.debug("%s not stale (r=%f)", self.url, r)
        return False

    def get_latest(self, skip_pattern=None):
        """
        get_latest is the heart of the application. It will get the current
        version on the web, extract its summary with readability and compare
        it against a previous version. If a difference is found it will
        compute the diff, save it as html and png files, and tell Internet
        Archive to create a snapshot.

        If a new version was found it will be returned, otherwise None will
        be returned.
        """

        time_sleep = config.get("time_sleep", 0)
        if time_sleep > 0:
            time.sleep(time_sleep)

        # fetch the current readability-ized content for the page
        logging.info("checking %s", self.url)
        try:
            resp = _get(self.url)
        except Exception as e:
            logging.error("unable to fetch %s: %s", self.url, str(e))
            return None

        if resp.status_code != 200:
            logging.warn("Got %s when fetching %s", resp.status_code, self.url)
            return None

        doc = readability.Document(to_utf8(resp.text))
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p"], strip=True)
        summary = _normal(summary)

        # if the title or the summay contains the skipping pattern,
        # then return none as I don't want to report this change
        if skip_pattern and (
            matches(skip_pattern, title) or matches(skip_pattern, summary)
        ):
            logging.info(
                "Skipped page. It matches the skip_pattern prop defined for this feed."
            )
            return None

        # in case there was a redirect, and remove utm style marketing
        canonical_url = _remove_utm(resp.url)

        # get the latest version, if we have one
        versions = (
            EntryVersion.select()
            .where(EntryVersion.url == canonical_url)
            .order_by(-EntryVersion.created)
            .limit(1)
        )
        if len(versions) == 0:
            old = None
        else:
            old = versions[0]

        # compare what we got against the latest version and create a
        # new version if it looks different, or is brand new (no old version)
        new = None

        # use _equal to determine if the summaries are the same
        if not old or old.title != title or not _equal(old.summary, summary):
            new = EntryVersion.create(
                title=title, url=canonical_url, summary=summary, entry=self
            )
            new.archive()
            if old:
                logging.debug("found new version %s", old.entry.url)
                diff = Diff.create(old=old, new=new)
                if not diff.generate():
                    logging.warn(
                        "html diff showed no changes between versions #%s and #%s: %s",
                        old.id,
                        new.id,
                        self.url,
                    )
                    new.delete()
                    new = None
            else:
                logging.debug("found first version: %s", self.url)
        else:
            logging.debug("content hasn't changed %s", self.url)

        self.checked = datetime.utcnow()
        self.save()

        return new


class FeedEntry(BaseModel):
    feed = ForeignKeyField(Feed)
    entry = ForeignKeyField(Entry)
    created = DateTimeField(default=datetime.utcnow)


class EntryVersion(BaseModel):
    title = TextField()
    url = TextField(index=True)
    summary = TextField()
    created = DateTimeField(default=datetime.utcnow)
    archive_url = TextField(null=True)
    entry = ForeignKeyField(Entry, backref="versions")
    tweet_status_id_str = CharField(null=False, default="")

    @property
    def diff(self):
        """
        The diff that this version created. It can be None if
        this is the first version of a given entry.
        """
        try:
            return Diff.select().where(Diff.new_id == self.id).get()
        except:
            return None

    @property
    def next_diff(self):
        """
        The diff that this version participates in as the previous
        version. I know that's kind of a tongue twister. This can be
        None if this version is the latest we know about.
        """
        try:
            return Diff.select().where(Diff.old_id == self.id).get()
        except:
            return None

    @property
    def html(self):
        return "<h1>%s</h1>\n\n%s" % (self.title, self.summary)

    def archive(self):
        save_url = "https://web.archive.org/save/" + self.url
        try:
            resp = _get(save_url)
            archive_url = resp.headers.get("Content-Location")
            if archive_url:
                self.archive_url = "https://web.archive.org" + archive_url
                logging.debug("archived version at %s", self.archive_url)
                self.save()
                return self.archive_url
            else:
                logging.error(
                    "unable to get archive url from %s [%s]: %s",
                    save_url,
                    resp.status_code,
                    resp.headers,
                )

        except Exception as e:
            logging.error(
                "unexpected archive.org response for %s: %s", save_url, str(e)
            )
        return None


class Diff(BaseModel):
    old = ForeignKeyField(EntryVersion, backref="prev_diffs")
    new = ForeignKeyField(EntryVersion, backref="next_diffs")
    created = DateTimeField(default=datetime.utcnow)
    tweeted = DateTimeField(null=True)
    emailed = DateTimeField(null=True)
    blogged = DateTimeField(null=True)

    @property
    def url_changed(self):
        return self.old.url != self.new.url

    @property
    def title_changed(self):
        return self.old.title != self.new.title

    @property
    def summary_changed(self):
        return self.old.summary != self.new.summary

    @property
    def html_path(self):
        # use prime number to spread across directories
        path = home_path("diffs/%s/%s.html" % ((self.id % 257), self.id))
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        return path

    @property
    def screenshot_path(self):
        return self.html_path.replace(".html", ".png")

    @property
    def thumbnail_path(self):
        return self.screenshot_path.replace(".png", "-thumb.png")

    @property
    def url(self):
        def snap(url):
            m = re.match(r"^https://web.archive.org/web/(\d+?)/.*$", url)
            return m.group(1) if m else None

        return "https://web.archive.org/web/diff/{}/{}/{}/".format(
            snap(self.old.archive_url), snap(self.new.archive_url), self.old.url
        )

    # TODO: configurable option for deleting the diffs after some time (1 week?)
    def generate(self):
        if self._generate_diff_html():
            self._generate_diff_images()
            return True
        else:
            return False

    def _generate_diff_html(self):
        if os.path.isfile(self.html_path):
            return
        tmpl_path = os.path.join(os.path.dirname(__file__), "diff.html")
        logging.debug("creating html diff: %s", self.html_path)
        diff = htmldiff2.render_html_diff(self.old.html, self.new.html)
        if "<ins>" not in diff and "<del>" not in diff:
            return False
        tmpl = jinja2.Template(codecs.open(tmpl_path, "r", "utf8").read())
        html = tmpl.render(
            title=self.new.title,
            url=self.old.entry.url,
            old_url=self.old.archive_url,
            old_time=self.old.created,
            new_url=self.new.archive_url,
            new_time=self.new.created,
            diff=diff,
        )
        codecs.open(self.html_path, "w", "utf8").write(html)
        return True

    def _generate_diff_images(self):
        if os.path.isfile(self.screenshot_path):
            return

        logging.debug("creating image screenshot %s", self.screenshot_path)
        browser.set_window_size(1400, 1000)
        uri = "file:///" + os.path.abspath(self.html_path)
        browser.get(uri)
        time.sleep(5)  # give the page time to load
        browser.save_screenshot(self.screenshot_path)
        logging.debug("creating image thumbnail %s", self.thumbnail_path)
        browser.set_window_size(800, 400)
        browser.execute_script("clip()")
        browser.save_screenshot(self.thumbnail_path)


def setup_logging(log_file=True, log_console=False):
    # TODO. Configurable verbosity
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_formatter = logging.Formatter(log_format)

    handlers = []
    if log_file:
        filename = config.get("log", home_path("diffengine.log"))
        file_handler = logging.FileHandler(filename=filename, mode="a")
        file_handler.setFormatter(log_formatter)
        handlers.append(file_handler)

    if log_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)
        handlers.append(console_handler)

    if handlers:
        logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)
        logging.getLogger("readability.readability").setLevel(logging.WARNING)
        logging.getLogger("tweepy.binder").setLevel(logging.WARNING)


def load_config(prompt=True):
    global config
    config_file = os.path.join(home, "config.yaml")
    env_file = home_path(".env")
    if os.path.isfile(config_file):
        config = EnvYAML(
            config_file, env_file=env_file if os.path.isfile(env_file) else None
        )
    else:
        if not os.path.isdir(home):
            os.makedirs(home)
        if prompt:
            config = get_initial_config()
        yaml.dump(config, open(config_file, "w"), default_flow_style=False)
    return config


def get_auth_link_and_show_token():
    global home
    home = os.getcwd()
    config = load_config(True)
    twitter = config["twitter"]
    token = request_pin_to_user_and_get_token(
        twitter["consumer_key"], twitter["consumer_secret"]
    )
    print("\nThese are your access token and secret.\nDO NOT SHARE THEM WITH ANYONE!\n")
    print("ACCESS_TOKEN\n%s\n" % token[0])
    print("ACCESS_TOKEN_SECRET\n%s\n" % token[1])


def get_initial_config():
    config = {"feeds": []}

    while len(config["feeds"]) == 0:
        url = input("What RSS/Atom feed would you like to monitor? ")
        feed = feedparser.parse(url)
        if len(feed.entries) == 0:
            print("Oops, that doesn't look like an RSS or Atom feed.")
        else:
            config["feeds"].append({"url": url, "name": feed.feed.title})

    answer = input("Would you like to set up tweeting edits? [Y/n] ") or "Y"
    if answer.lower() == "y":
        print("Go to https://apps.twitter.com and create an application.")
        consumer_key = input("What is the consumer key? ")
        consumer_secret = input("What is the consumer secret? ")

        token = request_pin_to_user_and_get_token(consumer_key, consumer_secret)

        config["twitter"] = {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
        }
        config["feeds"][0]["twitter"] = {
            "access_token": token[0],
            "access_token_secret": token[1],
        }

    answer = input("Would you like to set up emailing edits? [Y/n] ")
    if answer.lower() == "y":
        print("Go to https://app.sendgrid.com/ and get an API key.")
        api_key = input("What is the API key? ")
        sender = input("What email address is sending the email? ")
        receivers = input("Who are receiving the emails?  ")

        config["sendgrid"] = {"api_key": api_key}

        config["feeds"][0]["sendgrid"] = {"sender": sender, "receivers": receivers}

    print("Saved your configuration in %s/config.yaml" % home.rstrip("/"))
    print("Fetching initial set of entries.")

    return config


def request_pin_to_user_and_get_token(consumer_key, consumer_secret):
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.secure = True
    auth_url = auth.get_authorization_url()
    input(
        "Log in to https://twitter.com as the user you want to tweet as and hit enter."
    )
    input("Visit %s in your browser and hit enter." % auth_url)
    pin = input("What is your PIN: ")
    return auth.get_access_token(verifier=pin)


def home_path(rel_path):
    return os.path.join(home, rel_path)


def setup_db():
    global home, database
    database_url = config.get("db", "sqlite:///diffengine.db")
    logging.debug("connecting to db %s", database_url)
    database_handler = connect(database_url)
    database.initialize(database_handler)
    database.connect()
    database.create_tables([Feed, Entry, FeedEntry, EntryVersion, Diff], safe=True)

    if isinstance(database_handler, SqliteDatabase):
        try:
            migrator = SqliteMigrator(database_handler)
            migrate(migrator.add_index("entryversion", ("url",), False))
        except OperationalError as e:
            logging.debug(e)


def chromedriver_browser(executable_path, binary_location):
    options = ChromeOptions()
    options.binary_location = binary_location
    options.add_argument("--headless")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(executable_path=executable_path, options=options)


def geckodriver_browser():
    opts = FirefoxOptions()
    opts.headless = True
    return webdriver.Firefox(options=opts)


def setup_browser(engine="geckodriver", executable_path=None, binary_location=""):
    global browser

    if engine not in ["chromedriver", "geckodriver"]:
        raise UnknownWebdriverError(engine)

    if not shutil.which(engine):
        sys.exit("Please install %s and make sure it is in your PATH." % engine)

    if engine == "chromedriver":
        return chromedriver_browser(
            engine if executable_path is None else executable_path, binary_location
        )

    if engine == "geckodriver":
        return geckodriver_browser()


def init(new_home, prompt=True):
    global home, config, browser
    home = new_home
    load_config(prompt)
    try:
        # by defualt keep using geckodriver
        engine = config.get("webdriver.engine", "geckodriver")
        executable_path = config.get("webdriver.executable_path")
        binary_location = config.get("webdriver.binary_location")
        browser = setup_browser(engine, executable_path, binary_location)
        setup_logging(
            config.get("logger.file", True), config.get("logger.console", False)
        )
        setup_db()
    except RuntimeError as e:
        logging.error("Could not finish the setup", str(e))


def main():
    if len(sys.argv) == 1:
        home = os.getcwd()
    else:
        home = sys.argv[1]

    init(home)
    start_time = datetime.utcnow()
    logging.info("starting up with home=%s", home)
    lang = config.get("lang", {})

    try:
        twitter_config = config.get("twitter", {})
        twitter_handler = TwitterHandler(
            twitter_config["consumer_key"], twitter_config["consumer_secret"]
        )
    except TwitterConfigNotFoundError as e:
        twitter_handler = None
        logging.warning("error when creating Twitter Handler. Reason", str(e))
    except KeyError as e:
        twitter_handler = None
        logging.warning("the twitter keys are not present in config. Reason", str(e))

    sendgrid_config = config.get("sendgrid", {})
    sendgrid_handler = SendgridHandler(sendgrid_config)

    checked = skipped = new = 0

    for f in config.get("feeds", []):
        feed, created = Feed.get_or_create(url=f["url"], name=f["name"])
        if created:
            logging.debug("created new feed for %s", f["url"])

        # get latest feed entries
        feed.get_latest()

        # get latest content for each entry
        for entry in feed.entries:
            result = process_entry(entry, f, twitter_handler, sendgrid_handler, lang)
            skipped += result["skipped"]
            checked += result["checked"]
            new += result["new"]

    elapsed = datetime.utcnow() - start_time
    logging.info(
        "shutting down: new=%s checked=%s skipped=%s elapsed=%s",
        new,
        checked,
        skipped,
        elapsed,
    )

    browser.quit()


def process_entry(entry, feed_config={}, twitter=None, sendgrid=None, lang={}):
    result = {"skipped": 0, "checked": 0, "new": 0}
    if not entry.stale:
        result["skipped"] = 1
    else:
        result["checked"] = 1
        try:
            skip_pattern = feed_config.get("skip_pattern")
            version = entry.get_latest(skip_pattern)
            if version:
                result["new"] = 1
                if version.diff:
                    try:
                        token = feed_config.get("twitter", {})
                        if token:
                            twitter.tweet_diff(version.diff, token, lang)
                    except TwitterError as e:
                        logging.warning("error occurred while trying to tweet", str(e))
                    except Exception as e:
                        logging.error("unknown error when tweeting diff", e)

                    try:
                        sendgrid.publish_diff(
                            version.diff, feed_config.get("sendgrid", {})
                        )

                    except SendgridConfigNotFoundError as e:
                        logging.error(
                            "Missing configuration values for publishing entry %s",
                            entry.url,
                        )
                    except SendgridError as e:
                        logging.warning(
                            "error occurred while trying to email with sendgrid ",
                            str(e),
                        )
                    except Exception as e:
                        logging.error("unknown error when tweeting diff", str(e))

        except Exception as e:
            logging.error("unable to get latest", e)

    return result


def _dt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _normal(s):
    # additional normalizations for readability + bleached text
    s = s.replace("\xa0", " ")
    s = s.replace("“", '"')
    s = s.replace("”", '"')
    s = s.replace("’", "'")
    s = s.replace("\n", " ")
    s = s.replace("­", "")
    s = re.sub(r"  +", " ", s)
    s = s.strip()
    return s


def _equal(s1, s2):
    return _fingerprint(s1) == _fingerprint(s2)


punctuation = dict.fromkeys(
    i for i in range(sys.maxunicode) if unicodedata.category(chr(i)).startswith("P")
)


def _fingerprint(s):
    # make sure the string has been normalized, bleach everything, remove all
    # whitespace and punctuation to create a pseudo fingerprint for the text
    # for use during comparison
    s = _normal(s)
    s = bleach.clean(s, tags=[], strip=True)
    s = re.sub(r"\s+", "", s, flags=re.MULTILINE)
    s = s.translate(punctuation)
    return s


def _remove_utm(url):
    u = urlparse(url)
    q = parse_qs(u.query, keep_blank_values=True)
    new_q = dict((k, v) for k, v in q.items() if not k.startswith("utm_"))
    return urlunparse(
        [u.scheme, u.netloc, u.path, u.params, urlencode(new_q, doseq=True), u.fragment]
    )


def _get(url, allow_redirects=True):
    return requests.get(
        url, timeout=60, headers={"User-Agent": UA}, allow_redirects=allow_redirects
    )


if __name__ == "__main__":
    # Cli options
    parser = argparse.ArgumentParser()
    parser.add_argument("--add", action="store_true")
    options = parser.parse_args()

    if options.add:
        get_auth_link_and_show_token()
    else:
        main()
    sys.exit("Finishing diffengine")
