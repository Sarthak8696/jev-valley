# A first look: three month-long runs on Jev

Before the benchmark, three single month-long runs (seeds 7, 11 and 21, rich questions, on 2026-10-25) were done by hand, to see whether the valley holds together with Jev and whether the animals really try to survive. They are one-off runs, read from their replays and request logs with a throwaway script that is not in the repo, so treat them as an early look and not as a measurement. Final populations:

| Seed | Rabbits (24 at the start) | Deer (10) | Wolves (5) | All three alive at the end |
|---|---|---|---|---|
| 7 | 45 | 6 | 2 | yes |
| 11 | 19 | 1 | 0 (the last wolf died on day 27) | no |
| 21 | 25 | 0 (the last deer died on day 19) | 4 | no |

- **The valley is not balanced for Jev yet.** With the old stand-in brains all three species survived on 96 to 97% of unseen seeds; with Jev they survived in one run of three. Rabbits are the buffer (74 to 130 born per run). Deer had 29 births against 52 deaths over the three runs, and all 18 wolf deaths were starvation. The valley has not been retuned for Jev.
- **Wolves chase deer almost as often as they chase rabbits, and rarely catch them:** 40 catches in 426 chases of deer (9%), against 229 in 535 chases of rabbits (43%). A chase costs a wolf three times the energy of resting, and it keeps the deer running: deer spent 21% of their hours fleeing.
- **The animals do try to survive.** Hungry prey with no wolf in sight ate 92% of the time (rabbits) and 96% (deer), and thirsty ones drank 88% and 95%. With a wolf within two tiles, rabbits fled 92% of the time and deer 93%. Hungry wolves with a carcass in sight scavenged 97% of the time, hungry wolves with prey in view hunted 83% of the time and scavenged 14%, and a parched wolf drank every time (18 of 18). The animals that starved died trying: in their last day, wolves spent 88% of their hours hunting or scavenging, and prey spent 62 to 71% eating and 20 to 34% running away. They starved because there was no prey or no food near them.
- **Two weaknesses.** Prey flee from wolves that are still three or more tiles away 66 to 80% of the time, which costs energy. And personality changes effort a great deal: lazy animals rested 53% of the time (rabbits), 41% (deer) and 72% (wolves), restless ones never. Lazy and timid wolves hunted or scavenged in 78% and 74% of their hungry hours, against 84 to 95% for the other personalities, and lazy wolves starved least (0.9 deaths per 1000 wolf-hours against 2.2 to 2.9; only 24 wolves in all, so this is a hint).

These runs are not benchmark results: the numbers were read by hand from the replays and the request logs, and nothing here comes from `python -m valley bench`. The benchmark has not been run against Jev yet. See the [README](../README.md#results-so-far) and [Limitations](../README.md#limitations).
