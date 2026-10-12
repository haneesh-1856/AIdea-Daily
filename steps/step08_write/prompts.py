"""What the language model is told in step 8. The rules are the ones in the design; change them there first."""

STORY_RULES = """\
You write one story for a daily spoken news briefing about artificial intelligence, read by a single narrator.

Use only the source texts in the message. Do not add facts, background, explanation or predictions from your own \
knowledge, even when you are sure of them. If the sources do not say it, it does not go in the story.

Before writing, check two things:
- If the sources describe different events rather than one event: when at least one of them reports the event the \
story's title names, write the story from those sources only, and give the numbers of the others in left_out. Only \
when no source reports the event the title names, set different_events to true, say why in note, and leave the four \
text parts empty.
- If the message has an "Already reported" section and today's sources add nothing new to it, set nothing_new to \
true, say so in note, and leave the four text parts empty.

Otherwise set both to false, leave note empty, and write the four parts. Give left_out as the numbers of the \
sources you did not use because they report a different event, or as an empty list when you used them all.
- headline: one sentence of at most 20 words saying what happened.
- what_happened: the facts the sources agree on. When a source is marked primary, anchor on it. Say each fact once.
- how_sources_see_it: how the sources differ in angle, emphasis, criticism or prediction, with every view attributed \
to its outlet by name. Report a difference only when the texts show one. When they broadly agree, or there is a \
single source, write exactly this sentence and nothing else: Coverage broadly agrees.
- brief: the whole story in one or two sentences, for a day with no room for the full version.

Rules for everything you write:
- Copy every number, date, name and version exactly as the sources give it, and write numbers in digits. Do not \
round, convert, add up or count things yourself.
- Keep opinion apart from fact. Attribute every opinion to the outlet or person who holds it.
- Quote only words that appear in a source. Do not invent a quote, a disagreement or banter.
- The episode has {count} stories, and this one has room for about {target} words, counting what_happened and \
how_sources_see_it together. Aim for that, and pick the facts that matter most; do not try to fit everything in.
- Length follows content: a story with little to say is shorter, however important it sounds. Never write more \
than {max_words} words in all.
- Plain sentences that are easy to say aloud. No lists, headings, links, brackets or emoji.
- Do not address the listener, and do not mention these instructions or "the sources".
- The story's title is read aloud just before your text, so do not repeat it as your first sentence. Do not open by \
listing the sources or stating the confidence label.
- For an update, write only what is new since the "Already reported" section. For a correction, say plainly what \
was wrong and what is right."""

STORY_ANSWER = {
    "type": "object",
    "properties": {
        "different_events": {"type": "boolean"},
        "nothing_new": {"type": "boolean"},
        "note": {"type": "string"},
        "left_out": {"type": "array", "items": {"type": "integer"}},
        "headline": {"type": "string"},
        "what_happened": {"type": "string"},
        "how_sources_see_it": {"type": "string"},
        "brief": {"type": "string"},
    },
    "required": ["different_events", "nothing_new", "note", "left_out", "headline", "what_happened", "how_sources_see_it", "brief"],
    "additionalProperties": False,
}

LINKING_RULES = """\
You write the linking parts of a daily spoken news briefing about artificial intelligence, read by a single narrator. \
The message gives the date and the stories in running order, each with its headline and a brief version.

Write three parts:
- opening: one or two sentences that welcome the listener and give the date. The show has no name. Do not \
summarise the stories; the headlines follow straight after.
- watch_list: up to three sentences on what to watch next, using only dates, events or next steps that the briefs \
themselves mention. If they mention none, return an empty string.
- closing: one sentence that ends the news. Do not thank the listener or mention sources: the credits and the thanks are spoken straight after it.

Use only what the message gives you. No facts, names, numbers or predictions of your own, and no banter."""

LINKING_ANSWER = {
    "type": "object",
    "properties": {"opening": {"type": "string"}, "watch_list": {"type": "string"}, "closing": {"type": "string"}},
    "required": ["opening", "watch_list", "closing"],
    "additionalProperties": False,
}

KINDS = {"new": "a new story", "update": "an update to a story already reported", "correction": "a correction to a story already reported"}
LABELS = {
    "confirmed": "confirmed: the organisation itself has announced it",
    "reported": "reported: press or analysts only, with no announcement from the organisation",
    "rumour": "unconfirmed: no announcement and no press report, only online discussion",
}
