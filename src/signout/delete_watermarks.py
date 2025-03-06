import json
import mimetypes
from pathlib import PurePosixPath

from lib.aws.s3 import delete_object, get_object, is_exiests_object
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    did = event["did"]
    target_bucket_name = settings.WATERMARKS_BUCKET_NAME

    # pat = r"^{}.*$".format(did)
    # keys = get_object_keys(target_bucket_name, pat)
    # for key in keys:
    #     logger.info(f"Deleting `{key}` ...")
    #     response = delete_object(target_bucket_name, key)
    #     logger.info(f"Response: {str(response)}")

    # metadataを特定
    logger.info("Spotting metadata object ...")
    metadata_obj_name = PurePosixPath("metadatas").joinpath(did).with_suffix(".json")
    metadata_obj_name = metadata_obj_name.as_posix()
    if is_exiests_object(target_bucket_name, metadata_obj_name):
        got_object = get_object(target_bucket_name, metadata_obj_name)
        # 画像を特定
        logger.info("Spotting image object ...")
        metadata = json.loads(got_object["Body"].read().decode("utf-8"))
        suffix = mimetypes.guess_all_extensions(metadata["mime_type"]).pop()
        img_object_name = PurePosixPath("images").joinpath(did).with_suffix(suffix)
        img_object_name = img_object_name.as_posix()

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
