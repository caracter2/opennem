import logging
from datetime import datetime
from pprint import pprint

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from opennem.db import db_connect
from opennem.db.models.opennem import Station
from opennem.geo.google_geo import place_search

logger = logging.getLogger(__name__)


def build_address_string(station_record):
    address_components = [
        station_record.network_name,
        station_record.locality,
        station_record.state,
        "Australia",
    ]

    address_string = ", ".join(str(i) for i in address_components if i)

    return address_string


def opennem_geocode(limit=None):
    engine = db_connect()
    session = sessionmaker(bind=engine)
    s = session()

    records = s.query(Station).filter(Station.geom is None).filter(Station.geocode_skip is False)

    count = 0
    skipped = 0
    records_added = 0

    for r in records:
        geo_address_string = build_address_string(r)

        logger.info(f"Geocoding record: {geo_address_string}")
        continue

        google_result = place_search(geo_address_string)

        pprint(google_result)

        if google_result and type(google_result) is list and len(google_result) > 0:
            result = google_result[0]

            r.place_id = result["place_id"]

            lat = result["geometry"]["location"]["lat"]
            lng = result["geometry"]["location"]["lng"]
            r.geom = f"SRID=4326;POINT({lng} {lat})"

            r.geocode_processed_at = datetime.now()
            r.geocode_by = "google"
            r.geocode_approved = False

            try:
                s.add(r)
                s.commit()
                records_added += 1
            except IntegrityError as e:
                logger.error(e)
                skipped += 1
                pass
            except Exception as e:
                skipped += 1
                logger.error(f"Error: {e}")
        else:
            skipped += 1

        count += 1
        if limit and count >= limit:
            break

    print(f"Geocode of opennem records done. Added {records_added} records. Couldn't match {skipped}")


if __name__ == "__main__":
    opennem_geocode()
