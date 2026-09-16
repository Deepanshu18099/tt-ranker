"""
Turning what someone typed into `/tt` into a match — text in, structure out.

Grammar, informally:

    /tt log  @bob  11-7 9-11 11-5                   singles, you vs Bob
    /tt log  @partner vs @dan @eve  11-7 11-9       doubles, you+partner named first
    /tt log  @a @b vs @c @d  11-7 11-9              anyone can record a match
    /tt log  @bob  11-7                             one game is a match too

`vs` splits the sides. Without it every mention is the opposition and you are
side A, which makes the common case — logging your own singles game — as short
as it can be. With it, if you never named yourself and your side is short one
player, you are added to it: `@partner vs @dan @eve` means what it reads like.

Everything raises ParseError with a message meant for the player, because nearly
every way this fails has its own fix and one generic usage dump helps nobody.
"""
import re

import elo

# Slack sends "<@U123>" or "<@U123|name>" for a mention; W-prefixed IDs are org users.
MENTION_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
# Three digits so an obvious typo ("11-100") is caught by the range check and
# explained, rather than silently not looking like a score at all.
SCORE_RE = re.compile(r"(\d{1,3})[-–—:](\d{1,3})")
VS_RE = re.compile(r"(?:vs?|versus|x)\.?", re.IGNORECASE)
# "11 - 7" and "11 : 7" mean "11-7". Both sides must be digits, which no Slack
# mention token contains around a separator, so mentions pass through untouched.
SPACED_SCORE_RE = re.compile(r"(\d)\s*[-–—:]\s*(\d)")

_TRIM = ".,;!?()[]"

SUBCOMMANDS = {
    "log": "log", "add": "log", "result": "log", "played": "log",
    "score": "log", "record": "log", "beat": "log", "lost": "log",
    "register": "register", "join": "register", "signup": "register",
    "me": "me", "card": "me", "stats": "me", "profile": "me", "rating": "me",
    "board": "board", "leaderboard": "board", "top": "board", "rank": "board",
    "standings": "board", "ladder": "board",
    "history": "history", "recent": "history", "log-history": "history",
    "undo": "undo", "oops": "undo",
    "pending": "pending", "unconfirmed": "pending",
    "odds": "odds", "predict": "odds", "chance": "odds",
    "sync": "sync", "backfill": "sync",
    "intro": "intro", "welcome": "intro", "rules": "intro", "howto": "intro",
    "name": "name", "callme": "name", "rename": "name",
    "nudge": "nudge", "askall": "nudge",
    # `form` and a bare `log` both open the guided modal.
    "form": "log", "new": "log",
    "help": "help", "h": "help", "usage": "help",
}


class ParseError(ValueError):
    """A problem worth showing the player verbatim."""


def mentions_in(text, exclude=None):
    """Mentioned user IDs, in order, deduped, minus the bot itself — @-ing the
    bot while logging a match is a mention of a player who wasn't on the table."""
    seen = [uid for uid in MENTION_RE.findall(text or "") if uid != exclude]
    return list(dict.fromkeys(seen))


def split_subcommand(text):
    """('log', 'rest of the text') — the leading verb and what follows.

    An unrecognised first word is not an error: `/tt @bob 11-7` is what people
    type once they know the bot, so anything carrying game scores is a log.
    """
    text = (text or "").strip()
    if not text:
        return "help", ""
    first, _, rest = text.partition(" ")
    key = first.strip(_TRIM).lower()
    if key in SUBCOMMANDS:
        return SUBCOMMANDS[key], rest.strip()
    return ("log" if SCORE_RE.search(_normalize(text)) else "help"), text


def _normalize(text):
    return SPACED_SCORE_RE.sub(r"\1-\2", text or "")


