import json
import mimetypes
import os
from io import BytesIO
from pathlib import PurePosixPath

import boto3
from atproto import Client, IdResolver, models

from lib.aws.s3 import post_bytes_object, post_string_object
from lib.bs.client import get_client
from lib.bs.get_bsky_post_by_url import get_did_from_url, get_rkey_from_url
from lib.common_converter import generate_exec_id, get_id_of_did
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def _get_authors_pds_client(author_did: str) -> Client:
    resolver = IdResolver()
    did_doc = resolver.did.resolve(author_did)
    authors_pds_endpoint = did_doc.service[0].service_endpoint
    return Client(base_url=authors_pds_endpoint)


def _start_workflow(author_did: str, metadata: dict):
    """ステートマシンを起動する"""
    sm_arn = os.environ["STATEMACHINE_ARN"]
    sfn_client = boto3.client("stepfunctions")

    exec_id = generate_exec_id(author_did)
    sfn_client.start_execution(stateMachineArn=sm_arn, name=exec_id, input=json.dumps(metadata))
    logger.info(f"Started state machine execution_id=`{exec_id}`")


def _save_watermark_img_to_s3(event: dict):
    input = json.loads(event["Records"][0]["body"])
    rkey = get_rkey_from_url(input.get("uri"))
    did = get_did_from_url(input.get("uri"))
    client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    post = client.get_post(post_rkey=rkey, profile_identify=did)
    # いいねを付ける
    client.like(uri=input.get("uri"), cid=input.get("cid"))

    # ウォーターマーク画像を取得し、S3に保存
    author_did = input.get("author_did")
    authors_pds_client = _get_authors_pds_client(author_did)
    for image in post.value.embed.images:
        if "alt" in image.model_fields_set and settings.ALT_OF_SET_WATERMARK_IMG == image.alt:
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

            # メタデータをS3に保存
            metadata_obj_name = PurePosixPath("metadatas").joinpath(id_of_did).with_suffix(".json")
            metadata_obj_name = metadata_obj_name.as_posix()
            post_string_object(
                settings.WATERMARKS_BUCKET_NAME, metadata_obj_name, json.dumps(metadata)
            )
            logger.info(f"Saved metadata to S3 {metadata_obj_name}")

            # ステートマシンを起動
            _start_workflow(author_did, metadata)

            # 1ポストあたり複数のウォーターマーク画像がある場合、最初に受理したものだけを使ってウォーターマークを設定する
            break


def handler(event, context):
    """SQSイベントが差すポストからウォーターマーク画像を特定し、フローを起動する"""
    logger.info(f"Received event: {event}")
    try:
        _save_watermark_img_to_s3(event)
    except Exception as e:
        logger.error(e)

    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    sample_event = {
        "Records": [
            {
                "body": '{"cid": "bafyreiaytzibck6j2nza33zpsebg4kvdibisatohrzkwh3lmw3t6dvqvzq", "uri": "at://did:plc:yzw3jty3wrlfejayynmp6oh7/app.bsky.feed.post/3lkik73z4vs2l", "author_did": "did:plc:yzw3jty3wrlfejayynmp6oh7", "created_at": "2025-03-16T11:33:24.416Z"}'
            }
        ]
    }
    handler(sample_event, {})
