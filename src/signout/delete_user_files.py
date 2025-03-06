from lib.aws.s3 import delete_object
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    did = event["did"]
    target_bucket_name = settings.USERINFO_BUCKET_NAME
    logger.info(f"Deleting user file for `{did}` from `{target_bucket_name}` ...")
    response = delete_object(target_bucket_name, did)
    logger.info(f"Response: {str(response)}")
    return {"did": did}


if __name__ == "__main__":
    print(handler({}, {}))
