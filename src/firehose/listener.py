"""Bluesky Firehose Listener

See:
    https://github.com/MarshalX/atproto/blob/main/examples/firehose/process_commits.py
"""

import json
import multiprocessing
import os
import signal
import time
from collections import defaultdict
from types import FrameType
from typing import Any

import boto3
from atproto import (
    CAR,
    AtUri,
    Client,
    FirehoseSubscribeReposClient,
    firehose_models,
    models,
    parse_subscribe_repos_message,
)

from lib.aws.sqs import get_sqs_client
from lib.bs.client import get_client
from lib.bs.graph import get_follows, get_list_members
from lib.log import get_logger
from settings import settings

_INTERESTED_RECORDS = {
    # models.ids.AppBskyGraphFollow: models.AppBskyGraphFollow,  # Follows
    models.ids.AppBskyFeedPost: models.AppBskyFeedPost  # Posts
}
"""Listen対象とするレコードの種類"""

ALT_OF_SET_WATERMARK_IMG = "fr"
ALT_OF_SKIP_WATERMARKING = "nofr"
MAX_QUEUE_SIZE = 10000
FOLLOWED_QUEUE_URL = os.getenv("FOLLOWED_QUEUE_URL")
SET_WATERMARK_IMG_QUEUE_URL = os.getenv("SET_WATERMARK_IMG_QUEUE_URL")
WATERMARKING_QUEUE_URL = os.getenv("WATERMARKING_QUEUE_URL")
CLUSTER_NAME = os.getenv("CLUSTER_NAME")
SERVICE_NAME = os.getenv("SERVICE_NAME")


FOLLOWED_LIST_UPDATE_INTERVAL_SECS = 30
"""フォロイーテーブルを更新する間隔"""

MEASURE_EVENT_INTERVAL_SECS = 10
"""イベントの計測間隔"""

logger = get_logger(__name__)
sqs_client = get_sqs_client()

client: FirehoseSubscribeReposClient = None

bluesky_client: Client = None
current_follows: set = set()
"""listener稼働中を通じて更新され続けるフォロイー"""

pool: multiprocessing.Pool = None
"""マルチプロセス用のプール"""

queue: multiprocessing.Queue = None
"""マルチプロセス用のキュー"""


def _get_ops_by_type(commit: models.ComAtprotoSyncSubscribeRepos.Commit) -> defaultdict:
    """Get operations by type

    Args:
        commit (models.ComAtprotoSyncSubscribeRepos.Commit): Commit object

    Returns:
        defaultdict: Operations by type
    """
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


def _is_post_has_image(record) -> bool:
    """画像を含む投稿であることを判定する"""
    try:
        if record.embed.images[0].image.mime_type.startswith("image/"):
            return True
    except Exception:
        pass
    return False


def _is_follows_post(post) -> bool:
    """followsによる投稿であることを判定する"""
    global current_follows
    return post["author"] in current_follows


def _is_watermarking_skip(record) -> bool:
    """ウォーターマーク付与を拒否するAltが付与されている事を判定する"""
    images_alt = {i.alt for i in record.embed.images if "alt" in i.model_fields_set}
    if ALT_OF_SKIP_WATERMARKING in images_alt:
        return True
    else:
        return False


def _is_set_watermark_img_post(record) -> bool:
    """ウォーターマーク画像の投稿であることを判定する"""
    images_alt = {i.alt for i in record.embed.images if "alt" in i.model_fields_set}
    if ALT_OF_SET_WATERMARK_IMG in images_alt:
        return True
    else:
        return False


def _followed_to_bot(record) -> bool:
    """Check if the followed DID is a bot user"""
    return record.startswith("did:at:bot:")


