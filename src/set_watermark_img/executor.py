import json
import mimetypes
import os
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from uuid import uuid4

import boto3
from atproto import Client, IdResolver, models

from firehose.listener import ALT_OF_SET_WATERMARK_IMG
from lib.aws.s3 import post_bytes_object, post_string_object
from lib.bs.client import get_client
from lib.bs.get_bsky_post_by_url import get_did_from_url, get_rkey_from_url
from lib.common_converter import get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def _get_authors_pds_client(author_did: str) -> Client:
    resolver = IdResolver()
    did_doc = resolver.did.resolve(author_did)
    # Since the image to be acquired is stored in the PDS in which the author participates, the Client of the PDS to which the author belongs is obtained from the author's DID.
    authors_pds_endpoint = did_doc.service[0].service_endpoint
    return Client(base_url=authors_pds_endpoint)


def handler(event, context):
    """SQSイベントが差すポストからウォーターマーク画像を特定し、フローを起動する"""
    logger.info(f"Received event: {event}")
    input = json.loads(event["Records"][0]["body"])
    sm_arn = os.environ["STATEMACHINE_ARN"]
    sfn_client = boto3.client("stepfunctions")
    rkey = get_rkey_from_url(input.get("uri"))
    did = get_did_from_url(input.get("uri"))
    client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    post = client.get_post(post_rkey=rkey, profile_identify=did)

    author_did = input.get("author_did")
    authors_pds_client = _get_authors_pds_client(author_did)
    for image in post.value.embed.images:
        if "alt" in image.model_fields_set and ALT_OF_SET_WATERMARK_IMG == image.alt:
            blob_cid = image.image.cid.encode()
            blob = authors_pds_client.com.atproto.sync.get_blob(
                models.ComAtprotoSyncGetBlob.Params(cid=blob_cid, did=author_did)
            )
            metadata = {
                "did": author_did,
                "mime_type": image.image.mime_type,
                "size": image.image.size,
                "width": image.aspect_ratio.width,
                "height": image.aspect_ratio.height,
            }
            id_of_did = get_id_of_did(author_did)
            # S3に画像とそのmetadataのセットを保存
            with BytesIO(blob) as f:
                img_object_name = (
                    PurePosixPath("images")
                    .joinpath(id_of_did)
                    .with_suffix(mimetypes.guess_extension(image.image.mime_type))
                )
                img_object_name = img_object_name.as_posix()
                post_bytes_object(settings.WATERMARKS_BUCKET_NAME, img_object_name, f)
                logger.info(f"Saved watermark image to S3 {img_object_name}")
                metadata["path"] = img_object_name
            with StringIO(json.dumps(metadata)) as f:
                metadata_obj_name = (
                    PurePosixPath("metadatas").joinpath(id_of_did).with_suffix(".json")
                )
                metadata_obj_name = metadata_obj_name.as_posix()
                post_string_object(settings.WATERMARKS_BUCKET_NAME, metadata_obj_name, f)
                logger.info(f"Saved metadata to S3 {metadata_obj_name}")
            # 1ポストあたり複数のウォーターマーク画像がある場合、最初に受理したものだけを使ってウォーターマークを設定する
            break

    execution_id = str(uuid4())
    sfn_client.start_execution(
        stateMachineArn=sm_arn, name=execution_id, input=json.dumps(metadata)
    )
    logger.info(f"Started state machine execution_id=`{execution_id}`")

    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    sample_event = {
        "Records": [
            {
                "body": '{"cid": "bafyreievlxsxato2b7yuyige7dxh6flnicgrsk75czpmw6wo2kh5wdmrk4", "uri": "at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3ljusggsobk2w", "author_did": "did:plc:yzw3jty3wrlfejayynmp6oh7", "created_at": "2025-03-08T15:07:25.813Z", "is_watermark": true}'
            }
        ]
    }
    handler(sample_event, {})