def _tokenize(text, exclude=None):
    """[(kind, value), …] where kind is 'mention' | 'vs' | 'score' | 'other'."""
    out = []
    for raw in _normalize(text).split():
        uids = [u for u in MENTION_RE.findall(raw) if u != exclude]
        if MENTION_RE.search(raw):
            out += [("mention", u) for u in uids]
            continue
        tok = raw.strip(_TRIM)
        m = SCORE_RE.fullmatch(tok)
        if m:
            out.append(("score", (int(m.group(1)), int(m.group(2)))))
        elif VS_RE.fullmatch(tok):
            out.append(("vs", None))
        elif tok:
            out.append(("other", tok))
    return out


def _sides(tokens, caller):
    """Mentions → (side_a, side_b), applying the `vs` rules. Not validated yet."""
    has_vs = any(kind == "vs" for kind, _ in tokens)
    side_a, side_b = [], []
    target = side_a if has_vs else side_b
    for kind, value in tokens:
        if kind == "vs":
            target = side_b
        elif kind == "mention":
            target.append(value)

    # Slack's autocomplete makes a double @mention easy; within one side that is
    # plainly a slip. The same name on *both* sides is a real mistake, so that
    # one is left for validate_sides to reject.
    side_a, side_b = list(dict.fromkeys(side_a)), list(dict.fromkeys(side_b))

    if not has_vs:
        # No separator: everyone named is the opposition and you are side A.
        side_a = [caller] if caller else []
    elif caller and caller not in side_a + side_b and len(side_a) < len(side_b):
        # "@partner vs @dan @eve" — you left yourself out of a side you're on.
        side_a.insert(0, caller)
    return side_a, side_b


def parse_match(text, caller=None, bot_id=None):
    """Text after `/tt log` → {"side_a": [uid…], "side_b": [uid…], "games": [(a,b)…]}.

    Raises ParseError, already phrased for the player, on anything unusable.
    """
    tokens = _tokenize(text, exclude=bot_id)
    side_a, side_b = _sides(tokens, caller)
    games = [v for kind, v in tokens if kind == "score"]
    validate_sides(side_a, side_b)
    validate_games(games)
    return {"side_a": side_a, "side_b": side_b, "games": games}


def validate_sides(side_a, side_b):
    if not side_a or not side_b:
        raise ParseError(
            "I need to know who played. Try `/tt log @opponent 11-7 9-11 11-5`, "
            "or `/tt log @partner vs @dan @eve 11-7 11-9` for doubles."
        )
    everyone = side_a + side_b
    if len(set(everyone)) != len(everyone):
        raise ParseError("Someone is on both sides (or listed twice) — check the @mentions.")
    if len(side_a) != len(side_b):
        raise ParseError(
            f"Uneven sides: {len(side_a)} v {len(side_b)}. Use `vs` to split them — "
            "`/tt log @partner vs @dan @eve 11-7 11-9`."
        )
    if len(side_a) > 2:
        raise ParseError("Singles and doubles only — that's more than two a side.")


def validate_games(games):
    if not games:
        raise ParseError(
            "No game scores found. Add them as points, one per game: "
            "`/tt log @opponent 11-7 9-11 11-5`."
        )
    if len(games) > elo.MAX_GAMES:
        raise ParseError(f"That's {len(games)} games — more than {elo.MAX_GAMES} looks like a typo.")
    for a, b in games:
        if a == b:
            raise ParseError(f"`{a}-{b}` can't be a finished game — someone has to win it.")
        if max(a, b) > elo.MAX_POINTS:
            raise ParseError(f"`{a}-{b}` is out of range — scores are the points in one game.")


def parse_games(text):
    """Just the game scores out of a blob of text.

    What the guided form's score field hands us — players come from its people
    pickers, so there are no mentions to separate out. Same validation as the
    typed path, so the two routes can never disagree about what a legal match is.
    """
    games = [v for kind, v in _tokenize(text) if kind == "score"]
    validate_games(games)
    return games


def parse_odds(text, caller=None, bot_id=None):
    """`/tt odds @bob` or `/tt odds @a @b vs @c @d` → (side_a, side_b), on the
    same side rules as a match but with no scores to give."""
    side_a, side_b = _sides(_tokenize(text, exclude=bot_id), caller)
    validate_sides(side_a, side_b)
    return side_a, side_b
