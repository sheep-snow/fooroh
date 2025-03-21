import json

from lib.aws.s3 import post_string_object
from lib.common_converter import get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)

bucket_name = settings.USERINFO_BUCKET_NAME


def handler(event, context):
    """S3バケットに空のユーザファイルを新規作成する"""
    logger.info(f"Received event: {event}")
    did = event["did"]
    obj_key = get_id_of_did(did)
    if not did.startswith("did:plc:"):
        raise ValueError(f"Invalid did: {did}")
    post_string_object(bucket_name=bucket_name, key=f"{obj_key}", body=json.dumps({}))
    logger.info(f"Created user file: {obj_key} to {bucket_name}")
    return {"did": did}


if __name__ == "__main__":
    sample_event = {"did": "did:plc:yzw3jty3wrlfejayynmp6oh7"}
    handler(sample_event, {})
