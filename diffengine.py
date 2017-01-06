#!/usr/bin/env python

UA = "diffengine/0.1 (+https://github.com/edsu/diffengine)"

import os
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

config = yaml.load(open('config.yaml'))
db = SqliteDatabase('diffengine.db')

twitter = None
if 'twitter' in config:
    t = config['twitter']
    auth = tweepy.OAuthHandler(t['consumer_key'], t['consumer_secret'])
    auth.secure = True
    auth.set_access_token(t['access_token'], t['access_token_secret'])
    twitter = tweepy.API(auth)
            

class Feed(Model):
    url = CharField(primary_key=True)
    name = CharField()
    created = DateTimeField(default=datetime.utcnow)

    def get_latest(self):
        log = logging.getLogger(__name__)
        log.debug("fetching feed: %s", self.url)
        feed = feedparser.parse(self.url)
        for e in feed.entries:
            entry, created = Entry.get_or_create(url=e.link, feed=self)
            if created:
                log.debug("found new entry: %s", e.link)

    class Meta:
        database = db


class Entry(Model):
    url = CharField()
    created = DateTimeField(default=datetime.utcnow)
    checked = DateTimeField(default=datetime.utcnow)
    feed = ForeignKeyField(Feed, related_name='entries')

    def stale(self):
        """
        A heuristic for checking new content very often, and checking 
        older content less frequently. If an entry is deemed stale then
        it is worth checking again to see if the content has changed.
        """
        log = logging.getLogger(__name__)

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
            log.debug("%s is stale (r=%f)", self.url, r)
            return True

        log.debug("%s not stale (r=%f)", self.url, r)
        return False

    def get_latest(self):
        log = logging.getLogger(__name__)

        if not self.stale():
            return

        # make sure we don't go too fast
        time.sleep(1)

        # fetch the current readability-ized content for the page
        log.debug("checking %s", self.url)
        resp = requests.get(self.url, headers={"User-Agent": UA})
        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p"], strip=True)


        # get the latest version, if we have one
        versions = EntryVersion.select().where(EntryVersion.entry==self)
        versions = versions.order_by(-EntryVersion.created)
        if len(versions) == 0:
            old = None
        else:
            old = versions[0]

        # compare what we got against the latest version and create a 
        # new version if it looks different, or is brand new (no old version)
        diff = None

        if not old or old.title != title or old.summary != summary:
            new = EntryVersion.create(
                title=title,
                summary=summary,
                entry=self
            )
            new.archive()
            if old:
                log.info("found new version %s", old.entry.url)
                diff = Diff.create(old=old, new=new)
                diff.generate()
            else:
                log.debug("found first version: %s", self.url)

        self.checked = datetime.utcnow()
        self.save()
        return diff

    class Meta:
        database = db


class EntryVersion(Model):
    title = CharField()
    summary = CharField()
    created = DateTimeField(default=datetime.utcnow)
    archive_url = CharField(null=True)
    entry = ForeignKeyField(Entry, related_name='versions')

    @property
    def html(self):
        return "<h1>%s</h1>\n\n%s" % (self.title, self.summary)

    def archive(self):
        log = logging.getLogger(__name__)
        resp = requests.post('https://pragma.archivelab.org',
                             json={'url': self.entry.url},
                             headers={"User-Agent": UA})
        data = resp.json()
        if 'wayback_id' not in data:
            log.error("unexpected archive.org response: %s", json.dumps(data))
            return
        wayback_id = data['wayback_id']
        self.archive_url = "https://wayback.archive.org" + wayback_id
        log.debug("archived version at %s", self.archive_url)
        self.save()

    class Meta:
        database = db


class Diff(Model):
    old = ForeignKeyField(EntryVersion, related_name="prev_diff")
    new = ForeignKeyField(EntryVersion, related_name="next_diff")
    created = DateTimeField(default=datetime.utcnow)
    tweeted = DateTimeField(null=True)
    blogged = DateTimeField(null=True)

    @property
    def html_path(self):
        dir_name = "diffs/%s" % (self.old.entry.id % 53)
        if not os.path.isdir(dir_name):
            os.makedirs(dir_name)
        return "%s/%s-%s.html" % (dir_name, self.old.id, self.new.id)

    @property
    def screenshot_path(self):
        return self.html_path.replace(".html", ".jpg")

    def generate(self):
        self._generate_diff_html()
        self._generate_diff_image()

    def _generate_diff_html(self):
        log = logging.getLogger(__name__)
        if os.path.isfile(self.html_path):
            return
        log.debug("creating html diff: %s", self.html_path)
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

    def _generate_diff_image(self):
        log = logging.getLogger(__name__)
        if os.path.isfile(self.screenshot_path):
            return
        log.debug("creating image screenshot %s", self.screenshot_path)
        if not hasattr(self, 'browser'):
            phantomjs = config.get('phantomjs', '/usr/local/bin/phantomjs')
            self.browser = webdriver.PhantomJS(phantomjs)
            self.browser.set_window_size(1400, 1000)
        self.browser.get(self.html_path)
        self.browser.save_screenshot(self.screenshot_path)

    class Meta:
        database = db



def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler("diffengine.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)
    return logger


def main():
    log = setup_logging()
    log.debug("starting up")
    db.connect()
    db.create_tables([Feed, Entry, EntryVersion, Diff], safe=True)

    for f in config['feeds']:
        feed, created = Feed.create_or_get(url=f['url'], name=f['name'])
        if created:
            log.debug("created new feed for %s", f['url'])

        # get latest feed entries
        feed.get_latest()
        
        # get latest content for each entry
        for entry in feed.entries:
            diff = entry.get_latest()

    log.debug("shutting down")

def _dt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")
        

if __name__ == "__main__":
    main()

