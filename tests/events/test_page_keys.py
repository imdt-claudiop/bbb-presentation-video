# SPDX-FileCopyrightText: 2026 BigBlueButton Inc. and by respective authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List

from bbb_presentation_video.events import (
    Event,
    parse_events,
    resolve_page_keys,
)
from bbb_presentation_video.events.page_keys import PageKeyResolver

PRESENTATION = "pres-1"
PAGE_1 = "e0c1a3aa-0000-0000-0000-000000000001"
PAGE_2 = "e0c1a3aa-0000-0000-0000-000000000002"
INSERTED = "e0c1a3aa-0000-0000-0000-00000000000f"


def test_resolve_prefers_the_id_on_the_event() -> None:
    resolver = PageKeyResolver({PRESENTATION: [PAGE_1]})
    assert resolver.resolve(PRESENTATION, 0, INSERTED) == INSERTED


def test_resolve_falls_back_to_the_upload_order_page_ids() -> None:
    resolver = PageKeyResolver({PRESENTATION: [PAGE_1, PAGE_2]})
    # Event page numbers are 0-based, like the positions in the list.
    assert resolver.resolve(PRESENTATION, 0) == PAGE_1
    assert resolver.resolve(PRESENTATION, 1) == PAGE_2


def test_page_ids_win_over_a_learned_id() -> None:
    resolver = PageKeyResolver({PRESENTATION: [PAGE_1]})
    resolver.learn(PRESENTATION, 0, PAGE_2)
    assert resolver.resolve(PRESENTATION, 0) == PAGE_1


def test_page_number_past_the_page_ids_falls_back() -> None:
    resolver = PageKeyResolver({PRESENTATION: [PAGE_1]})
    resolver.learn(PRESENTATION, 3, INSERTED)
    assert resolver.resolve(PRESENTATION, 3) == INSERTED
    assert resolver.resolve(PRESENTATION, 5) == f"{PRESENTATION}/6"


def test_page_ids_of_another_presentation_are_not_used() -> None:
    resolver = PageKeyResolver({"pres-other": [PAGE_1]})
    assert resolver.resolve(PRESENTATION, 0) == f"{PRESENTATION}/1"


def test_resolve_falls_back_to_a_learned_id() -> None:
    resolver = PageKeyResolver()
    resolver.learn(PRESENTATION, 0, PAGE_1)
    assert resolver.resolve(PRESENTATION, 0) == PAGE_1


def test_learn_keeps_the_first_id_and_ignores_empty() -> None:
    resolver = PageKeyResolver()
    resolver.learn(PRESENTATION, 0, None)
    resolver.learn(PRESENTATION, 0, "")
    resolver.learn(PRESENTATION, 0, PAGE_1)
    resolver.learn(PRESENTATION, 0, PAGE_2)
    assert resolver.resolve(PRESENTATION, 0) == PAGE_1


def test_resolve_falls_back_to_a_composite_key() -> None:
    resolver = PageKeyResolver()
    # 1-based, matching the whiteboardId of recordings that had no page ids.
    assert resolver.resolve(PRESENTATION, 0) == f"{PRESENTATION}/1"
    assert resolver.resolve(PRESENTATION, 4) == f"{PRESENTATION}/5"


def test_resolve_without_a_presentation() -> None:
    resolver = PageKeyResolver()
    assert resolver.resolve(None, 0) == "/1"


def event(name: str, **fields: Any) -> Event:
    parsed: Dict[str, Any] = {"name": name, "timestamp": Fraction(0)}
    parsed.update(fields)
    return parsed  # type: ignore[return-value]


def keys_of(events: List[Event]) -> List[Any]:
    return [e.get("page_key") for e in events]  # type: ignore[attr-defined]


def test_inserted_page_does_not_share_a_key_with_the_page_it_displaced() -> None:
    """A page number is reused after an insert; the pages behind it are not.

    Page 2 of the presentation is annotated, a page is then inserted in front of
    it and annotated in turn. Both sets of annotations arrive under page number
    1, and must not end up on the same page.
    """
    events: List[Event] = [
        event("presentation", presentation=PRESENTATION),
        event("slide", slide=1, page_id=PAGE_2),
        event("tldraw.add_shape", presentation=PRESENTATION, slide=1, page_id=PAGE_2),
        # The insert renumbers: page number 1 is now the inserted page.
        event("slide", slide=1, page_id=INSERTED),
        event("tldraw.add_shape", presentation=PRESENTATION, slide=1, page_id=INSERTED),
        # Back to the original page, which has moved to number 2.
        event("slide", slide=2, page_id=PAGE_2),
    ]

    # Upload order: the inserted page is not in the list.
    resolve_page_keys(events, {PRESENTATION: [PAGE_1, PAGE_2]})

    assert keys_of(events) == [PAGE_1, PAGE_2, PAGE_2, INSERTED, INSERTED, PAGE_2]


def test_page_shown_at_the_start_is_named_by_its_annotations() -> None:
    """The first page has no slide event of its own, but its shapes name it."""
    events: List[Event] = [
        event("presentation", presentation=PRESENTATION),
        event("tldraw.add_shape", presentation=PRESENTATION, slide=0, page_id=PAGE_1),
    ]

    resolve_page_keys(events)

    # No page ids here, so the presentation event has to borrow the id that the
    # shape event carries, or the two would be on different pages.
    assert keys_of(events) == [PAGE_1, PAGE_1]


