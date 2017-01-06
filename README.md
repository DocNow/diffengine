Most newspapers make sure that what they print is as accurate as possible,
because once the words are on paper, and the paper is in someone's hands,
there's no changing it.

The same is not true on the web, where stories can be quickly edited as new
facts arrive, and more is learned. Many newspapers treat their website as a
place for their first drafts, which allows them to craft a story in near real
time, while giving them the opportunity to be the first to publish a breaking
story.

But news travels *fast* in social media. What if you don't subscribe to the
print newspaper anymore? What if the news organization doesn't have a print
edition? And what if that initial, perhaps flawed version goes viral, and it is
the only version you ever read?  It's not exactly *fake news*, because there's
no intent to mislead ...  but it may not have been the best news either.

---

diffengine is a utility for watching RSS feeds to see when story
content changes. When new content is found a snapshot is saved at the Internet
Archive, and a diff is generated for sending to social media. The hope is that
it can help draw attention to the way news is being shaped on the web.

Thanks for the inspiration of [nyt_diff] and [NewsDiffs] which *almost* did what
was needed, but not quite. Through the magic of [feedparser] and [readability]
diffengine should work with any site that publishes a feed. And rather than
creating another website for people to watch diffengine pushes updates out to
social media where people are already.

[nyt_diff]: https://twitter.com/nyt_diff
[NewsDiffs]: http://newsdiffs.org/
[feedparser]: https://pythonhosted.org/feedparser/
[readability]: https://github.com/buriy/python-readability
