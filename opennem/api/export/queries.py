from datetime import timedelta
from textwrap import dedent

from sqlalchemy import sql
from sqlalchemy.sql.elements import TextClause

from opennem.api.stats.controllers import networks_to_in
from opennem.controllers.output.schema import OpennemExportSeries
from opennem.schema.network import NetworkAPVI, NetworkAU, NetworkNEM, NetworkSchema, NetworkWEM
from opennem.schema.stats import StatTypes


def weather_observation_query(time_series: OpennemExportSeries, station_codes: list[str]) -> str:
    # Get the time range using either the old way or the new v4 way
    fence_post_delta: timedelta = timedelta(minutes=0)

    time_series_range = time_series.get_range()
    date_start = time_series_range.start
    date_end = time_series_range.end

    if time_series.interval.interval >= 1440:
        # @TODO replace with mv
        __query = """
        select
            date_trunc('{trunc}', t.observation_hour at time zone '{tz}') as observation_time,
            t.station_id,
            avg(t.temp_avg),
            min(t.temp_min),
            max(t.temp_max)
        from (
            select
                time_bucket_gapfill('1 hour', observation_time) as observation_hour,
                fs.station_id,

                case
                    when avg(fs.temp_air) is not null
                        then avg(fs.temp_air)
                    when max(fs.temp_max) is not null and max(fs.temp_min) is not null
                        then ((max(fs.temp_max) + min(fs.temp_min)) / 2)
                    else NULL
                end as temp_avg,

                case when min(fs.temp_min) is not null
                    then min(fs.temp_min)
                    else min(fs.temp_air)
                end as temp_min,

                case when max(fs.temp_max) is not null
                    then max(fs.temp_max)
                    else max(fs.temp_air)
                end as temp_max

            from bom_observation fs
            where
                fs.station_id in ({station_codes}) and
                fs.observation_time <= '{date_end}' and
                fs.observation_time >= '{date_start}'
            group by 1, 2
        ) as t
        group by 1, 2
        order by 1 asc;
        """

        query = __query.format(
            trunc=time_series.interval.trunc,
            tz=time_series.network.timezone_database,
            station_codes=",".join([f"'{i}'" for i in station_codes]),
            date_start=date_start,
            date_end=date_end,
        )

    else:
        __query = """
        select
            time_bucket_gapfill('30 minutes', fs.observation_time) as ot,
            fs.station_id as station_id,

            case when min(fs.temp_air) is not null
                then avg(fs.temp_air)
                else NULL
            end as temp_air,

            case when min(fs.temp_min) is not null
                then min(fs.temp_min)
                else min(fs.temp_air)
            end as temp_min,

            case when max(fs.temp_max) is not null
                then max(fs.temp_max)
                else max(fs.temp_air)
            end as temp_max

        from bom_observation fs
        where
            fs.station_id in ({station_codes}) and
            fs.observation_time <= '{date_end}' and
            fs.observation_time >= '{date_start}'
        group by 1, 2
        order by 1 desc;
        """

        query = __query.format(
            station_codes=",".join([f"'{i}'" for i in station_codes]),
            date_start=date_start,
            date_end=date_end - fence_post_delta,
            tz=time_series.network.timezone_database,
        )

    return dedent(query)


def interconnector_power_flow(time_series: OpennemExportSeries, network_region: str) -> str:
    """Get interconnector region flows using materialized view"""

    ___query = """
    select
        time_bucket_gapfill(INTERVAL '5 minutes', bs.trading_interval) as trading_interval,
        bs.network_region,
        case when max(bs.net_interchange) < 0 then
            max(bs.net_interchange)
        else 0
        end as imports,
        case when max(bs.net_interchange) > 0 then
            max(bs.net_interchange)
        else 0
        end as exports
    from balancing_summary bs
    where
        bs.network_id = '{network_id}' and
        bs.network_region= '{region}' and
        bs.trading_interval <= '{date_end}' and
        bs.trading_interval >= '{date_start}'
    group by 1, 2
    order by trading_interval desc;


    """

    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    query = ___query.format(
        network_id=time_series.network.code,
        region=network_region,
        date_start=date_min,
        date_end=date_max,
    )

    return dedent(query)


