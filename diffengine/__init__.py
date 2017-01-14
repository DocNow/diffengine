#!/usr/bin/env python

# maybe this module should be broken up into multiple files, or maybe not ...

UA = "diffengine/0.0.1 (+https://github.com/edsu/diffengine)"

import os
import re
import sys
import json
import time
import yaml
import bleach
import codecs
import jinja2
import tweepy
import logging
import htmldiff
import requests
import selenium
import feedparser
import subprocess
import readability

from peewee import *
from datetime import datetime, timedelta
from selenium import webdriver
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

home = None
config = {}
db = SqliteDatabase(None)

class BaseModel(Model):
    class Meta:
        database = db

class Feed(BaseModel):
    url = CharField(primary_key=True)
    name = CharField()
    created = DateTimeField(default=datetime.utcnow)
    
    @property
    def entries(self):
        return (Entry.select()
                .join(FeedEntry)
                .join(Feed)
                .where(Feed.url==self.url))

    def get_latest(self):
        """
        Gets the feed and creates new entries for new content.
        """
        logging.info("fetching feed: %s", self.url)
        feed = feedparser.parse(self.url)
        for e in feed.entries:
            # TODO: look up with url only, because there may be 
            # overlap bewteen feeds, especially when a large newspaper
            # has multiple feeds
            entry, created = Entry.get_or_create(url=e.link)
            if created:
                FeedEntry.create(entry=entry, feed=self)
                logging.info("found new entry: %s", e.link)
            elif len(entry.feeds.where(Feed.url == self.url)) == 0: 
                FeedEntry.create(entry=entry, feed=self)
                logging.info("found entry from another feed: %s", e.link)


class Entry(BaseModel):
    url = CharField()
    created = DateTimeField(default=datetime.utcnow)
    checked = DateTimeField(default=datetime.utcnow)

    @property
    def feeds(self):
        return (Feed.select()
                .join(FeedEntry)
                .join(Entry)
                .where(Entry.id==self.id))

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

    def get_latest(self, force=True):
        """
        get_latest is the heart of the application. If the entry is stale
        it will get the current version on the web, extract its summary with 
        readability and compare it against a previous version. If a difference
        is found it will compute the diff, save it as html and png files, and
        tell Internet Archive to create a snapshot.
        """

        if not self.stale and not force:
            return

        # make sure we don't go too fast
        time.sleep(1)

        # fetch the current readability-ized content for the page
        logging.info("checking %s", self.url)
        resp = requests.get(self.url, headers={"User-Agent": UA})
        if resp.status_code != 200:
            logging.warn("Got %s when fetching %s", resp.status_code, self.url)
            return

        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p"], strip=True)

        # in case there was a redirect, and remove utm style marketing
        canonical_url = _remove_utm(resp.url)

        # little cleanups that should be in a function if they grow more
        summary = summary.replace("\xa0", " ")
        summary = summary.replace('“', '"')
        summary = summary.replace('”', '"')

        # get the latest version, if we have one
        versions = EntryVersion.select().where(EntryVersion.entry==self)
        versions = versions.order_by(-EntryVersion.created)
        if len(versions) == 0:
            old = None
        else:
            old = versions[0]

        # compare what we got against the latest version and create a 
        # new version if it looks different, or is brand new (no old version)
        new = None

        if not old or old.title != title or old.summary != summary:
            new = EntryVersion.create(
                title=title,
                url=canonical_url,
                summary=summary,
                entry=self
            )
            new.archive()
            if old:
                logging.info("found new version %s", old.entry.url)
                diff = Diff.create(old=old, new=new)
                diff.generate()
            else:
                logging.info("found first version: %s", self.url)
        else:
            logging.info("content hasn't changed %s", self.url)

        self.checked = datetime.utcnow()
        self.save()
        return new


class FeedEntry(BaseModel):
    feed = ForeignKeyField(Feed)
    entry = ForeignKeyField(Entry)
    created = DateTimeField(default=datetime.utcnow)


