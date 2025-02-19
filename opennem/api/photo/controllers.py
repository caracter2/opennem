import logging
import os
from io import BytesIO
from typing import Any

import requests
from PIL import Image

from opennem import settings
from opennem.utils.http import http
from opennem.utils.url import bucket_to_website

logger = logging.getLogger(__name__)

S3_EXPORT_DEFAULT_BUCKET = "s3://photos.opennem.org.au/"


UPLOAD_ARGS = {
    "ContentType": "image/jpeg",
}


def write_photo_to_s3(file_path: str, data: Any, overwrite: bool = False) -> int:
    """Writes a photo blob to the S3 photo bucket. Will by default
    not overwrite any existing paths"""
    # @TODO move this to aws.py
    s3_save_path = os.path.join(settings.photos_bucket_path, file_path)
    write_count = 0

    http_save_path = bucket_to_website(s3_save_path)

    # check if it already exits
    # @TODO check hashes
    if not overwrite:
        r = http.get(http_save_path)

        if r.ok:
            return len(r.content)

    # s3_client = boto3.client("s3")

    # with open(
    #     s3_save_path,
    #     "wb",
    #     transport_params=dict(multipart_upload_kwargs=UPLOAD_ARGS),
    # ) as fh:
    #     write_count = fh.write(data)

    # s3_client.upload_file(s3_save_path)

    logger.info(f"Wrote {len(data)} to {s3_save_path}")

    return write_count


def photos_process() -> None:
    """"""
    pass
    # session = SessionLocal()

    # photos: List[Photo] = session.query(Photo).filter_by(processed=False).all()

    # for photo in photos:
    #     r = write_photo_to_s3(photo.name, photo.url)


def store_photo(photo_url: str) -> None:
    img = Image.open(requests.get(photo_url, stream=True).raw)

    save_bugger = BytesIO()
    img.save(save_bugger, format="JPEG")

    write_photo_to_s3("test.jpeg", data=save_bugger.getbuffer())


if __name__ == "__main__":
    photos_process()
