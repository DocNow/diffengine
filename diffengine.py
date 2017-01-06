#!/usr/bin/env python

import os
import json
import time
import yaml
import bleach
import codecs
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
if config['twitter']:
    t = config['twitter']
    auth = tweepy.OAuthHandler(t['consumer_key'], t['consumer_secret'])
    auth.secure = True
    auth.set_access_token(t['access_token'], t['access_token_secret'])
    twitter = tweepy.API(auth)
            

class Feed(Model):
    url = CharField(primary_key=True)
    name = CharField()
    created = DateTimeField(default=datetime.now)

    def get_latest(self):
        log = logging.getLogger(__name__)
        log.debug("fetching feed: %s", self.url)
        feed = feedparser.parse(self.url)
        for e in feed.entries:
            entry, created = Entry.create_or_get(url=e.link, feed=self)
            if created:
                log.debug("found new entry: %s", e.link)

    class Meta:
        database = db


class Entry(Model):
    url = CharField(primary_key=True)
    created = DateTimeField(default=datetime.now)
    checked = DateTimeField(default=datetime.now)
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
        hotness = (datetime.now() - self.created).seconds

        # time since the entry was last checked
        staleness = (datetime.now() - self.checked).seconds

        # ratio of staleness to hotness
        r = staleness / float(hotness)

        # TODO: allow this magic number to be configured per feed?
        if r >= 0.125:
            log.debug("%s is stale (%f)", self.url, r)
            return True

        # Why 0.125 you ask? Well it's just a guess. If an entry was first 
        # noticed 2 hours ago (7200 secs) and the last time it was 
        # checked was 15 minutes ago (900 secs) then it is deemed stale
        #
        # Similarly, if the entry was first noticed 2 weeks ago (1209600 secs)
        # and it was last checked 1 and 3/4 days ago (151200 secs) then it 
        # will be deemed stale.

        log.debug("%s not stale (%f)", self.url, r)
        return False

    def get_latest(self):
        log = logging.getLogger(__name__)

        if not self.stale():
            log.debug("skipping %s, not stale", self.url) 
            return

        # make sure we don't go too fast
        time.sleep(1)

        # fetch the current readability-ized content for the page
        log.debug("checking %s", self.url)
        resp = requests.get(self.url)
        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p"], strip=True)

        # get the latest version, if we have one
        versions = EntryVersion.select().where(EntryVersion.entry==self)
        versions = versions.order_by(-EntryVersion.created)
        if len(versions) == 0:
            lastv = None
        else:
            lastv = versions[0]

        # compare what we got against the latest version and create a 
        # new version if it looks different, or is brand new (no last version)
        if not lastv or lastv.title != title or lastv.summary != summary:
            version = EntryVersion.create(
                title=title,
                summary=summary,
                entry=self
            )
            version.archive()
            if lastv:
                log.info("found a new version: %s", self.url)
            else:
                log.debug("found first version: %s", self.url)

        self.checked = datetime.now()
        self.save()

    def generate_diffs(self):
        log = logging.getLogger(__name__)
        if len(self.versions) < 2:
            return
        versions = EntryVersion.select().where(EntryVersion.entry==self)
        versions = versions.order_by(EntryVersion.created)

        i = 0
        while i < len(versions) - 1:
            self._generate_diff(versions[i], versions[i+1])
            i += 1

    def _generate_diff(self, v1, v2):
        self._generate_diff_html(v1, v2)
        self._generate_diff_image()

    def _generate_diff_html(self, v1, v2):
        log = logging.getLogger(__name__)
        path = "diffs/%s-%s.html" % (v1.id, v2.id)
        if os.path.isfile(path):
            return path
        log.debug("creating html diff: %s", path)
        diff = htmldiff.render_html_diff(v1.html, v2.html)
        # TODO: move this to geshi since we have that installed for htmldiff?
        html = """
            <html>
              <head>
                <meta charset="UTF-8">
                <title></title>
                <link rel="stylesheet" href="style.css">
                <script src="jquery.min.js"></script>
                <script src="clip.js"></script>
                <script>
                  $(function() {
                    clip();
                  });
                </script>
              </head>
            <body>
              <header>
                <div class="url"><a href="%s">%s</a></div>
                <div class="archive">
                  <img src="ia.png"> 
                  <a href="%s">%s</a> ≠ <a href="%s">%s</a>
                </div>
              </header>
              <div class="diff">%s</div>
            </body>
            </html>""" % (
                v1.entry.url, v1.entry.url,
                v1.archive_url, _dt(v1.created),
                v2.archive_url, _dt(v2.created),
                diff
            )
        codecs.open(path, "w", 'utf8').write(html)
        return path

    def _generate_diff_image(self):
        log = logging.getLogger(__name__)
        img_path = self.screenshot_path
        if os.path.isfile(img_path):
            return img_path
        log.debug("creating image screenshot %s", img_path)
        if not hasattr(self, 'browser'):
            phantomjs = config.get('phantomjs', '/usr/local/bin/phantomjs')
            self.browser = webdriver.PhantomJS(phantomjs)
            self.browser.set_window_size(1400, 1000)
        self.browser.get(self.html_path)
        self.browser.save_screenshot(img_path)
        return img_path

    class Meta:
        database = db


class EntryVersion(Model):
    title = CharField()
    summary = CharField()
    created = DateTimeField(default=datetime.now)
    archive_url = CharField(null=True)
    entry = ForeignKeyField(Entry, related_name='versions')

    @property
    def html(self):
        return "<h1>%s</h1>\n\n%s" % (self.title, self.summary)

    @property
    def html_path(self):
        return "diffs/%s-%s.html" % (v1.id, v2.id)

    @property
    def screenshot_path(self):
        return self.html_path.replace(".html", ".jpg")

    def archive(self):
        log = logging.getLogger(__name__)
        data = {'url': self.entry.url}
        resp = requests.post('https://pragma.archivelab.org', json=data)
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


class Diff(model):
    old = ForeignKeyField(EntryVersion)
    new = ForeignKeyField(EntryVersion)
    created = DateTimeField(default=datetime.now)
    tweeted = DateTimeField(null=True)
    blogged = DateTimeField(null=True)


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
    db.create_tables([Feed, Entry, EntryVersion], safe=True)

    for f in config['feeds']:
        feed, created = Feed.create_or_get(url=f['url'], name=f['name'])
        if created:
            log.debug("created new feed for %s", f['url'])

        # get latest feed entries
        feed.get_latest()
        
        # get latest content for each entry
        for entry in feed.entries:
            entry.get_latest()
            if len(entry.versions) > 1:
                entry.generate_diffs()

    log.debug("shutting down")

def _dt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")
        

if __name__ == "__main__":
    main()

