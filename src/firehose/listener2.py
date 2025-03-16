import asyncio
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
FOLLOWED_LIST_UPDATE_INTERVAL_SECS = 10
"""フォロイーテーブルを更新する間隔"""

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


def update_events_per_interval(func: callable) -> callable:
    def wrapper(*args) -> Any:
        wrapper.calls += 1
        cur_time = time.time()

        if cur_time - wrapper.start_time >= FOLLOWED_LIST_UPDATE_INTERVAL_SECS:
            global bsclient
            global current_follows
            current_follows = _get_current_follows(bsclient)
            logger.debug(f"Update in memory Follows table, {len(current_follows)} follows.")

        return func(*args)

    wrapper.calls = 0
    wrapper.start_time = time.time()

    return wrapper


def intervaled_events(func: callable) -> callable:
    def wrapper(*args) -> Any:
        wrapper.calls += 1
        cur_time = time.time()

        # if cur_time - wrapper.start_time >= 1:
        #     logger.debug(f"NETWORK LOAD: {wrapper.calls} events/second")
        #     wrapper.start_time = cur_time
        #     wrapper.calls = 0

        if cur_time - wrapper.start_time >= FOLLOWED_LIST_UPDATE_INTERVAL_SECS:
            global bsclient
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


async def main(firehose_client: AsyncFirehoseSubscribeReposClient) -> None:
    @intervaled_events
    async def on_message_handler(message: firehose_models.MessageFrame) -> None:
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
            author = created_post["author"]
            record = created_post["record"]

            inlined_text = record.text.replace("\n", " ")
            # logger.debug(
            #     f"NEW POST [CREATED_AT={record.created_at}][AUTHOR={author}]: {inlined_text}"
            # )

    await client.start(on_message_handler)


if __name__ == "__main__":
    global bsclient
    global current_follows
    global sqs_client
    sqs_client = get_sqs_client()
    bsclient = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
    current_follows = _get_current_follows(bsclient)

    signal.signal(signal.SIGINT, lambda _, __: asyncio.create_task(signal_handler(_, __)))

    start_cursor = None

    params = None
    if start_cursor is not None:
        params = models.ComAtprotoSyncSubscribeRepos.Params(cursor=start_cursor)

    client = AsyncFirehoseSubscribeReposClient(params)

    # use run() for a higher Python version
    asyncio.get_event_loop().run_until_complete(main(client))
