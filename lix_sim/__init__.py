"""Lix OS — pygame simulator backend.

Drop-in replacement for lix_hw on a laptop. Exposes SimDisplay, SimButtons,
and SimOS which implement the same api.Display / api.Buttons / api.OS ABCs.
"""

from lix_sim.display import SimDisplay
from lix_sim.buttons import SimButtons
from lix_sim.os import SimOS
