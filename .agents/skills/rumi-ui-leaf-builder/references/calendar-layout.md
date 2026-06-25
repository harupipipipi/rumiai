# Calendar Layout

- Treat overlap placement as a special layout algorithm. A leaf should own at most one such algorithm.
- Split WeekGrid, TimeAxis, EventBlock, EventEditor, OverlapLayout, and MobileAgenda when complexity rises.
- Mobile calendar views should change topology instead of squeezing the desktop grid.
- Event titles, times, and conflict state must remain readable without color alone.
