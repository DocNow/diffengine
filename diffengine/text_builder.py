import logging


def build_text(diff, lang={}):
    # Try build the text from i18n
    if can_build_with_lang(lang):
        logging.debug("building text with lang")
        return "%s\n%s" % (
            build_with_lang(
                lang, diff.url_changed, diff.title_changed, diff.summary_changed
            ),
            diff.url,
        )
    elif lang:
        logging.warning(
            "cannot build text from lang. Check you have ALL the keys: 'change_in', 'the_url', 'the_title' and 'the_summary'"
        )

    logging.debug("building text with default content")
    return build_with_default_content(diff)


def can_build_with_lang(lang):
    return all(
        k in lang for k in ("change_in", "the_url", "the_title", "and", "the_summary")
    )


def build_with_lang(
    lang, url_changed=False, title_changed=False, summary_changed=False
):
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


def build_with_default_content(diff):
    text = diff.new.title
    if len(text) >= 225:
        text = text[0:225] + "…"
    text += " " + diff.url
    return text