def worker_main(
    cursor_value: multiprocessing.Value, pool_queue: multiprocessing.Queue, sqs_client: boto3.client
) -> None:
    """Worker main function

    Args:
        cursor_value (multiprocessing.Value): value of the cursor
        pool_queue (multiprocessing.Queue): Queue object
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # we handle it in the main process

    while True:
        message = pool_queue.get()

        commit = parse_subscribe_repos_message(message)
        if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
            continue

        if commit.seq % 20 == 0:
            cursor_value.value = commit.seq

        if not commit.blocks:
            continue

        ops = _get_ops_by_type(commit)
        for created_post in ops[models.ids.AppBskyFeedPost]["created"]:
            # https://atproto.blue/en/latest/atproto/atproto_client.models.app.bsky.feed.post.html
            record = created_post["record"]

            if not _is_follows_post(created_post):
                # フォロイーの投稿ではない場合はスキップ
                continue
            if not _is_post_has_image(record):
                # 画像投稿ではない場合はスキップ
                continue
            basic_msg_body = {
                "cid": created_post["cid"],
                "uri": created_post["uri"],
                "author_did": created_post["author"],
                "created_at": record.created_at,
            }
            # ウォーターマーク画像の投稿を検知
            if _is_set_watermark_img_post(record):
                msg = json.dumps({**basic_msg_body, "is_watermark": True})
                logger.info(msg)
                sqs_client.send_message(QueueUrl=SET_WATERMARK_IMG_QUEUE_URL, MessageBody=msg)
                continue
            # ウォーターマーク拒否ではないコンテンツ画像の投稿を検知
            if _is_watermarking_skip(record) is False:
                msg = json.dumps(basic_msg_body)
                logger.info(msg)
                sqs_client.send_message(QueueUrl=WATERMARKING_QUEUE_URL, MessageBody=msg)
                continue


def get_firehose_params(
    cursor_value: multiprocessing.Value,
) -> models.ComAtprotoSyncSubscribeRepos.Params:
    """Get firehose params

    Args:
        cursor_value (multiprocessing.Value): Cursor value

    Returns:
        models.ComAtprotoSyncSubscribeRepos.Params: Firehose params
    """
    return models.ComAtprotoSyncSubscribeRepos.Params(cursor=cursor_value.value)


def update_follows_table_per_interval(func: callable) -> callable:
    """Update follows table per interval"""

    def wrapper(*args) -> Any:
        cur_time = time.time()

        if cur_time - wrapper.start_time >= FOLLOWED_LIST_UPDATE_INTERVAL_SECS:
            global current_follows
            global bluesky_client
            current_follows = _get_current_follows(bluesky_client)
            logger.debug(f"Update in memory Follows table, {len(current_follows)} follows.")
            wrapper.start_time = cur_time
            wrapper.calls = 0

        return func(*args)

    wrapper.start_time = time.time()

    return wrapper


def measure_events_per_interval(func: callable) -> callable:
    """Measure events per second"""

    def wrapper(*args) -> Any:
        wrapper.calls += 1
        cur_time = time.time()

        if cur_time - wrapper.start_time >= MEASURE_EVENT_INTERVAL_SECS:
            rate = int(wrapper.calls / MEASURE_EVENT_INTERVAL_SECS)
            logger.debug(f"NETWORK LOAD: {rate} events/second")
            wrapper.start_time = cur_time
            wrapper.calls = 0

        return func(*args)

    wrapper.calls = 0
    wrapper.start_time = time.time()

    return wrapper


def signal_handler(_: int, __: FrameType) -> None:
    """Signal handler"""
    logger.info(
        "Keyboard interrupt received. Waiting for the queue to empty before terminating processes..."
    )

    # Stop receiving new messages
    client.stop()

    # Drain the messages queue
    while not queue.empty():
        logger.info("Waiting for the queue to empty...")
        time.sleep(0.2)

    logger.info("Queue is empty. Gracefully terminating processes...")

    pool.terminate()
    pool.join()
    # exit the main process gracefully.
    logger.info("Listener stopped gracefully, Bye!")
    exit(0)


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


def on_callback_error_handler(error: BaseException) -> None:
    logger.error("Got error!")
    try:
        # エラー時のタスク再起動処理
        # エラーを吐いたら自タスクは起動している意味がないため自身で停止し
        # サービス定義の desired count に従って復帰させる
        logger.info("Stopping ECS tasks...")
        ecs_client = boto3.client("ecs")
        response = ecs_client.list_tasks(cluster=CLUSTER_NAME, launchType="FARGATE")
        for taskArn in response["taskArns"]:
            ecs_client.stop_task(cluster=CLUSTER_NAME, task=taskArn)
        logger.info("All ECS task stopped successfully.")
    except Exception:
        logger.warning("Failed to stop ECS tasks.")


def main():
    logger.info("Starting Bluesky Client Session...")
    global current_follows
    global bluesky_client
    bluesky_client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    # followsテーブルを最新化する
    current_follows = _get_current_follows(bluesky_client)
    logger.info("Got current follows successfully.")

    logger.info("Starting listener...")
    logger.info("Press Ctrl+C to stop the listener.")
    signal.signal(signal.SIGINT, signal_handler)
    start_cursor = None
    params = None
    cursor = multiprocessing.Value("i", 0)
    if start_cursor is not None:
        cursor = multiprocessing.Value("i", start_cursor)
        params = get_firehose_params(cursor)

    global client
    client = FirehoseSubscribeReposClient(params)

    workers_count = multiprocessing.cpu_count() * 2 - 1
    # workers_count = 1 # DEBUG

    queue = multiprocessing.Queue(maxsize=MAX_QUEUE_SIZE)
    pool = multiprocessing.Pool(workers_count, worker_main, (cursor, queue, sqs_client))  # noqa

    @update_follows_table_per_interval
    @measure_events_per_interval
    def on_message_handler(message: firehose_models.MessageFrame) -> None:
        if cursor.value:
            # we are using updating the cursor state here because of multiprocessing
            # typically you can call client.update_params() directly on commit processing
            client.update_params(get_firehose_params(cursor))

        queue.put(message)

    client.start(on_message_handler, on_callback_error_handler)
    # client.start(on_message_handler)


if __name__ == "__main__":
    main()
