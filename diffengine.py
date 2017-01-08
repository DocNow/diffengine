#!/usr/bin/env python

UA = "diffengine/0.1 (+https://github.com/edsu/diffengine)"

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
import readability

from peewee import *
from datetime import datetime, timedelta
from selenium import webdriver
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

config = {}
db = SqliteDatabase(None)
twitter = None

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
    canonical_url = None
    created = DateTimeField(default=datetime.utcnow)
    checked = DateTimeField(default=datetime.utcnow)

    @property
    def feeds(self):
        return (Feed.select()
                .join(FeedEntry)
                .join(Entry)
                .where(Entry.id==self.id))

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

    def get_latest(self, force=False):
        """
        Check to see if the entry has changed. If it has you'll get back
        the EntryVersion for it.
        """

        if not self.stale() and not force:
            return

        # make sure we don't go too fast
        time.sleep(1)

        # fetch the current readability-ized content for the page
        logging.info("checking %s", self.url)
        resp = requests.get(self.url, headers={"User-Agent": UA})
        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p"], strip=True)

        # in case there was a redirect, save the actual url for archiving
        self.canonical_url = _remove_utm(resp.url)
        self.save()

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
                summary=summary,
                entry=self
            )
            new.archive()
            if old:
                logging.info("found new version %s", old.entry.url)
                diff = Diff.create(old=old, new=new)
                diff.generate()
                diff.tweet()
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
    summary = CharField()
    created = DateTimeField(default=datetime.utcnow)
    archive_url = CharField(null=True)
    entry = ForeignKeyField(Entry, related_name='versions')

    @property
    def prev_diff(self):
        return self.prev_diffs.get()

    @property
    def next_diff(self):
        return self.next_diffs.get()

    @property
    def html(self):
        return "<h1>%s</h1>\n\n%s" % (self.title, self.summary)

    def archive(self):
        resp = requests.post('https://pragma.archivelab.org',
                             json={'url': self.entry.canonical_url},
                             headers={"User-Agent": UA})
        data = resp.json()
        if 'wayback_id' not in data:
            logging.error("unexpected archive.org response: %s ; headers=%s", 
                      json.dumps(data),
                      resp.headers)
            return
        wayback_id = data['wayback_id']
        self.archive_url = "https://wayback.archive.org" + wayback_id
        logging.info("archived version at %s", self.archive_url)
        self.save()


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

    def tweet(self):
        if not twitter:
            logging.debug("twitter not configured")
            return
        elif self.tweeted:
            logging.warn("diff %s has already been tweeted", self.id)
            return
        elif not (self.old.archive_url and self.new.archive_url):
            log.debug("not tweeting without archive urls")
            return

        status = self.new.title
        if len(status) >= 85:
            status = status[0:85] + "…"

        status += " " + self.old.archive_url +  " -> " + self.new.archive_url

        try:
            twitter.update_with_media(self.thumbnail_path, status)
            self.tweeted = datetime.utcnow()
            logging.info("tweeted %s", status)
            self.save()
        except Exception as e:
            logging.error("unable to tweet: %s", e)


    def _generate_diff_html(self):
        if os.path.isfile(self.html_path):
            return
        logging.info("creating html diff: %s", self.html_path)
        diff = htmldiff.render_html_diff(self.old.html, self.new.html)
        tmpl = jinja2.Template(codecs.open("diff.html", "r", "utf8").read())
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


def setup_twitter():
    global twitter
    if 'twitter' not in config:
        return
    t = config['twitter']
    auth = tweepy.OAuthHandler(t['consumer_key'], t['consumer_secret'])
    auth.secure = True
    auth.set_access_token(t['access_token'], t['access_token_secret'])
    twitter = tweepy.API(auth)

def setup_logging():
    path = config.get('log', home_path('diffengine.log'))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=path,
        filemode="a"
    )

def load_config(home):
    global config
    config_file = os.path.join(home, "config.yaml")
    if os.path.isfile(config_file):
        config = yaml.load(open(config_file))
    else:
        if not os.path.isdir(home):
            os.makedirs(home)
        config = {"feeds": []}
        yaml.dump(config, open(config_file, "w"))
    config['home'] = home

def home_path(rel_path):
    return os.path.join(config['home'], rel_path)

def setup_db():
    global db
    db_file = config.get('db', home_path('diffengine.db'))
    logging.debug("connecting to db %s", db_file)
    db.init(db_file)
    db.connect()
    db.create_tables([Feed, Entry, FeedEntry, EntryVersion, Diff], safe=True)

def init(home):
    load_config(home)
    setup_logging()
    setup_db()
    setup_twitter()

def main():
    if len(sys.argv) == 1:
        home = os.getcwd()
    else:
        home = sys.argv[1]

    init(home)
    logging.info("starting up with home=%s", home)
    
    for f in config['feeds']:
        feed, created = Feed.create_or_get(url=f['url'], name=f['name'])
        if created:
            logging.debug("created new feed for %s", f['url'])

        # get latest feed entries
        feed.get_latest()
        
        # get latest content for each entry
        for entry in feed.entries:
            entry.get_latest()

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

