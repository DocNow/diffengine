#!/usr/bin/env python

import os
import time
import yaml
import bleach
import codecs
import logging
import requests
import selenium
import feedparser
import simplediff
import readability

from peewee import *
from datetime import datetime
from selenium import webdriver

config = yaml.load(open('config.yaml'))
db = SqliteDatabase('diffengine.db')


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
        # TODO: do something fancy with created and checked
        return True

    def get_latest(self):
        log = logging.getLogger(__name__)

        # TODO: maybe there's a better way to be nice to servers?
        time.sleep(1)

        if not self.stale():
            return

        # fetch the current readability-ized content for the page
        log.debug("checking %s", self.url)
        resp = requests.get(self.url)
        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["p", "div"], strip=True)

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
            if lastv:
                log.info("found a new version: %s", self.url)
            else:
                log.debug("found first version: %s", self.url)
            version = EntryVersion.create(
                title=title,
                summary=summary,
                entry=self
            )
            version.archive()

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
            log.debug("comparing versions %s and %s", i, i+1)
            self._generate_diff(versions[i], versions[i+1])
            i += 1

    def _generate_diff(self, v1, v2):
        html_path = self._generate_diff_html(v1, v2)
        self._generate_diff_image(html_path)

    def _generate_diff_html(self, v1, v2):
        log = logging.getLogger(__name__)
        path = "diffs/%s-%s.html" % (v1.id, v2.id)
        if os.path.isfile(path):
            return path
        log.debug("creating html diff: %s", path)
        diff = simplediff.html_diff(v1.html, v2.html)
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

    def _generate_diff_image(self, html_path):
        log = logging.getLogger(__name__)
        img_path = html_path.replace(".html", ".jpg")
        if os.path.isfile(img_path):
            return img_path
        log.debug("creating image screenshot %s", img_path)
        phantomjs = config.get('phantomjs', '/usr/local/bin/phantomjs')
        driver = webdriver.PhantomJS(phantomjs)
        driver.get(html_path)
        driver.save_screenshot(img_path)
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

    def archive(self):
        log = logging.getLogger(__name__)
        data = {'url': self.entry.url}
        resp = requests.post('https://pragma.archivelab.org', json=data)
        wayback_id = resp.json()['wayback_id']
        self.archive_url = "https://wayback.archive.org" + wayback_id
        log.debug("archived version at %s", self.archive_url)
        self.save()

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

def _dt(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")
        

if __name__ == "__main__":
    main()

