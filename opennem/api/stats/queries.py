from datetime import datetime
from typing import List, Tuple

from opennem.core.networks import network_from_network_region
from opennem.core.normalizers import normalize_duid
from opennem.schema.network import NetworkSchema
from opennem.schema.time import TimeInterval, TimePeriod


def duid_in_case(facility_codes: List[str]) -> str:
    return ",".join(
        ["'{}'".format(i) for i in map(normalize_duid, facility_codes)]
    )


def power_facility(
    facility_codes: List[str],
    network_code: str,
    interval: TimeInterval,
    period: TimePeriod,
) -> str:

    scale = 1

    network = network_from_network_region(network_code)
    timezone = network.timezone_database

    if not timezone:
        timezone = "UTC"

    __query = """with intervals as (
            select generate_series(
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}') - '{period}'::interval,
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}'),
                '{interval}'::interval
            )::timestamp as interval
        )

        select
            i.interval as trading_day,
            fs.generated,
            fs.facility_code as facility_code
        from intervals i
        left outer join
            (select
                date_trunc('{trunc}', fs.trading_interval AT TIME ZONE '{timezone}')::timestamp  {interval_remainder} as interval,
                fs.facility_code,
                coalesce(avg(generated), 0) as generated
                from facility_scada fs
                where
                    fs.facility_code in ({facility_codes_parsed})
                    and fs.trading_interval > now() AT TIME ZONE '{timezone}' - '{period}'::interval
                    and fs.network_id = '{network_code}'
                group by 1, 2
            ) as fs on fs.interval = i.interval
        order by 1 desc, 2 desc"""

    query = __query.format(
        facility_codes_parsed=duid_in_case(facility_codes),
        network_code=network_code,
        trunc=interval.trunc,
        interval=interval.interval_human,
        interval_remainder=interval.get_sql_join(
            timezone=network.timezone_database
        ),
        period=period.period_sql,
        scale=scale,
        timezone=timezone,
    )

    return query


def power_network(
    network_code: str, interval: TimeInterval, period: TimePeriod,
) -> str:

    scale = 1

    network = network_from_network_region(network_code)
    timezone = network.timezone_database

    if not timezone:
        timezone = "UTC"

    __query = """with intervals as (
            select generate_series(
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}') - '{period}'::interval,
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}'),
                '{interval}'::interval
            )::timestamp as interval
        )

        select
            i.interval as trading_day,
            fs.generated,
            fs.facility_code as facility_code
        from intervals i
        left outer join
            (select
                date_trunc('{trunc}', fs.trading_interval AT TIME ZONE '{timezone}')::timestamp  {interval_remainder} as interval,
                fs.facility_code,
                coalesce(avg(generated), 0) as generated
                from facility_scada fs
                where
                    fs.trading_interval > now() AT TIME ZONE '{timezone}' - '{period}'::interval
                    and fs.network_id = '{network_code}'
                group by 1, 2
            ) as fs on fs.interval = i.interval
        order by 1 desc, 2 desc"""

    query = __query.format(
        network_code=network_code,
        trunc=interval.trunc,
        interval=interval.interval_human,
        interval_remainder=interval.get_sql_join(
            timezone=network.timezone_database
        ),
        period=period.period_sql,
        scale=scale,
        timezone=timezone,
    )

    return query


def energy_facility(
    facility_codes: List[str],
    network_code: str,
    interval: TimeInterval,
    period: TimePeriod,
) -> str:

    network = network_from_network_region(network_code)
    timezone = network.timezone_database

    __query = """with intervals as (
            select generate_series(
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}') - '{period}'::interval,
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}'),
                '{interval}'::interval
            )::timestamp as interval
        )

        select
            i.interval as trading_day,
            fs.generated,
            fs.facility_code as facility_code
        from intervals i
        left outer join
            (select
                date_trunc('{trunc}', fs.trading_interval AT TIME ZONE '{timezone}')::timestamp  {interval_remainder} as interval,
                fs.facility_code,
                coalesce(sum(fs.eoi_quantity), NULL) / {scale} as generated
                from facility_scada fs
                where
                    fs.facility_code in ({facility_codes_parsed})
                    and fs.trading_interval > now() AT TIME ZONE '{timezone}' - '{period}'::interval
                    and fs.network_id = '{network_code}'
                group by 1, 2
            ) as fs on fs.interval = i.interval
        order by 1 desc, 2 asc"""

    query = __query.format(
        facility_codes_parsed=duid_in_case(facility_codes),
        network_code=network_code,
        trunc=interval.trunc,
        interval=interval.interval_sql,
        interval_remainder=interval.get_sql_join(
            timezone=network.timezone_database
        ),
        period=period.period_sql,
        scale=network.intervals_per_hour,
        timezone=timezone,
    )

    return query


