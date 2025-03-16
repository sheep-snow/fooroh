import json

from lib.aws.sqs import get_sqs_client
from lib.bs.client import get_client
from lib.bs.graph import get_followers, get_follows, get_list_members
from lib.log import get_logger
from settings import settings

logger = get_logger(__name__)


def handler(event, context):
    logger.info(f"Received event: {event}")
    sqs = get_sqs_client()
    try:
        client = get_client(settings.BOT_USERID, settings.BOT_APP_PASSWORD)
        # whitelist のメンバーを取得する
        whitelist = get_list_members(client, settings.WHITE_LIST_URI)
        # 無視リストのメンバーを取得する
        ignores = get_list_members(client, settings.IGNORE_LIST_URI)
        # フォローしているメンバーを取得する
        follows = get_follows(client)
        # フォロワーを取得する
        followers = get_followers(client)
        if len(whitelist) > 0:
            # whitelistに登録がある場合は、whitelistに含まれるユーザー以外をすべてignore扱いにする
            ignores = ignores.union(follows).union(followers).difference(whitelist)
        logger.info(f"Found {len(ignores)} ignores.")
        # フォローしているがフォローされていないユーザーをフォロー解除する処理にメッセージを送る
        unfollowers = follows.difference(ignores).difference(followers)
        # フォローしていないがフォローされているユーザーをフォローする処理にメッセージを送る
        newfollowers = followers.difference(ignores).difference(follows)
        logger.info(f"Found {len(unfollowers)} new unfollowers.")
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"message": "NG on getting unfollower/follower process.", "status": 200}

    try:
        # signout 通知を送る
        for unfollower in unfollowers:
            sqs.send_message(
                QueueUrl=settings.SIGNOUT_QUEUE_URL, MessageBody=json.dumps({"did": unfollower})
            )
            logger.info(f"Send did {unfollower} to {settings.SIGNOUT_QUEUE_URL}")
        logger.info(f"Found {len(newfollowers)} new followers.")
    except Exception as e:
        logger.error(f"Error on Signout Process: {e}")

    try:
        # signup 通知を送る
        for newfollower in newfollowers:
            sqs.send_message(
                QueueUrl=settings.FOLLOWED_QUEUE_URL, MessageBody=json.dumps({"did": newfollower})
            )
            logger.info(f"Send did {newfollower} to {settings.FOLLOWED_QUEUE_URL}")
    except Exception as e:
        logger.error(f"Error on Signup Process: {e}")

    return {"message": "OK", "status": 200}


if __name__ == "__main__":
    handler({}, {})
