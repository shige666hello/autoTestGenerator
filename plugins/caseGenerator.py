# encoding:utf-8

import os
import json
from plugins import Plugin
from bridge.context import ContextType
from plugins.event import Event, EventContext, EventAction
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from config import conf

@Plugin.register(
    name="TestCaseGenerator",
    desire_priority=-1,
    hidden=True,
    desc="A plugin to generate test cases based on user input",
    version="0.1",
    author="your_name",
)
class TestCaseGenerator(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            self.prompt1 = None
            self.prompt2 = None
            logger.info("[TestCaseGenerator] inited")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        except Exception as e:
            logger.error(f"[TestCaseGenerator] 初始化异常：{e}")
            raise Exception("[TestCaseGenerator] init failed, ignore")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            if e_context["context"].type == ContextType.PATPAT:
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = self.patpat_prompt
                e_context.action = EventAction.BREAK  # 事件结束，进入默认处理逻辑
                if not self.config or not self.config.get("use_character_desc"):
                    e_context["context"]["generate_breaked_by"] = EventAction.BREAK
            return

        content = e_context["context"].content
        logger.debug("[TestCaseGenerator] on_handle_context. content: %s" % content)

        if "生成测试用例" in content:
            if not self.prompt1:
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "请添加产品需求。"
                self.prompt1 = content.replace("生成测试用例", "").strip()
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            elif not self.prompt2:
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "请添加用例编写要求。"
                self.prompt2 = content.strip()
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                final_prompt = f"产品需求: {self.prompt1}, 用例编写要求: {self.prompt2}"
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = final_prompt
                e_context.action = EventAction.BREAK_PASS
                # 清空 prompts
                self.prompt1 = None
                self.prompt2 = None

    def get_help_text(self, **kwargs):
        help_text = "输入'生成测试用例'，我会引导你添加产品需求和用例编写要求，然后生成测试用例。"
        return help_text

    def _load_config_template(self):
        logger.debug("No TestCaseGenerator plugin config.json, use plugins/testcasegenerator/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)
            # 这里记录加载配置时的异常情况
            logger.warning("Failed to load plugin configuration.")
        return None  # 返回空配置以防止后续操作出现错误
