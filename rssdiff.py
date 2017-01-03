#!/usr/bin/env python

import time
import yaml
import bleach
import logging
import requests
import feedparser
import readability

from peewee import *
from datetime import datetime

config = yaml.load(open('config.yaml'))
db = SqliteDatabase('rssdiff.db')


class Feed(Model):
    url = CharField(primary_key=True)
    name = CharField()
    created = DateTimeField(default=datetime.now)

    def get_latest(self):
        log = logging.getLogger(__name__)
        log.info("fetching feed: %s", self.url)
        feed = feedparser.parse(self.url)
        for e in feed.entries:
            entry, created = Entry.create_or_get(url=e.link, feed=self)
            if created:
                log.info("found new entry: %s", e.link)
            entry.get_latest() 

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
        # TODO: maybe there's a better way to be nice to servers?
        time.sleep(1)

        if not self.stale():
            return

        log = logging.getLogger(__name__)
        log.info("checking %s", self.url)
        resp = requests.get(self.url)
        doc = readability.Document(resp.text)
        title = doc.title()
        summary = doc.summary(html_partial=True)
        summary = bleach.clean(summary, tags=["div", "p"], strip=True)

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
            version = EntryVersion.create(
                title=title,
                summary=summary,
                entry=self
            )
            version.archive()

        self.checked = datetime.now()
        self.save()

    class Meta:
        database = db


class EntryVersion(Model):
    title = CharField()
    summary = CharField()
    created = DateTimeField(default=datetime.now)
    archive_url = CharField(null=True)
    entry = ForeignKeyField(Entry, related_name='versions')

    def archive(self):
        log = logging.getLogger(__name__)
        data = {'url': self.entry.url}
        resp = requests.post('https://pragma.archivelab.org', json=data)
        wayback_id = resp.json()['wayback_id']
        self.archive_url = "https://wayback.archive.org" + wayback_id
        log.info("archived version at %s", self.archive_url)
        self.save()

    class Meta:
        database = db


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler("rssdiff.log")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)
    return logger


def main():
    logger = setup_logging()
    db.connect()
    db.create_tables([Feed, Entry, EntryVersion], safe=True)
    for feed in config['feeds']:
        f, created = Feed.create_or_get(url=feed['url'], name=feed['name'])
        f.get_latest()


if __name__ == "__main__":
    main()