def interconnector_flow_network_regions_query(time_series: OpennemExportSeries, network_region: str | None = None) -> str:
    """ """

    __query = """
    select
        t.trading_interval at time zone '{timezone}' as trading_interval,
        t.flow_region,
        t.network_region,
        t.interconnector_region_to,
        coalesce(sum(t.flow_power), NULL) as flow_power
    from
    (
        select
            time_bucket_gapfill('{interval_size}', fs.trading_interval) as trading_interval,
            f.network_region || '->' || f.interconnector_region_to as flow_region,
            f.network_region,
            f.interconnector_region_to,
            sum(fs.generated) as flow_power
        from facility_scada fs
        left join facility f on fs.facility_code = f.code
        where
            f.interconnector is True
            and f.network_id='{network_id}'
            and fs.trading_interval <= '{date_end}'
            and fs.trading_interval >= '{date_start}'
            {region_query}
        group by 1, 2, 3, 4
    ) as t
    group by 1, 2, 3, 4
    order by
        1 desc,
        2 asc
    """

    region_query = ""

    if network_region:
        region_query = f"and f.network_region='{network_region}'"

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    query = __query.format(
        timezone=time_series.network.timezone_database,
        interval_size=time_series.interval.interval_sql,
        network_id=time_series.network.code,
        region_query=region_query,
        date_start=date_min,
        date_end=date_max,
    )

    return dedent(query)


def country_stats_query(stat_type: StatTypes, country: str = "au") -> TextClause:
    return sql.text(
        dedent(
            """
                select
                    s.stat_date,
                    s.value,
                    s.stat_type
                from stats s
                where s.stat_type = :stat_type and s.country= :country
                order by s.stat_date desc
           """
        )
    ).bindparams(
        stat_type=str(stat_type),
        country=country,
    )