def test_returning_to_a_presentation_restores_its_page() -> None:
    """Sharing a presentation again returns to its last viewed page.

    The renderers restore that page, so an event that names no page of its own
    right after the switch must resolve against it, not against the page the
    previous presentation was left on.
    """
    events: List[Event] = [
        event("presentation", presentation="pres-a"),
        event("slide", slide=2, page_id=None),
        event("presentation", presentation="pres-b"),
        event("cursor_v2", page_id=None),
        event("presentation", presentation="pres-a"),
        event("cursor_v2", page_id=None),
    ]

    resolve_page_keys(events)

    assert keys_of(events) == [
        "pres-a/1",
        "pres-a/3",
        # pres-b has never been shown, so it opens on its first page.
        "pres-b/1",
        "pres-b/1",
        # pres-a returns on the page it was left on.
        "pres-a/3",
        "pres-a/3",
    ]


def test_recording_without_page_ids_keys_by_number() -> None:
    """Older recordings carry no ids anywhere and keep per-number behaviour."""
    events: List[Event] = [
        event("presentation", presentation=PRESENTATION),
        event("slide", slide=1, page_id=None),
        event("shape", presentation=PRESENTATION, slide=1, page_id=None),
        event("shape", presentation=PRESENTATION, slide=None, page_id=None),
        event("slide", slide=2, page_id=None),
        event("shape", presentation=PRESENTATION, slide=2, page_id=None),
    ]

    resolve_page_keys(events)

    assert keys_of(events) == [
        f"{PRESENTATION}/1",
        f"{PRESENTATION}/2",
        f"{PRESENTATION}/2",
        # No page number of its own: the page being shown at the time.
        f"{PRESENTATION}/2",
        f"{PRESENTATION}/3",
        f"{PRESENTATION}/3",
    ]


def test_page_shown_at_the_start_is_named_by_the_page_ids() -> None:
    """A presentation shown for the first time opens on its first page id."""
    events: List[Event] = [
        event("presentation", presentation=PRESENTATION),
        event("cursor_v2", page_id=None),
    ]

    resolve_page_keys(events, {PRESENTATION: [PAGE_1, PAGE_2]})

    assert keys_of(events) == [PAGE_1, PAGE_1]


EVENTS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<recording meeting_id="m-1" bbb_version="4.1.0">
  <metadata isBreakout="false" meetingId="m-1"/>
  {conversions}
  <event timestamp="2000" module="PRESENTATION" eventname="SharePresentationEvent">
    <presentationName>{presentation}</presentationName>
    <podId>DEFAULT_PRESENTATION_POD</podId>
  </event>
  <event timestamp="3000" module="WHITEBOARD" eventname="WhiteboardCursorMoveEvent">
    <presentation>{presentation}</presentation>
    <pageNumber>0</pageNumber>
    <xOffset>10</xOffset>
    <yOffset>10</yOffset>
    <userId>w_1</userId>
  </event>
</recording>
"""


def conversion(timestamp: int, page_ids: str = "") -> str:
    ids = f"<pageIds>{page_ids}</pageIds>" if page_ids else ""
    return f"""<event timestamp="{timestamp}" module="PRESENTATION" eventname="ConversionCompletedEvent">
    <presentationName>{PRESENTATION}</presentationName>
    <originalFilename>deck.pdf</originalFilename>
    <podId>DEFAULT_PRESENTATION_POD</podId>
    {ids}
  </event>"""


def page_keys_of(directory: Path, conversions: str) -> List[Any]:
    (directory / "events.xml").write_text(
        EVENTS_XML.format(conversions=conversions, presentation=PRESENTATION)
    )
    info = parse_events(str(directory))
    return [
        e["page_key"]  # type: ignore[typeddict-item]
        for e in info.events
        if e["name"] in ("presentation", "cursor_v2")
    ]


def test_parse_events_uses_the_last_conversion_of_a_presentation(
    tmp_path: Path,
) -> None:
    conversions = conversion(1000, f"{PAGE_2},{PAGE_1}") + conversion(
        1500, f"{PAGE_1},{PAGE_2}"
    )
    assert page_keys_of(tmp_path, conversions) == [PAGE_1, PAGE_1]


def test_parse_events_without_page_ids_falls_back_to_page_numbers(
    tmp_path: Path,
) -> None:
    """Recordings from before page ids have a ConversionCompletedEvent without them."""
    assert page_keys_of(tmp_path, conversion(1000)) == [
        f"{PRESENTATION}/1",
        f"{PRESENTATION}/1",
    ]


def test_parse_events_skips_an_insert_of_pages(tmp_path: Path, capsys: Any) -> None:
    """The events that act on a page carry its id, so the insert itself is not read."""
    inserted = f"""<event timestamp="1500" module="PRESENTATION" eventname="PresentationPagesInsertedEvent">
    <presentationName>{PRESENTATION}</presentationName>
    <podId>DEFAULT_PRESENTATION_POD</podId>
    <pageIds>{PAGE_1},{PAGE_2},{INSERTED}</pageIds>
  </event>"""
    conversions = conversion(1000, f"{PAGE_1},{PAGE_2}") + inserted

    assert page_keys_of(tmp_path, conversions) == [PAGE_1, PAGE_1]
    assert "Unknown event" not in capsys.readouterr().out
