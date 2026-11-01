# Systems Navigator data availability

Reviewed 21 October 2026 against Frontier's journal manual, EDMC's plugin
documentation, the current EDMC-NavRoute source, Route Scoop's README,
ED Scout's source, and the existing local ExploData/Pioneer references.
This is our implementation and research summary; no reference-plugin code is bundled.

| Information | Game export or service | Available when | Important boundary |
| --- | --- | --- | --- |
| Destination primary star class | StartJump.StarClass, FSDTarget.StarClass, NavRoute.Route[].StarClass | Target/route known; StartJump is written at countdown | Describes the primary star, not every star in that system. N means neutron. |
| Primary neutron/fuel indication | Interpret that exported class | Before arrival, offline | A non-neutron/non-scoopable primary does not rule out useful companions. |
| Secondary-star types | Scan.StarType; public body databases | Local Scan events or a prior database report | A route entry alone is insufficient. Database absence is not proof of an empty system. |
| Honk and personal scan progress | FSSDiscoveryScan, Scan, FSSAllBodiesFound | When those journal events occur; prior local journals can be replayed | FSSDiscoveryScan contains progress and body counts, not a typed list of every star. |
| Reported system bodies | EDSM bodies API; EDAstro starsystem API | Before arrival for systems they know | These are player-reported inventories; coverage/completeness varies. This release uses EDSM only. |
| Fuel-star distance | Scan.DistanceFromArrivalLS / EDSM distanceToArrival | After a body record is known | This is from the arrival reference, not the ship's current three-dimensional position. |
| Globally never visited/honked | No authoritative public negative found | Cannot be established from a missing public record | WasDiscovered is a per-body prior-discovery flag, not a complete global visit audit. |

## Why other tools can warn during hyperspace

The game already exports the destination primary's class during the countdown.
Tools can interpret that immediately and start a cached database lookup while
the transit animation is playing. EDMC also provides NavRoute.json data to
plugins, including on restart via its state object. They do not need to wait
for the destination honk to identify a neutron primary.

Route Scoop explicitly distinguishes locally supplied primary-star information
from its optional EDAstro lookup for secondary stars. ED Scout uses EDSM and
explains why missing database records cannot guarantee an undiscovered system.
EDMC-NavRoute consumes route classes for its star-information display.

The in-game map's knowledge does not imply every displayed property is present
in the documented plugin exports. Our implementation uses documented exports
and public data rather than reading game memory or trying to scrape the map.

## Changes made to our code

- Read primary classes from StartJump, FSDTarget and NavRoute state.
- Prefetch the destination at StartJump without switching the current-system UI.
- Preserve late results under the correct system and avoid duplicate lookups.
- Recover old jump/target classifications during the existing background replay.
- Distinguish No (Known Stars) from a confirmed complete-system No.
- Use requests with certificate roots supplied by certifi, status checks,
  explicit connect/read timeouts and a response-size limit. EDMC specifically
  recommends requests over urllib due to system-certificate compatibility.
- Rebuild older caches automatically. No repeated window refreshes were added.

## Sources

- Frontier journal manual: https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf
- EDMC plugin API and HTTP guidance: https://github.com/EDCD/EDMarketConnector/blob/main/PLUGINS.md
- EDMC-NavRoute: https://github.com/Silarn/EDMC-NavRoute
- Route Scoop: https://gitlab.com/inutt/edmc-jump-fuel-plugin
- Route Scoop primary/secondary distinction: https://gitlab.com/inutt/edmc-jump-fuel-plugin/-/blob/main/README.md
- ED Scout: https://github.com/joncage/ed-scout
- EDSM bodies API: https://www.edsm.net/en_GB/api-system-v1
- EDAstro API: https://edastro.com/api-details.html

EDAstro documents 100 requests per 15 minutes and up to 10 systems per batch;
any future fallback integration must respect those limits. It has not been
added to this release merely because it appeared in the research.

## Local-first update policy (0.2.2)

Local history is applied before requests start. Current journal observations
are displayed immediately, and live events received during replay are merged
as the newer local source. Cached online data can fill missing fields while
a single background revalidation runs. Honks and scans do not trigger another
request, and failed requests do not clear previously known information.

Each stellar observation carries its data timestamp when supplied. Existing
local values are replaced only when both sources have comparable timestamps
and the online body's update timestamp is strictly newer. Equal timestamps,
missing dates and older online values retain the local value. A newly fetched
response is not automatically new data; fetch times and discovery-credit
dates are deliberately excluded from the comparison. Availability of a data
update timestamp varies, so the safe fallback is local priority plus gap filling.