def price_network_query(
    time_series: OpennemExportSeries,
    group_field: str = "bs.network_id",
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
        select
            time_bucket_gapfill('{trunc}', bs.trading_interval) as trading_interval,
            {group_field},
            coalesce(avg(bs.price_dispatch), avg(bs.price)) as price
        from balancing_summary bs
        where
            bs.trading_interval <= '{date_max}' and
            bs.trading_interval >= '{date_min}' and
            {network_query}
            {network_region_query}
            1=1
        group by 1, 2
        order by 1 desc
    """

    timezone = time_series.network.timezone_database
    network_region_query = ""

    if network_region:
        network_region_query = f"bs.network_region='{network_region}' and "
        group_field = "bs.network_region"

    network_query = f"bs.network_id IN ({networks_to_in(networks_query)}) and "

    if len(networks_query) > 1:
        group_field = "'AU'"

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    return dedent(
        __query.format(
            network_query=network_query,
            trunc=time_series.interval.interval_sql,
            network_region_query=network_region_query,
            timezone=timezone,
            date_max=date_max,
            date_min=date_min,
            group_field=group_field,
        )
    )


def network_demand_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
    select
        t.trading_interval at time zone '{timezone}' as trading_interval,
        t.network_id,
        t.demand
    from (
        select
            time_bucket_gapfill('{interval}', trading_interval) as trading_interval,
            network_id,
            coalesce(max(demand_total), 0) as demand
        from balancing_summary bs
        where
            bs.trading_interval <= '{date_max}' and
            bs.trading_interval >= '{date_min}' and
            {network_query}
            {network_region_query}
            1=1
        group by
            1, {groups_additional}
    ) as t
    order by 1 desc;
    """

    group_keys = ["network_id"]
    network_region_query = ""

    if network_region:
        group_keys.append("network_region")
        network_region_query = f"bs.network_region = '{network_region}' and "

    groups_additional = ", ".join(group_keys)

    network_query = f"bs.network_id IN ({networks_to_in(networks_query)}) and "

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    query = __query.format(
        timezone=time_series.network.timezone_database,
        interval=time_series.interval.interval_sql,
        date_max=date_max,
        date_min=date_min,
        network_id=time_series.network.code,
        network_query=network_query,
        network_region_query=network_region_query,
        groups_additional=groups_additional,
    )

    return dedent(query)


def power_network_fueltech_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    """Query power stats"""

    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
    select
        t.trading_interval,
        t.fueltech_code,
        sum(t.fueltech_power)
    from (
        select
            time_bucket_gapfill('{trunc}', fs.trading_interval) AS trading_interval,
            ft.code as fueltech_code,
            coalesce(avg(fs.generated), 0) as fueltech_power
        from facility_scada fs
        join facility f on fs.facility_code = f.code
        join fueltech ft on f.fueltech_id = ft.code
        where
            fs.is_forecast is False and
            f.fueltech_id is not null and
            f.fueltech_id not in ({fueltechs_exclude}) and
            {network_query}
            {network_region_query}
            fs.trading_interval <= '{date_max}' and
            fs.trading_interval >= '{date_min}'
            {fueltech_filter}
        group by 1, f.code, 2
    ) as t
    group by 1, 2
    order by 1 desc
    """

    network_region_query: str = ""
    fueltech_filter: str = ""
    wem_apvi_case: str = ""
    timezone: str = time_series.network.timezone_database

    fueltechs_excluded = ["exports", "imports", "interconnector"]

    if NetworkNEM in networks_query or NetworkWEM in networks_query:
        fueltechs_excluded.append("solar_rooftop")

    if network_region:
        network_region_query = f"f.network_region='{network_region}' and "

    if NetworkWEM in networks_query:
        # silly single case we'll refactor out
        # APVI network is used to provide rooftop for WEM so we require it
        # in country-wide totals
        wem_apvi_case = "or (f.network_id='APVI' and f.network_region='WEM')"

    network_query = f"(f.network_id IN ({networks_to_in(networks_query)}) {wem_apvi_case}) and "

    # Get the data time range
    # use the new v2 feature if it has been provided otherwise use the old method
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    # If we have a fueltech filter, add it to the query
    fueltechs_exclude = ", ".join(f"'{i}'" for i in fueltechs_excluded)

    query = dedent(
        __query.format(
            network_query=network_query,
            trunc=time_series.interval.interval_sql,
            network_region_query=network_region_query,
            timezone=timezone,
            date_max=date_max,
            date_min=date_min,
            fueltech_filter=fueltech_filter,
            wem_apvi_case=wem_apvi_case,
            fueltechs_exclude=fueltechs_exclude,
        )
    )

    return query


def power_network_rooftop_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    """Query power stats"""

    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
        select
            t.trading_interval at time zone '{timezone}' as trading_interval,
            t.fueltech_code,
            coalesce(sum(t.facility_power), 0) as power
        from (

            select
                time_bucket_gapfill('30 minutes', fs.trading_interval)  AS trading_interval,
                ft.code as fueltech_code,
                {agg_func}(fs.generated) as facility_power
            from facility_scada fs
            join facility f on fs.facility_code = f.code
            join fueltech ft on f.fueltech_id = ft.code
            where
                {forecast_query}
                f.fueltech_id = 'solar_rooftop' and
                {network_query}
                {network_region_query}
                fs.trading_interval >= '{date_min}' and
                fs.trading_interval < '{date_max}'
            group by 1, 2
        ) as t
        group by 1, 2
        order by 1 desc
    """

    network_region_query: str = ""
    wem_apvi_case: str = ""
    agg_func = "sum"
    timezone: str = time_series.network.timezone_database

    forecast_query = f"fs.is_forecast is {time_series.forecast} and"

    if network_region:
        network_region_query = f"f.network_region='{network_region}' and "

    if NetworkWEM in networks_query:
        # silly single case we'll refactor out
        # APVI network is used to provide rooftop for WEM so we require it
        # in country-wide totals
        wem_apvi_case = "or (f.network_id='APVI' and f.network_region='WEM')"

        if NetworkAPVI in networks_query:
            networks_query.remove(NetworkAPVI)

        if NetworkNEM not in networks_query:
            agg_func = "max"

    network_query = f"(f.network_id IN ({networks_to_in(networks_query)}) {wem_apvi_case}) and "

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_min = time_series_range.start
    date_max = time_series_range.end

    if time_series.forecast:
        # @TODO move to purely in get_range()
        date_max = date_min + timedelta(hours=12)

    return dedent(
        __query.format(
            network_query=network_query,
            network_region_query=network_region_query,
            timezone=timezone,
            date_min=date_min,
            date_max=date_max,
            forecast_query=forecast_query,
            agg_func=agg_func,
        )
    )


""" Emission Queries """


def power_and_emissions_network_fueltech_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
) -> str:
    """Query emission stats for each network and fueltech"""

    __query = """
        select
            t.trading_interval at time zone '{timezone}',
            t.fueltech_code,
            sum(t.fueltech_power),
            sum(t.emissions),
            case
                when sum(t.fueltech_power) <= 0
                    then 0
                else
                    sum(t.emissions) / sum(t.fueltech_power) * {intervals_per_hour}
            end
        from
        (
            select
                time_bucket_gapfill('{trunc}', fs.trading_interval) AS trading_interval,
                ft.code as fueltech_code,
                case
                    when sum(fs.generated) > 0 then
                        sum(fs.generated) / {intervals_per_hour} * max(f.emissions_factor_co2)
                    else 0
                end as emissions,
                coalesce(max(fs.generated), 0) as fueltech_power
            from facility_scada fs
            join facility f on fs.facility_code = f.code
            join fueltech ft on f.fueltech_id = ft.code
            where
                fs.is_forecast is False and
                f.fueltech_id is not null and
                {network_query}
                {network_region_query}
                fs.trading_interval <= '{date_max}' and
                fs.trading_interval >= '{date_min}'
                {fueltech_filter}
            group by 1, f.code, 2
        ) as t
        group by 1, 2
        order by 1 desc;
    """

    network_region_query: str = ""
    fueltech_filter: str = ""
    timezone: str = time_series.network.timezone_database

    fueltechs_excluded = ["exports", "imports", "interconnector", "solar_rooftop", "solar_utility", "wind"]

    if network_region:
        network_region_query = f"f.network_region='{network_region}' and "

    network_query = f"f.network_id ='{time_series.network.code}' and"

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    fueltechs_exclude = ", ".join(f"'{i}'" for i in fueltechs_excluded)

    query = dedent(
        __query.format(
            network_query=network_query,
            trunc=time_series.interval.interval_sql,
            network_region_query=network_region_query,
            timezone=timezone,
            date_max=date_max,
            date_min=date_min,
            fueltech_filter=fueltech_filter,
            fueltechs_exclude=fueltechs_exclude,
            intervals_per_hour=time_series.network.intervals_per_hour,
        )
    )

    return query


