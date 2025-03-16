import asyncio
import json
import os
import signal
import time
from collections import defaultdict
from types import FrameType
from typing import Any

from atproto import (
    CAR,
    AsyncFirehoseSubscribeReposClient,
    AtUri,
    Client,
    firehose_models,
    models,
    parse_subscribe_repos_message,
)

from lib.aws.sqs import get_sqs_client
from lib.bs.client import get_client
from lib.bs.graph import get_follows, get_list_members
from lib.log import get_logger
from settings import settings

_INTERESTED_RECORDS = {models.ids.AppBskyFeedPost: models.AppBskyFeedPost}
FOLLOWED_LIST_UPDATE_INTERVAL_SECS = 600
"""フォロイーテーブルを更新する間隔"""

SET_WATERMARK_IMG_QUEUE_URL = os.getenv("SET_WATERMARK_IMG_QUEUE_URL")
WATERMARKING_QUEUE_URL = os.getenv("WATERMARKING_QUEUE_URL")
ALT_OF_SKIP_WATERMARKING = settings.ALT_OF_SKIP_WATERMARKING

logger = get_logger(__name__)


def _get_current_follows(bsclient: Client) -> set:
    whitelist = get_list_members(bsclient, settings.WHITE_LIST_URI)
    if len(whitelist) > 0:
        # whitelistに登録がある場合は
        # whitelistに含まれるユーザーのみをフォローしているとみなす
        return whitelist
    follows = get_follows(bsclient)
    ignores = get_list_members(bsclient, settings.IGNORE_LIST_URI)
    # 無視リストに登録されているユーザーを除外して返す
    return follows.difference(ignores)


def _get_ops_by_type(commit: models.ComAtprotoSyncSubscribeRepos.Commit) -> defaultdict:
    operation_by_type = defaultdict(lambda: {"created": [], "deleted": []})

    car = CAR.from_bytes(commit.blocks)
    for op in commit.ops:
        if op.action == "update":
            # not supported yet
            continue

        uri = AtUri.from_str(f"at://{commit.repo}/{op.path}")

        if op.action == "create":
            if not op.cid:
                continue

            create_info = {"uri": str(uri), "cid": str(op.cid), "author": commit.repo}

            record_raw_data = car.blocks.get(op.cid)
            if not record_raw_data:
                continue

            record = models.get_or_create(record_raw_data, strict=False)
            record_type = _INTERESTED_RECORDS.get(uri.collection)
            if record_type and models.is_record_type(record, record_type):
                operation_by_type[uri.collection]["created"].append(
                    {"record": record, **create_info}
                )

        if op.action == "delete":
            operation_by_type[uri.collection]["deleted"].append({"uri": str(uri)})

    return operation_by_type


def intervaled_events(func: callable) -> callable:
    def wrapper(*args) -> Any:
        wrapper.calls += 1
        cur_time = time.time()

        if cur_time - wrapper.start_time >= FOLLOWED_LIST_UPDATE_INTERVAL_SECS:
            bsclient = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
            global current_follows
            current_follows = _get_current_follows(bsclient)
            logger.debug(f"Update in memory Follows table, {len(current_follows)} follows.")
            wrapper.start_time = cur_time
            wrapper.calls = 0

        return func(*args)

    wrapper.calls = 0
    wrapper.start_time = time.time()

    return wrapper


async def signal_handler(_: int, __: FrameType) -> None:
    logger.info("Keyboard interrupt received. Stopping...")

    # Stop receiving new messages
    await client.stop()


async def _is_post_has_image(record) -> bool:
    """画像を含む投稿であることを判定する"""
    try:
        if record.embed.images[0].image.mime_type.startswith("image/"):
            return True
    except Exception:
        pass
    return False


async def _is_follows_post(post, current_follows) -> bool:
    """followsによる投稿であることを判定する"""
    return post["author"] in current_follows


async def _is_watermarking_skip(record, desired_alt) -> bool:
    """ウォーターマーク付与を拒否するAltが含まれている事を判定する"""
    images_alts = {i.alt for i in record.embed.images if "alt" in i.model_fields_set}
    contains = []
    for alt in images_alts:
        if isinstance(desired_alt, str):
            contains.append(desired_alt in alt)
    return any(contains)


async def _is_set_watermark_img_post(record) -> bool:
    """ウォーターマーク画像の投稿であることを判定する"""
    images_alts = {i.alt for i in record.embed.images if "alt" in i.model_fields_set}
    if settings.ALT_OF_SET_WATERMARK_IMG in images_alts:
        return True
    else:
        return False


async def main(firehose_client: AsyncFirehoseSubscribeReposClient) -> None:
    @intervaled_events
    async def on_message_handler(message: firehose_models.MessageFrame) -> None:
        global current_follows
        commit = parse_subscribe_repos_message(message)
        if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
            return

        if commit.seq % 20 == 0:
            firehose_client.update_params(
                models.ComAtprotoSyncSubscribeRepos.Params(cursor=commit.seq)
            )

        if not commit.blocks:
            return

        ops = _get_ops_by_type(commit)
        for created_post in ops[models.ids.AppBskyFeedPost]["created"]:
            # https://atproto.blue/en/latest/atproto/atproto_client.models.app.bsky.feed.post.html
            record = created_post["record"]

            if not await _is_follows_post(created_post, current_follows):
                # フォロイーの投稿ではない場合はスキップ
                continue
            if not await _is_post_has_image(record):
                # 画像投稿ではない場合はスキップ
                continue
            msg_body = json.dumps(
                {
                    "cid": created_post["cid"],
                    "uri": created_post["uri"],
                    "author_did": created_post["author"],
                    "created_at": record.created_at,
                }
            )
            # ウォーターマーク画像の投稿を検知
            if await _is_set_watermark_img_post(record):
                logger.info(f"Watermark Set Request Received: `{msg_body}`")
                sqs_client.send_message(QueueUrl=SET_WATERMARK_IMG_QUEUE_URL, MessageBody=msg_body)
                continue
            # ウォーターマーク拒否ではないコンテンツ画像の投稿を検知
            if await _is_watermarking_skip(record, ALT_OF_SKIP_WATERMARKING) is False:
                logger.info(f"Image Post Received: {msg_body}")
                sqs_client.send_message(QueueUrl=WATERMARKING_QUEUE_URL, MessageBody=msg_body)
                continue

    await client.start(on_message_handler)


if __name__ == "__main__":
    global current_follows
    global sqs_client
    sqs_client = get_sqs_client()
    bsclient = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    current_follows = _get_current_follows(bsclient)
    logger.info(f"Update in memory Follows table, {len(current_follows)} follows.")

    signal.signal(signal.SIGINT, lambda _, __: asyncio.create_task(signal_handler(_, __)))

    start_cursor = None

    params = None
    if start_cursor is not None:
        params = models.ComAtprotoSyncSubscribeRepos.Params(cursor=start_cursor)

    client = AsyncFirehoseSubscribeReposClient(params)
    asyncio.run(main(client))
