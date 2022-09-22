"""
Daily summary - fueltechs as proportion of demand
and other stats per network
"""
import logging
from datetime import datetime, timedelta
from operator import attrgetter
from textwrap import dedent
from typing import List

from datetime_truncate import truncate as date_trunc

from opennem.core.templates import serve_template
from opennem.db import get_database_engine
from opennem.notifications.slack import slack_message
from opennem.queries.summary import get_daily_fueltech_summary_query
from opennem.schema.core import BaseConfig
from opennem.schema.network import NetworkNEM, NetworkSchema
from opennem.settings import settings
from opennem.utils.dates import get_last_complete_day_for_network  # noqa: F401
from opennem.utils.sql import duid_in_case

logger = logging.getLogger("opennem.workers.daily_summary")


class DailySummaryResult(BaseConfig):
    trading_day: datetime
    network: str
    fueltech_id: str
    fueltech_label: str
    renewable: bool
    energy: float
    generated_total: float
    demand_total: float
    demand_proportion: float


class DailySummary(BaseConfig):
    trading_day: datetime
    network: str

    results: List[DailySummaryResult]

    @property
    def renewable_proportion(self) -> float:
        return sum([i.demand_proportion for i in filter(lambda x: x.renewable is True, self.results)])

    @property
    def records(self) -> List[DailySummaryResult]:
        return sorted(self.results, key=attrgetter("energy"), reverse=True)


def get_daily_fueltech_summary(network: NetworkSchema) -> DailySummary:
    engine = get_database_engine()
    _result = []
    day = get_last_complete_day_for_network(network)

    query = get_daily_fueltech_summary_query(day=day, network=network)

    with engine.connect() as c:
        logger.debug(query)
        _result = list(c.execute(query))

    records = [
        DailySummaryResult(
            trading_day=i[0],
            network=i[1],
            fueltech_id=i[2],
            fueltech_label=i[3],
            renewable=i[4],
            energy=i[5],
            generated_total=i[6],
            demand_total=i[7],
            demand_proportion=i[8],
        )
        for i in _result
    ]

    ds = DailySummary(trading_day=records[0].trading_day, network=records[0].network, results=records)

    return ds


def run_daily_fueltech_summary(network: NetworkSchema) -> None:
    ds = get_daily_fueltech_summary(network=network)

    _render = serve_template("tweet_daily_summary.md", ds=ds)

    logger.debug(_render)

    slack_sent = slack_message(_render)

    if slack_sent:
        logger.info("Sent slack message")

    else:
        logger.error("Could not send slack message for daily fueltech summary")


if __name__ == "__main__":
    run_daily_fueltech_summary(network=NetworkNEM)