def power_network_interconnector_emissions_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    """
    Get emissions for a network or network + region
    based on a year
    """

    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
    select
        t.trading_interval at time zone '{timezone}' as trading_interval,
        sum(t.imports_energy) / {energy_scale},
        sum(t.exports_energy) / {energy_scale},
        abs(sum(t.emissions_imports)) / {emissions_scale},
        abs(sum(t.emissions_exports)) / {emissions_scale},
        sum(t.market_value_imports) / {market_value_scale} as market_value_imports,
        sum(t.market_value_exports) / {market_value_scale} as market_value_exports,
        case
            when sum(t.imports_energy) > 0 then
                sum(t.emissions_imports) / sum(t.imports_energy) / {energy_scale}
            else 0.0
        end as imports_emission_factor,
        case
            when sum(t.exports_energy) > 0 then
                sum(t.emissions_exports) / sum(t.exports_energy) / {energy_scale}
            else 0.0
        end as exports_emission_factor
    from (
        select
            time_bucket_gapfill('5 min', t.trading_interval) as trading_interval,
            t.network_id,
            t.network_region,
            coalesce(t.energy_imports, 0) as imports_energy,
            coalesce(t.energy_exports, 0) as exports_energy,
            coalesce(t.emissions_imports, 0) as emissions_imports,
            coalesce(t.emissions_exports, 0) as emissions_exports,
            coalesce(t.market_value_imports, 0) as market_value_imports,
            coalesce(t.market_value_exports, 0) as market_value_exports
        from at_network_flows t
        where
            t.trading_interval <= '{date_max}' and
            t.trading_interval >= '{date_min}' and
            t.network_id = '{network_id}' and
            {network_region_query}
    ) as t
    group by 1
    order by 1 desc

    """

    # scale using opennem.units eventually (placeholder sql var)
    energy_scale: int = int(time_series.network.intervals_per_hour)
    emissions_scale: int = int(time_series.network.intervals_per_hour)
    market_value_scale: int = int(time_series.network.intervals_per_hour)

    timezone = time_series.network.timezone_database
    network_region_query = ""

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    if network_region:
        network_region_query = f"""
            t.network_region = '{network_region}'
        """

    query = dedent(
        __query.format(
            energy_scale=energy_scale,
            emissions_scale=emissions_scale,
            market_value_scale=market_value_scale,
            timezone=timezone,
            network_id=time_series.network.code,
            date_min=date_min,
            date_max=date_max,
            network_region_query=network_region_query,
        )
    )

    return query


"""
Demand queries
"""


def demand_network_region_query(
    time_series: OpennemExportSeries, network_region: str | None, networks: list[NetworkSchema] | None = None
) -> str:
    """Get the network demand energy and market_value"""

    ___query = """
        select
            date_trunc('{trunc}', trading_day) as trading_day,
            network_id,
            {network_region_select}
            round(sum(demand_energy), 4),
            round(sum(demand_market_value), 4)
        from at_network_demand
        where
            {network_query}
            {network_region}
            trading_day >= '{date_min}' and
            trading_day <= '{date_max}'
        group by 1,2 {group_by}
        order by
            1 asc
    """

    network_region_query = ""
    network_region_select = f"'{time_series.network.code}' as network_region,"
    group_by = ""

    if network_region:
        network_region_query = f"network_region='{network_region}' and"
        network_region_select = "network_region,"
        group_by = ",3"

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    networks_list = networks_to_in(time_series.network.get_networks_query())

    network_query = f"network_id IN ({networks_list}) and "

    return dedent(
        ___query.format(
            trunc=time_series.interval.trunc,
            date_min=date_min,
            date_max=date_max,
            network_id=time_series.network.code,
            network_region=network_region_query,
            network_region_select=network_region_select,
            group_by=group_by,
            network_query=network_query,
        )
    )


"""
Energy Queries
"""


def energy_network_fueltech_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
    coalesce_with: int | None = None,
) -> str:
    """
    Get Energy for a network or network + region
    based on a year
    """

    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
    select
        date_trunc('{trunc}', t.trading_day) as trading_interval,
        t.fueltech_id,
        sum(t.fueltech_energy),
        sum(t.fueltech_market_value),
        sum(t.fueltech_emissions)
    from
    (
        select
            time_bucket_gapfill('1d', t.trading_day) as trading_day,
            t.fueltech_id,
            coalesce(sum(t.energy) / 1000, {coalesce_with}) as fueltech_energy,
            coalesce(sum(t.market_value), {coalesce_with}) as fueltech_market_value,
            coalesce(sum(t.emissions), {coalesce_with}) as fueltech_emissions
        from at_facility_daily t
        where
            t.trading_day <= '{date_max}'::date and
            t.trading_day >= '{date_min}'::date and
            t.fueltech_id not in ('imports', 'exports', 'interconnector') and
            {network_query}
            {network_region_query}
            1=1
        group by 1, 2
    ) as t
    group by 1, 2
    order by 1 desc;
    """

    network_region_query = ""

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    date_max = time_series_range.end
    date_min = time_series_range.start

    trunc = time_series_range.interval.trunc

    if network_region:
        network_region_query = f"t.network_region='{network_region}' and"

    # @NOTE special case for WEM to only include APVI data for that network/region
    # and not double-count all of AU
    network_apvi_wem = ""

    if time_series.network in [NetworkWEM, NetworkAU]:
        network_apvi_wem = "or (t.network_id='APVI' and t.network_region in ('WEM'))"

        if NetworkAPVI in networks_query:
            networks_query.pop(networks_query.index(NetworkAPVI))

    networks_list = networks_to_in(networks_query)

    network_query = f"(t.network_id IN ({networks_list}) {network_apvi_wem}) and "

    return dedent(
        __query.format(
            trunc=trunc,
            date_min=date_min,
            date_max=date_max,
            network_query=network_query,
            network_region_query=network_region_query,
            coalesce_with=coalesce_with or "NULL",
        )
    )


