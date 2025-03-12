from io import BytesIO

from PIL import Image

from lib.aws.s3 import get_object
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    for path in event["image_path"]:
        with BytesIO(get_object(settings.WATERMARKED_IMAGE_BUCKET_NAME, path)["Body"].read()) as f:
            watermarked_img = Image.open(f)
            # TODO ポストを組み立ててユーザ名義で投稿する

    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    handler({}, {})