class EntryVersion(BaseModel):
    title = CharField()
    url = CharField()
    summary = CharField()
    created = DateTimeField(default=datetime.utcnow)
    archive_url = CharField(null=True)
    entry = ForeignKeyField(Entry, related_name='versions')

    @property
    def diff(self):
        """
        The diff that this version created. It can be None if
        this is the first version of a given entry.
        """
        try:
            return Diff.select().where(Diff.new_id==self.id).get()
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
            return Diff.select().where(Diff.old_id==self.id).get()
        except:
            return None

    @property
    def html(self):
        return "<h1>%s</h1>\n\n%s" % (self.title, self.summary)

    def archive(self):
        try:
            save_url = "https://web.archive.org/save/" + self.url
            resp = requests.get(save_url, headers={"User-Agent": UA})
            wayback_id = resp.headers.get("Content-Location")
            self.archive_url = "https://wayback.archive.org" + wayback_id
            logging.info("archived version at %s", self.archive_url)
            self.save()
            return self.archive_url
        except Exception as e:
            logging.error(
                "unexpected archive.org response for %s ; headers=%s ; %s", 
                save_url, resp.headers, e
            )
            return

class Diff(BaseModel):
    old = ForeignKeyField(EntryVersion, related_name="prev_diffs")
    new = ForeignKeyField(EntryVersion, related_name="next_diffs")
    created = DateTimeField(default=datetime.utcnow)
    tweeted = DateTimeField(null=True)
    blogged = DateTimeField(null=True)

    @property
    def html_path(self):
        # use prime number to spread across directories
        path = home_path("diffs/%s/%s.html" % ((self.id % 257), self.id))
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        return path

    @property
    def screenshot_path(self):
        return self.html_path.replace(".html", ".jpg")

    @property
    def thumbnail_path(self):
        return self.screenshot_path.replace('.jpg', '-thumb.jpg')

    def generate(self):
        self._generate_diff_html()
        self._generate_diff_images()


    def _generate_diff_html(self):
        if os.path.isfile(self.html_path):
            return
        tmpl_path = os.path.join(os.path.dirname(__file__), "diff.html")
        logging.info("creating html diff: %s", self.html_path)
        diff = htmldiff.render_html_diff(self.old.html, self.new.html)
        tmpl = jinja2.Template(codecs.open(tmpl_path, "r", "utf8").read())
        html = tmpl.render(
            title=self.new.title,
            url=self.old.entry.url,
            old_url=self.old.archive_url,
            old_time=self.old.created,
            new_url=self.new.archive_url,
            new_time=self.new.created,
            diff=diff
        )
        codecs.open(self.html_path, "w", 'utf8').write(html)

    def _generate_diff_images(self):
        if os.path.isfile(self.screenshot_path):
            return
        if not hasattr(self, 'browser'):
            phantomjs = config.get('phantomjs', 'phantomjs')
            self.browser = webdriver.PhantomJS(phantomjs)
        logging.info("creating image screenshot %s", self.screenshot_path)
        self.browser.set_window_size(1400, 1000)
        self.browser.get(self.html_path)
        self.browser.save_screenshot(self.screenshot_path)
        logging.info("creating image thumbnail %s", self.thumbnail_path)
        self.browser.set_window_size(800, 400)
        self.browser.execute_script("clip()")
        self.browser.save_screenshot(self.thumbnail_path)


def setup_logging():
    path = config.get('log', home_path('diffengine.log'))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=path,
        filemode="a"
    )

def load_config(prompt=True):
    global config
    config_file = os.path.join(home, "config.yaml")
    if os.path.isfile(config_file):
        config = yaml.load(open(config_file))
    else:
        if not os.path.isdir(home):
            os.makedirs(home)
        if prompt:
            config = get_initial_config()
        yaml.dump(config, open(config_file, "w"), default_flow_style=False)