def energy_network_interconnector_emissions_query(
    time_series: OpennemExportSeries,
    network_region: str | None = None,
    networks_query: list[NetworkSchema] | None = None,
) -> str:
    """
    Get emissions for a network or network + region
    based on a year
    """

    if not networks_query:
        networks_query = [time_series.network]

    if time_series.network not in networks_query:
        networks_query.append(time_series.network)

    __query = """
    select
        date_trunc('{trunc}', t.trading_interval at time zone '{timezone}') as trading_interval,
        sum(t.imports_energy) / 1000,
        sum(t.exports_energy) / 1000,
        abs(sum(t.emissions_imports)),
        abs(sum(t.emissions_exports)),
        sum(t.market_value_imports) as market_value_imports,
        sum(t.market_value_exports) as market_value_exports
    from (
        select
            time_bucket_gapfill('5 min', t.trading_interval) as trading_interval,
            t.network_id,
            t.network_region,
            coalesce(t.energy_imports, 0) as imports_energy,
            coalesce(t.energy_exports, 0) as exports_energy,
            coalesce(t.emissions_imports, 0) as emissions_imports,
            coalesce(t.emissions_exports, 0) as emissions_exports,
            coalesce(t.market_value_imports, 0) as market_value_imports,
            coalesce(t.market_value_exports, 0) as market_value_exports
        from at_network_flows t
        where
            t.trading_interval <= '{date_max}' and
            t.trading_interval >= '{date_min}' and
            t.network_id = '{network_id}' and
            {network_region_query}
    ) as t
    group by 1
    order by 1 desc

    """

    timezone = time_series.network.timezone_database
    network_region_query = ""

    # Get the time range using either the old way or the new v4 way
    time_series_range = time_series.get_range()
    interval_trunc = time_series_range.interval.trunc
    date_max = time_series_range.end
    date_min = time_series_range.start

    if network_region:
        network_region_query = f"""
            t.network_region = '{network_region}'
        """

    return dedent(
        __query.format(
            timezone=timezone,
            trunc=interval_trunc,
            network_id=time_series.network.code,
            date_min=date_min,
            date_max=date_max,
            network_region_query=network_region_query,
        )
    )
