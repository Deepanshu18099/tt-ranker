"""How to log a match.

The ladder is written to from Slack and only from Slack: a result needs a
person, and the web page has no idea who is reading it. So this page does not
pretend to be a form — it is the shortest path to the two things that do work,
and it says plainly what happens next, because the part people get wrong is
expecting the rating to move before their opponent has confirmed.
"""
from .. import components as c
from .. import icons, layout

STEPS = (
    ("Play", "Any number of games. A longer session counts for more, so play "
             "them all and log them together."),
    ("Log it", "In Slack, <code>/tt log</code> opens a form — pick the players, "
               "type the scores. No syntax to remember."),
    ("They confirm", "Your opponent gets the result and presses Confirm. "
                     "Nothing moves until they do, and nobody can rate their "
                     "own match."),
    ("Ratings move", "Both sides change, the result appears here, and the "
                     "board re-sorts itself."),
)

EXAMPLES = (
    ("/tt log", "Opens the form. The easy one."),
    ("/tt log @bob 11-7 9-11 11-5", "Singles, three games, typed straight out."),
    ("/tt log @partner vs @dan @eve 11-7 11-9", "Doubles. <code>vs</code> splits the sides."),
    ("/tt undo", "Rolls back the last session you logged."),
)


def render(channel_hint="", log_href="", updated=""):
    where = f"in #{c.e(channel_hint)}" if channel_hint else "in Slack"
    steps = "".join(
        f'<li class="step"><span class="step-n num">{i:02d}</span>'
        f'<span class="step-body"><span class="step-title">{c.e(title)}</span>'
        f'<span class="step-text">{text}</span></span></li>'
        for i, (title, text) in enumerate(STEPS, 1))
    examples = "".join(
        f'<li><code>{c.e(command)}</code><span>{note}</span></li>'
        for command, note in EXAMPLES)

    cta = (f'<a class="btn btn-primary" href="{c.e(log_href)}">{icons.plus()}'
           "Open Slack</a>" if log_href else "")
    body = [c.page_header(
        "Log a Match", eyebrow="Four steps",
        lead=f"Results are recorded {where}, where there's a name attached to "
             "whoever typed them. This page is read-only by design.",
        extra=f'<div class="head-cta">{cta}</div>' if cta else "")]
    body.append(c.section("How it works", f'<ol class="steps">{steps}</ol>',
                          classes="rise-1"))
    body.append(c.section("The commands", f'<ul class="commands">{examples}</ul>',
                          note="Every command starts with <code>/tt</code>. "
                               "<code>/tt help</code> lists the rest.",
                          classes="rise-2"))
    body.append(c.section(
        "Why the web can't do it",
        '<p class="note">A rating is a claim about two people, so the ladder '
        'needs to know who is making it. Slack knows; a public page does not. '
        'Everything here is readable by anyone in the channel and writable by '
        'nobody — which is also why there is no login to lose.</p>',
        classes="rise-3"))
    # No nav item is lit: this page is none of them, and lighting the ladder
    # would say the reader is somewhere they aren't.
    return layout.document("Log a Match — RALLY", "".join(body), current="",
                           log_href=log_href, channel_hint=channel_hint,
                           updated=updated)