def energy_network(
    network: NetworkSchema, interval: TimeInterval, period: TimePeriod,
) -> str:

    timezone = network.timezone_database

    __query = """with intervals as (
            select generate_series(
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}') - '{period}'::interval,
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}'),
                '{interval}'::interval
            )::timestamp as interval
        )

        select
            i.interval as trading_day,
            fs.generated,
            fs.facility_code as facility_code
        from intervals i
        left outer join
            (select
                date_trunc('{trunc}', fs.trading_interval AT TIME ZONE '{timezone}')::timestamp  {interval_remainder} as interval,
                fs.facility_code,
                coalesce(sum(fs.eoi_quantity), NULL) / {scale} as generated
                from facility_scada fs
                where
                    fs.trading_interval > now() AT TIME ZONE '{timezone}' - '{period}'::interval
                    and fs.network_id = '{network_code}'
                group by 1, 2
            ) as fs on fs.interval = i.interval
        order by 1 desc, 2 asc"""

    query = __query.format(
        network_code=network.code,
        trunc=interval.trunc,
        interval=interval.interval_sql,
        interval_remainder=interval.get_sql_join(
            timezone=network.timezone_database
        ),
        period=period.period_sql,
        scale=network.intervals_per_hour,
        timezone=timezone,
    )

    return query


def energy_year_network(network_code: str = "WEM", year: int = None) -> str:
    if not year:
        year = datetime.today().year

    network_code = network_code.upper()

    network = network_from_network_region(network_code)
    timezone = network.timezone_database

    if not timezone:
        timezone = "UTC"

    return """
        select
            date_trunc('day', fs.trading_interval AT TIME ZONE '{timezone}') AS trading_day,
            max(fs.eoi_quantity) as energy_output,
            f.fueltech_id as fueltech
        from facility_scada fs
        left join facility f on fs.facility_code = f.code
        where
            f.fueltech_id is not null
            and extract('year' from fs.trading_interval AT TIME ZONE '{timezone}') = {year}
            and fs.network_id = '{network_code}'
        group by 1, f.fueltech_id
        order by 1 asc, 2 asc
    """.format(
        year=year, network_code=network_code, timezone=timezone
    )


def price_network_region(
    network_code: str,
    region_code: str,
    interval: TimeInterval,
    period: TimePeriod,
) -> str:

    network = network_from_network_region(network_code)
    timezone = network.timezone_database

    if not timezone:
        timezone = "UTC"

    __query = """
        with intervals as (
            select generate_series(
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}') - '{period}'::interval,
                date_trunc('{trunc}', now() AT TIME ZONE '{timezone}'),
                '{interval}'::interval
            )::timestamp as interval
        )

        select
            i.interval AS trading_day,
            avg(bs.price) as price
        from intervals i
        left join balancing_summary bs on date_trunc('{trunc}', bs.trading_interval AT TIME ZONE '{timezone}')::timestamp = i.interval
        where
            bs.network_region = '{region_code}'
            and bs.trading_interval > now() AT TIME ZONE '{timezone}' - '{period}'::interval
            and bs.network_id = '{network_code}'
        group by 1
        order by 1
    """

    query = __query.format(
        region_code=region_code,
        network_code=network_code,
        trunc=interval.trunc,
        interval=interval.interval_sql,
        period=period.period_sql,
        timezone=timezone,
    )

    return query
