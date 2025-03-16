import json
from pathlib import PurePosixPath

from lib.aws.s3 import delete_object, get_object, is_exiests_object
from lib.common_converter import get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    did = event["did"]
    target_bucket_name = settings.WATERMARKS_BUCKET_NAME
    id_of_did = get_id_of_did(did)

    # metadataを特定
    logger.info("Spotting metadata object ...")
    metadata_obj_name = PurePosixPath("metadatas").joinpath(id_of_did).with_suffix(".json")
    metadata_obj_name = metadata_obj_name.as_posix()
    if is_exiests_object(target_bucket_name, metadata_obj_name):
        got_object = get_object(target_bucket_name, metadata_obj_name)
        # 画像を特定
        logger.info("Spotting image object ...")
        metadata_str = got_object["Body"].read().decode("utf-8")
        logger.debug(f"Downloaded Metadata: `{metadata_str}`")
        metadata = json.loads(metadata_str)
        img_object_name = PurePosixPath(metadata["path"]).as_posix()

        # 画像とmetadataの順に削除する
        logger.info(f"Deleting `{img_object_name}` ...")
        response = delete_object(target_bucket_name, img_object_name)
        logger.info(f"Response: {str(response)}")

        logger.info(f"Deleting `{metadata_obj_name}` ...")
        response = delete_object(target_bucket_name, metadata_obj_name)
        logger.info(f"Response: {str(response)}")
    else:
        logger.info(f"Metadata object `{metadata_obj_name}` does not exist.")

    return {"did": did}


if __name__ == "__main__":
    handler({"did": "did:plc:e4pwxsrsghzjud5x7pbe6t65"}, {})
