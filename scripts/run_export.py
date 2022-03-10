#!/usr/bin/env python
"""
Scratchpad to export JSON's for unit tests + testing
"""

from datetime import datetime, timedelta

from opennem.api.export.map import PriorityType, StatType, get_export_map, get_weekly_export_map
from opennem.api.export.tasks import export_electricitymap, export_energy, export_power
from opennem.api.stats.controllers import get_scada_range
from opennem.core.compat.loader import get_dataset
from opennem.schema.network import NetworkAEMORooftop, NetworkAPVI, NetworkNEM, NetworkWEM
from opennem.workers.aggregates import run_aggregates_all_days
from opennem.workers.gap_fill import run_energy_gapfill


def run_tests() -> None:
    export_map = get_export_map()

    power = (
        export_map.get_by_network_id("WEM").get_by_stat_type(StatType.power)
        # .get_by_network_region("NSW1")
        # .get_by_priority(PriorityType.history)
        .get_by_priority(PriorityType.live)
    )

    # export_power(power.resources)
    # return None

    # print(power.resources)

    energy_map = (
        export_map.get_by_network_id("NEM")
        .get_by_network_region("SA1")
        .get_by_stat_type(StatType.energy)
        .get_by_priority(PriorityType.monthly)
        # .get_by_years([2022])
    )

    if len(energy_map.resources):
        export_energy(energy_map.resources)

    return None

    energy_map = (
        export_map
        # .get_by_priority(PriorityType.daily)
        .get_by_stat_type(StatType.energy).get_by_network_id("WEM")
        # .get_by_network_region("NSW1")
        # .get_by_years([2021])
    )

    for r in energy_map.resources:
        print(
            "Exporting: {} {} {}: {} => {}".format(
                r.year, r.network.code, r.network_region, r.date_range.start, r.date_range.end
            )
        )
        export_energy([r])

    # if len(energy_map.resources):
    #     print(
    #         export_map.resources[0].network.code,
    #         [i.code for i in export_map.resources[0].networks],
    #     )
    #     export_energy(energy_map.resources)


def load_flows() -> None:
    pass


def fallback_runner() -> None:
    run_energy_gapfill(days=30)
    run_aggregates_all_days(days=30)
    export_energy(latest=False)


from opennem.workers.energy import run_energy_calc

#
if __name__ == "__main__":
    run_tests()
    # export_energy(latest=False)
    # fallback_runner()
    # dmin = datetime.fromisoformat("2022-02-17 07:00:00+08:00")
    # dmax = dmin + timedelta(hours=1)
    # export_energy(latest=True)
    # run_energy_calc(dmin, dmax, network=NetworkWEM)