def get_initial_config():
    config = {"feeds": [], "phantomjs": "phantomjs"}

    while len(config['feeds']) == 0:
        url = input("What RSS/Atom feed would you like to monitor? ")
        feed = feedparser.parse(url)
        if len(feed.entries) == 0:
            print("Oops, that doesn't look like an RSS or Atom feed.")
        else:
            config['feeds'].append({
                "url": url,
                "name": feed.feed.title
            })

    answer = input("Would you like to set up tweeting edits? [Y/n] ")
    if answer.lower() == "y":
        print("Go to https://apps.twitter.com and create an application.")
        consumer_key = input("What is the consumer key? ")
        consumer_secret = input("What is the consumer secret? ")
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.secure = True
        auth_url = auth.get_authorization_url()
        input("Log in to https://twitter.com as the user you want to tweet as and hit enter.")
        input("Visit %s in your browser and hit enter." % auth_url)
        pin = input("What is your PIN: ")
        token = auth.get_access_token(verifier=pin)
        config["twitter"] = {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret
        }
        config["feeds"][0]["twitter"] = {
            "access_token": token[0],
            "access_token_secret": token[1]
        }

    print("Saved your configuration in %s/config.yaml" % home.rstrip("/"))
    print("Fetching initial set of entries.")

    return config

def home_path(rel_path):
    return os.path.join(home, rel_path)

def setup_db():
    global db
    db_file = config.get('db', home_path('diffengine.db'))
    logging.debug("connecting to db %s", db_file)
    db.init(db_file)
    db.connect()
    db.create_tables([Feed, Entry, FeedEntry, EntryVersion, Diff], safe=True)

def setup_phantomjs():
    phantomjs = config.get("phantomjs", "phantomjs")
    try:
        subprocess.check_output([phantomjs, '--version'])
    except FileNotFoundError:
        print("Please install phantomjs <http://phantomjs.org/>")
        print("If phantomjs is intalled but not in your path you can set the full path to phantomjs in your config: %s" % home.rstrip("/"))
        sys.exit()

def tweet_diff(diff, token):
    if 'twitter' not in config:
        logging.debug("twitter not configured")
        return
    elif not token:
        logging.debug("access token/secret not set up for feed")
        return
    elif diff.tweeted:
        logging.warn("diff %s has already been tweeted", diff.id)
        return
    elif not (diff.old.archive_url and diff.new.archive_url):
        logging.warn("not tweeting without archive urls")
        return

    t = config['twitter']
    auth = tweepy.OAuthHandler(t['consumer_key'], t['consumer_secret'])
    auth.secure = True
    auth.set_access_token(token['access_token'], token['access_token_secret'])
    twitter = tweepy.API(auth)

    status = diff.new.title
    if len(status) >= 85:
        status = status[0:85] + "…"

    status += " " + diff.old.archive_url +  " -> " + diff.new.archive_url

    try:
        twitter.update_with_media(diff.thumbnail_path, status)
        diff.tweeted = datetime.utcnow()
        logging.info("tweeted %s", status)
        diff.save()
    except Exception as e:
        logging.error("unable to tweet: %s", e)


def init(new_home, prompt=True):
    global home
    home = new_home
    load_config(prompt)
    setup_phantomjs()
    setup_logging()
    setup_db()

def main():
    if len(sys.argv) == 1:
        home = os.getcwd()
    else:
        home = sys.argv[1]

    init(home)
    logging.info("starting up with home=%s", home)
    
    for f in config.get('feeds', []):

        feed, created = Feed.create_or_get(url=f['url'], name=f['name'])
        if created:
            logging.debug("created new feed for %s", f['url'])

        # get latest feed entries
        feed.get_latest()
        
        # get latest content for each entry
        for entry in feed.entries:
            version = entry.get_latest()
            if version and version.diff and 'twitter' in f:
                tweet_diff(version.diff, f['twitter'])

    logging.info("shutting down")

def _dt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")

def _remove_utm(url):
    u = urlparse(url)
    q = parse_qs(u.query, keep_blank_values=True)
    new_q = dict((k, v) for k, v in q.items() if not k.startswith('utm_'))
    return urlunparse([
        u.scheme,
        u.netloc,
        u.path,
        u.params,
        urlencode(new_q, doseq=True),
        u.fragment
    ])

if __name__ == "__main__":
    main()

