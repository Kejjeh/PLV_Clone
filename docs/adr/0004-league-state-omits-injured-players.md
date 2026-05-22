# league_state has no `injured_players()` method — the wrong call must be uncallable

The IL slot (`lineup_slot=='IL'`) vs IL status (`injured==True`) distinction is load-bearing for roster-capacity math: a player can be `injured` while occupying their starting slot (Langford OF), or on the bench (Helsley BE), and counting `injured==True` as "occupies an IL slot" produces wrong free-capacity numbers. This had a CLAUDE.md feedback entry (`feedback_il_slot_vs_il_status.md`) warning callers off `injured==True` for IL accounting. The warning lived implicitly in the pattern, and Claude Code reached for the wrong path anyway — multiple decision scripts re-derived IL math against `injured` rather than `lineup_slot`.

**Decision:** `league_state` has no `injured_players()` method. There is no convenience accessor for the `injured` flag at all. Callers that genuinely need the injury flag (display purposes, injury-status reports) read `my_roster()` and filter `injured==True` explicitly in two lines. The distinction becomes visible at the call site rather than hidden behind a method name.

## Why

Same principle as `league_state.available_fa()` having no `size=` parameter (the `size=2000` default lives inside the method, not as a caller knob): make the wrong call uncallable. The docstring-as-discipline approach was tried and failed for `injured==True`; offering a method named `injured_players()` would invite exactly the bug it warns against.

## Considered and rejected

- **Keep the method, document with a strong docstring warning.** Already tried implicitly via the CLAUDE.md feedback entry. Did not prevent the bug — when the method exists, it gets called.
- **Keep the method, deprecate with a runtime warning.** Trains callers to ignore warnings; the bug class persists during the deprecation window.

## Future contributors

A reasonable instinct is to add `injured_players()` back as a small helper. This ADR is the answer to "why not?" — the absence is the enforcement mechanism.
