import os

from lib.log import get_logger

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    watermarked_img_bucket_name = os.getenv("WATERMARKED_IMAGE_BUCKET")
    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    print(handler({}, {}))
