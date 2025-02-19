"""OpenNEM Network Flows v3

Creates an aggregate table with network flows (imports/exports), emissions
and market_value

"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from opennem.core.flow_solver import solve_flow_emissions_for_interval
from opennem.db import get_database_engine
from opennem.db.bulk_insert_csv import build_insert_query, generate_csv_from_records
from opennem.db.models.opennem import AggregateNetworkFlows
from opennem.schema.network import NetworkNEM, NetworkSchema

logger = logging.getLogger("opennem.aggregates.flows_v3")


class FlowWorkerException(Exception):
    pass


def load_interconnector_intervals(interval: datetime, network: NetworkSchema) -> pd.DataFrame:
    """Load interconnector flows for an interval.

    Returns
        pd.DataFrame: DataFrame containing interconnector flows for an interval.


    Example return dataframe:

        trading_interval    interconnector_region_from interconnector_region_to  generated     energy
        2023-04-09 10:15:00                       NSW1                     QLD1 -669.90010 -55.825008
        2023-04-09 10:15:00                       TAS1                     VIC1 -399.80002 -33.316668
        2023-04-09 10:15:00                       VIC1                     NSW1 -261.80997 -21.817498
        2023-04-09 10:15:00                       VIC1                      SA1  412.31787  34.359822
    """
    engine = get_database_engine()

    query = """
        select
            fs.trading_interval at time zone '{timezone}' as trading_interval,
            f.interconnector_region_from,
            f.interconnector_region_to,
            coalesce(sum(fs.generated), 0) as generated,
            coalesce(sum(fs.generated) / 12, 0) as energy
        from facility_scada fs
        left join facility f
            on fs.facility_code = f.code
        where
            fs.trading_interval = '{date_start}'
            and f.interconnector is True
            and f.network_id = '{network_id}'
        group by 1, 2, 3
        order by
            1 asc;

    """.format(
        date_start=interval,
        timezone=network.timezone_database,
        network_id=network.code,
    )

    logger.debug(query)

    df_gen = pd.read_sql(query, con=engine, index_col=["trading_interval"])

    if df_gen.empty:
        raise FlowWorkerException("No results from load_interconnector_intervals")

    return df_gen


def load_energy_and_emissions_for_intervals(
    interval_start: datetime, interval_end: datetime, network: NetworkSchema
) -> pd.DataFrame:
    """
    Fetch all energy and emissions for each network region for a network.

    Non-inclusive of interval_end.

    Args:
        interval_start (datetime): Start of the interval.
        interval_end (datetime): End of the interval.
        network (NetworkSchema): Network schema object.

    Returns:
        pd.DataFrame: DataFrame containing energy and emissions data for each network region.
            Columns:
                - trading_interval (datetime): Trading interval.
                - network_id (str): Network ID.
                - network_region (str): Network region.
                - energy (float): Sum of energy.
                - emissions (float): Sum of emissions.
                - emission_intensity (float): Emission intensity.

    Raises:
        FlowWorkerException: If no results are obtained from load_interconnector_intervals.

    Example return dataframe:


        trading_interval    network_id network_region      energy   emissions  emissions_intensity
        2023-04-09 10:20:00        NEM           NSW1  468.105472  226.549976             0.483972
        2023-04-09 10:20:00        NEM           QLD1  459.590348  295.124417             0.642147
        2023-04-09 10:20:00        NEM            SA1   36.929530    9.063695             0.245432
        2023-04-09 10:20:00        NEM           TAS1   71.088342    0.000000             0.000000
        2023-04-09 10:20:00        NEM           VIC1  387.120670  236.121274             0.609942
    """

    engine = get_database_engine()

    query = """
        select
            generated_intervals.trading_interval,
            generated_intervals.network_id,
            generated_intervals.network_region,
            sum(generated_intervals.energy) as energy,
            sum(generated_intervals.emissions) as emissions,
            case when sum(generated_intervals.emissions) > 0
                then sum(generated_intervals.emissions) / sum(generated_intervals.energy)
                else 0
            end as emissions_intensity
        from
        (
            select
                fs.trading_interval at time zone 'AEST' as trading_interval,
                f.network_id,
                f.network_region,
                fs.facility_code,
                sum(sum(fs.generated)) over (partition by fs.facility_code order by fs.trading_interval asc) / 2 / 12 as energy,
                case when f.emissions_factor_co2 > 0
                    then sum(sum(fs.generated)) over (partition by fs.facility_code order by fs.trading_interval asc) / 2 / 12  * f.emissions_factor_co2
                    else 0
                end as emissions
            from facility_scada fs
            left join facility f on fs.facility_code = f.code
            where
                fs.trading_interval >= '{interval_start}'
                and fs.trading_interval <= '{interval_end}'
                and f.network_id IN ('{network_id}')
                and f.interconnector is False
                and fs.generated > 0
            group by fs.trading_interval, fs.facility_code, f.emissions_factor_co2, f.network_region, f.network_id
        ) as generated_intervals
        where
            generated_intervals.trading_interval = '{interval_end}'
        group by 1, 2, 3
        order by 1 asc;
    """.format(
        interval_start=interval_start, interval_end=interval_end, network_id=network.code
    )

    logger.debug(query)

    df_gen = pd.read_sql(query, con=engine)

    if df_gen.empty:
        raise FlowWorkerException("No results from load_interconnector_intervals")

    return df_gen


def calculate_total_import_and_export_per_region_for_interval(interconnector_data: pd.DataFrame) -> pd.DataFrame:
    """Calculates total import and export energy for a region using the interconnector dataframe

    Args:
        interconnector_data (pd.DataFrame): interconnector dataframe from load_interconnector_intervals

    Returns:
        pd.DataFrame: total imports and export for each region for each interval

    Example return dataframe:

    network_id  network_region  energy_imports  energy_exports
    NEM         NSW1                      82.5             0.0
                QLD1                       0.0            55.0
                SA1                       22.0             0.0
                TAS1                       0.0            11.0
                VIC1                      11.0            49.5
    """

    dx = interconnector_data.groupby(["interconnector_region_from", "interconnector_region_to"]).energy.sum().reset_index()

    # invert regions
    dy = dx.rename(
        columns={
            "interconnector_region_from": "interconnector_region_to",
            "interconnector_region_to": "interconnector_region_from",
        }
    )

    # set indexes
    dy.set_index(["interconnector_region_to", "interconnector_region_from"], inplace=True)
    dx.set_index(["interconnector_region_to", "interconnector_region_from"], inplace=True)

    dy["energy"] *= -1

    dx.loc[dx.energy < 0, "energy"] = 0
    dy.loc[dy.energy < 0, "energy"] = 0

    f = pd.concat([dx, dy])

    energy_flows = pd.DataFrame(
        {
            "energy_imports": f.groupby("interconnector_region_to").energy.sum(),
            "energy_exports": f.groupby("interconnector_region_from").energy.sum(),
        }
    )

    energy_flows["network_id"] = "NEM"

    energy_flows.reset_index(inplace=True)
    energy_flows.rename(columns={"index": "network_region"}, inplace=True)
    # energy_flows.set_index(["network_id", "network_region"], inplace=True)

    return energy_flows


def calculate_demand_region_for_interval(energy_and_emissions: pd.DataFrame, imports_and_export: pd.DataFrame) -> pd.DataFrame:
    """
    Takes energy and emissions and imports and exports and calculates demand for each region and adds it to a merged
    total dataframe
    """

    df_with_demand = pd.merge(energy_and_emissions, imports_and_export)
    df_with_demand["demand"] = df_with_demand["energy"] + df_with_demand["energy_imports"] - df_with_demand["energy_exports"]

    return df_with_demand


def persist_network_flows_and_emissions_for_interval(flow_results: list[dict]) -> int:
    """Takes a list of generation values and calculates energies and bulk-inserts
    into the database"""

    if not flow_results:
        raise FlowWorkerException("No flow results to persist")

    records_to_store = flow_results

    # Build SQL + CSV and bulk-insert
    sql_query = build_insert_query(
        AggregateNetworkFlows,  # type: ignore
        [
            "energy_imports",
            "energy_exports",
            "emissions_imports",
            "emissions_exports",
            "market_value_imports",
            "market_value_exports",
            "updated_at",
        ],
    )
    conn = get_database_engine().raw_connection()
    cursor = conn.cursor()

    csv_content = generate_csv_from_records(
        AggregateNetworkFlows,  # type: ignore
        records_to_store,
        column_names=list(records_to_store[0].keys()),
    )

    try:
        logger.debug(sql_query)
        cursor.copy_expert(sql_query, csv_content)
        conn.commit()
    except Exception as e:
        logger.error(f"Error inserting records: {e}")
        return 0

    logger.info(f"Inserted {len(records_to_store)} records")

    return len(records_to_store)


def run_aggregate_flow_for_interval_v3(interval: datetime, network: NetworkSchema) -> None:
    """This method runs the aggregate for an interval and for a network using flow solver

    This is version 3 of the method and sits behind the settings.network_flows_v3 feature flag

    Args:
        interval (datetime): _description_
        network (NetworkSchema): _description_
    """

    # 1. get
    energy_and_emissions = load_energy_and_emissions_for_intervals(
        interval_start=interval, interval_end=interval + timedelta(minutes=5), network=network
    )

    # 2. get interconnector data and calculate region imports/exports net
    interconnector_data = load_interconnector_intervals(interval=interval, network=network)

    region_imports_and_exports = calculate_total_import_and_export_per_region_for_interval(
        interconnector_data=interconnector_data
    )

    # 3. calculate demand for each region and add it to the dataframe
    calculate_demand_region_for_interval(energy_and_emissions=energy_and_emissions, imports_and_export=region_imports_and_exports)

    # 4. Solve.
    region_flows_and_emissions = solve_flow_emissions_for_interval(
        energy_and_emissions=energy_and_emissions,
        interconnector=interconnector_data,
    )

    # 5. net out emissions and join with energy and emissions

    # @TODO net out flows
    region_flows_and_emissions = pd.merge(region_flows_and_emissions, region_imports_and_exports)

    # Persist to database aggregate table
    persist_network_flows_and_emissions_for_interval(region_flows_and_emissions)


# debug entry point
if __name__ == "__main__":
    interval = datetime.fromisoformat("2023-04-09T10:15:00+10:00")
    run_aggregate_flow_for_interval_v3(interval=interval, network=NetworkNEM)
