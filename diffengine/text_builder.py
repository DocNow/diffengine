import logging


def build_text(diff, lang):
    logging.debug("building text for diff %s" % diff.new.title)
    # Try build the text from i18n
    if can_build_with_lang(lang):
        logging.debug("with lang")
        return "%s\n%s" % (
            build_from_lang(
                lang, diff.url_changed, diff.title_changed, diff.summary_changed
            ),
            diff.url,
        )

    logging.debug("with default text")
    return build_default(diff)


def can_build_with_lang(lang):
    return all(k in lang for k in ("change_in", "the_url", "the_title", "the_summary"))


def build_from_lang(lang, url_changed, title_changed, summary_changed):
    changes = []
    if url_changed:
        changes.append(lang["the_url"])
    if title_changed:
        changes.append(lang["the_title"])
    if summary_changed:
        changes.append(lang["the_summary"])

    if len(changes) > 1:
        and_change = " %s " % lang["and"]
        last_change = changes.pop(len(changes) - 1)
    else:
        and_change = ""
        last_change = ""

    return "%s %s%s%s" % (
        lang["change_in"],
        ", ".join(changes),
        and_change,
        last_change,
    )


def build_default(diff):
    text = diff.new.title
    if len(text) >= 225:
        text = text[0:225] + "…"
    text += " " + diff.url
    return text
