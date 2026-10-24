# Why the valley is balanced this way

How the valley was changed so that a month can end with all three species alive, and what the research behind each change was. The numbers and the experiments are in the [ecosystem redesign record](build-spec.md#ecosystem-redesign-record) of the build specification.

The first version of the valley ended with wolves alone on some runs, and with nobody left on others. A hand-written stand-in for a model kept all three species alive to the end of the month on only 29 of 60 seeds. The cause was water: 31% of rabbit deaths were thirst, and the median rabbit died five tiles from the nearest drink, so the rabbits went first and the wolves, which can go about 105 hours without food, outlived them. Wolves were never the problem.

The valley was changed in the ways real predator and prey systems suggest, and each change was tested alone before it was kept:

- **Water within reach.** No tile is more than five tiles, the rabbit's vision, from water. On the old map this alone took that stand-in from 48% to 97% of seeds with all three species alive.
- **Wolves are not perfect hunters.** Yellowstone wolves succeed in about 15 to 26% of hunts ([USGS](https://digitalcommons.unl.edu/usgsnpwrc/337)) and take calves out of proportion to their numbers ([Smith and others](https://digitalcommons.mtu.edu/michigantech-p/13805)). A hunting wolf can lose a prey that is still some way off, and weak animals are easier to catch than strong ones.
- **Food limits the prey.** Plants regrow slower, so the prey settle below their caps instead of piling up against them. NetLogo's wolf and sheep model needs the same thing to be stable ([NetLogo](https://ccl.northwestern.edu/netlogo/models/WolfSheepPredation)).
- **More room.** A bigger valley at a lower density gives prey places to be, which is the idea behind [Huffaker's mite experiment](https://en.wikipedia.org/wiki/Huffaker%27s_mite_experiment).

Things that did not help were tried and dropped: weaker wolves, stronger hiding, digestion time after a kill, and crowding between wolves. The valley was balanced with two hand-written stand-in brains, one that follows simple rules and one that picks at random, so that it could be checked without a model. With them, all three species survived on 96 to 97% of 100 unseen seeds, wolves were never the only species left, and the random brain collapsed every time. Those stand-ins were later removed because the valley does not run without a model, so how Jev does in this valley is what the benchmark is for. A first look with three month-long runs is under [Results](first-look.md), and it is not encouraging for the deer and the wolves. The numbers, the experiments and the limits are in the [ecosystem redesign record](build-spec.md#ecosystem-redesign-record).
