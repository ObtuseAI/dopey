# Paper Execution Model

Tickets derive every contract ID, quantity, side, type, expiry, strike, and multiplier
from the frozen candidate; callers cannot omit a protective leg or substitute an
underlying. Risk, behavioral, and negative-control gates are computed inside the
builder from typed inputs bound to the frozen environment hash. Sell-bearing
structures remain abstention-only while the short-option lifecycle is uncertified.

Only a complete, content-addressed, sized, firm `nbbo_quote` can construct a paper
price. Public snapshots, previews, model values, and realized-fill labels are
separate evidence tiers. The ticket identity includes opportunity, candidate,
environment, price triples, controls, maximum loss, and all management rules.

A paper intent begins as `pending_later_quote_witness`. A later quote for every leg
must pass the full quote gate, occur inside the frozen entry/cancellation window,
show enough size, stay within package skew, and cross the frozen limit. The result is
still simulated and never realized evidence. No live connector exists.

The current price kernel accounts for adverse side, frozen slippage, and commission.
Exchange fees, impact, funding, borrow, taxes, and opportunity cost are not yet an
enforced complete-cost object, so execution or profitability certification remains
blocked. Shared provenance: `ARTIFACT_PROVENANCE.json`.
