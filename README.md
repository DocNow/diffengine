[![Build Status](https://travis-ci.org/DocNow/diffengine.svg)](http://travis-ci.org/DocNow/diffengine)

## Why?

Most newspapers make sure that what they print is as accurate as possible,
because once the words are on paper, and the paper is in someone's hands,
there's no changing it. This involves attention to truthfulness, accuracy,
objectivity, impartiality, fairness and public accountability--in short it is
the work of professional journalism.

News stories on the web can be edited quickly as new facts arrive, and more is
learned. Typos can be quickly fixed. Many newspapers treat their website as a
place for their first drafts, which allows them to craft a story in near real
time, in order to be the first to publish a breaking story.

But news travels *fast* in social media. What if you don't subscribe to the
print newspaper anymore? What if the news organization doesn't have a print
edition and is available only on the web? And what if that initial, perhaps
flawed version goes viral, and it is the only version you ever read?  It's not
necessarily *fake news*, because there's no intent to mislead ...  but it may
not have been the best news either.

## diffengine

diffengine is a utility for watching RSS feeds to see when story
content changes. When new content is found a snapshot is saved at the Internet
Archive, and a diff is generated for sending to social media. The hope is that
it can help draw attention to the way news is being shaped on the web.

Thanks for the inspiration of [nyt_diff] and [NewsDiffs] which *almost* did what
was needed, but not quite. Through the magic of [feedparser] and [readability]
diffengine should work with any site that publishes a feed. And rather than
creating another website for people to watch diffengine pushes updates out to
social media where people are already.

## Install 

The hardest part here is that you need to install PhantomJS which is a headless
browser used to create image snapshots of the HTML diffs. Fortunately there are
packages you can download for major platforms, and helpful 
[install](https://gist.github.com/julionc/7476620) examples.

1. install [PhantomJS](http://phantomjs.org)
1. install [Python 3](https://python.org)
1. `pip3 install diffengine`

## Run

In order to run diffengine you need to pick a directory location where you can
store the diffengine configuration, database and diffs. For example I have a
directory in my home directory, but you can use whatever location you want, you
just need to be able to write to it.

The first time you run diffengine it will prompt you to enter an RSS or Atom
feed URL to monitor and will authenticate with Twitter. 

    % diffengine /home/ed/.diffengine 

    What RSS/Atom feed would you like to monitor? https://inkdroid.org/feed.xml

    Would you like to set up tweeting edits? [Y/n] Y

    Go to https://apps.twitter.com and create an application.

    What is the consumer key? <TWITTER_APP_KEY>

    What is the consumer secret? <TWITTER_APP_SECRET>

    Log in to https://twitter.com as the user you want to tweet as and hit enter.

    Visit https://api.twitter.com/oauth/authorize?oauth_token=NRW9BQAAAAAAyqBnAAXXYYlCL8g

    What is your PIN: 8675309

    Saved your configuration in example/config.yaml
    
    Fetching initial set of entries.

    Done!

After that you just need to put diffengine in your crontab to have it run
regularly, or you can run it manually at your own intervals if you want:

    0,15,30,45 * * * * diffengine /home/ed/.diffengine

You can examine your config file at any time and add/remove feeds as needed.  It
is the `config.yaml` file that is stored relative to the storage directory you
chose, so in my case `/home/ed/.diffengine/config.yaml`.

## Examples

* [wapo_diff]: announces edits to [Washington Post] articles.
* [breitbart_diff]: announces edits to [Breitbart News] articles.
* [guardian_diff]: announces edits to [The Guardian] articles.
* [torstar_diff]: announces edits to [Toronto Star] articles.

[nyt_diff]: https://twitter.com/nyt_diff
[NewsDiffs]: http://newsdiffs.org/
[feedparser]: https://pythonhosted.org/feedparser/
[readability]: https://github.com/buriy/python-readability
[wapo_diff]: https://twitter.com/wapo_diff
[breitbart_diff]: https://twitter.com/breitbart_diff
[torstar_diff]: https://twitter.com/guardian_diff
[Washington Post]: https://www.washingtonpost.com
[Breitart News]: https://www.breitbart.com
[The Guardian]: https://www.theguardian.com/
[Toronto Star]: https://www.thestar.com/
[torstar_diff]: https://twitter.com/torstar_diff
[The Globe and Mail]: http://www.theglobeandmail.com/
[globemail_diff]: https://twitter.com/globemail_diff
[Canadaland]: http://www.canadalandshow.com/
[canadaland_diff]: https://twitter.com/canadaland_diff
