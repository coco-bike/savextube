# -*- coding: utf-8 -*-
"""消息更新器工厂。"""


def build_reply_message_updater(message, logger):
    """构建基于 message.reply 的异步更新器。"""

    async def message_updater(text_or_dict):
        try:
            if not message or not hasattr(message, "reply"):
                logger.warning("⚠️ message 对象不可用，跳过进度更新")
                return

            if isinstance(text_or_dict, dict):
                await message.reply(str(text_or_dict))
            else:
                await message.reply(text_or_dict)
        except Exception as e:
            logger.warning(f"⚠️ 更新进度消息失败: {e}")

    return message_updater
