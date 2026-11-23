# SPDX-FileCopyrightText: 2026 BigBlueButton Inc. and by respective authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stable per-page identity for the events of a recording.

A page number is not a stable name for a page. Inserting pages into a shared
presentation renumbers every page at and after the insert position, so the same
number can refer to two different pages at two points in the same recording.
Anything remembered per page - annotations, cursor positions, which background
to draw - therefore has to be keyed by the page's opaque id instead.

Recordings carry that id in two places: on the events themselves (``id`` on
GotoSlideEvent, ``whiteboardId`` on the whiteboard and cursor events) and in the
``pageIds`` element of ConversionCompletedEvent, which lists a presentation's
page ids in upload order. Recordings made before either existed get a composite
key built from the page number, which behaves exactly like the per-number
bookkeeping it replaces.

The presentation playback reads the same ids: BigBlueButton::Events.get_page_ids
(record-and-playback/core/lib/recordandplayback/generators/events.rb) keeps the
last ConversionCompletedEvent of each presentation, and the publish script
(record-and-playback/presentation/scripts/publish/presentation.rb) opens a
presentation shown for the first time on the first of those ids. Resolving the
same way here keeps the video and the presentation playback in agreement on
what a page is.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple


class PageKeyResolver:
    """Resolves the stable identity of the page an event refers to."""

    page_ids: Dict[str, List[str]]
    learned: Dict[Tuple[str, int], str]

    def __init__(self, page_ids: Optional[Mapping[str, Sequence[str]]] = None) -> None:
        """page_ids maps each presentation to its page ids in upload order."""
        self.page_ids = {
            presentation: list(ids) for presentation, ids in (page_ids or {}).items()
        }
        self.learned = {}

    def learn(
        self, presentation: Optional[str], slide: int, page_id: Optional[str]
    ) -> None:
        """Remember an id seen on an event, for pages that never carry one.

        A page can be shown before any event names it: the page on screen when
        a presentation is shared has no GotoSlideEvent of its own, but the
        annotations drawn on it name it, so the id can be borrowed from them.
        Like the upload-order page ids, this assumes the page number still
        refers to the same page; no event records an insert, so a number seen
        after one can name a different page. Events that carry their own id
        never depend on either; in recordings with page ids those are all the
        slide, whiteboard and cursor events.
        """
        if not page_id:
            return
        self.learned.setdefault((presentation or "", slide), page_id)

    def resolve(
        self, presentation: Optional[str], slide: int, page_id: Optional[str] = None
    ) -> str:
        """Name the page an event acts on.

        The presentation is unknown for events that happen before one is shared;
        those still get a key, so that every page-scoped event has one, but it
        can only be built from the page number.
        """
        if page_id:
            return page_id
        if presentation is not None:
            ids = self.page_ids.get(presentation)
            if ids and 0 <= slide < len(ids) and ids[slide]:
                return ids[slide]
        learned = self.learned.get((presentation or "", slide))
        if learned:
            return learned
        # Matches the composite ids recorded by BBB versions where the
        # whiteboardId was "<presentationId>/<pageNum>".
        return f"{presentation or ''}/{slide + 1}"
