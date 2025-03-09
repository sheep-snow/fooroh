from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    watermarked_img_bucket_name = settings.WATERMARKED_IMAGE_BUCKET_NAME
    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    handler({}, {})
