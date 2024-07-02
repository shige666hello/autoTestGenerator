"""
LinkAI client

@author LinkAI
@Date 2023/12/31
"""

import socket
import json
import threading
from enum import Enum
from linkai._common.log import logger
import time
import os
import re


class ClientMsgType(Enum):
    LOGIN = "LOGIN"
    CONFIG = "CONFIG"
    PUSH = "PUSH"
    HEARTBEAT = "HEARTBEAT"
    CHANNEL_LOGIN = "CHANNEL_LOGIN"
    CHANNEL_LOGOUT = "CHANNEL_LOGOUT"
    CHANNEL_QRCODE = "CHANNEL_QRCODE"
    LOCAL_CONFIG = "LOCAL_CONFIG"

    def __str__(self):
        return self.name


class PushMsg:
    def __init__(self, session_id: str, msg_content: str, is_group: bool = False):
        self.session_id = session_id
        self.msg_content = msg_content
        self.is_group = is_group


CLIENT_CONFIG_FILE = 'client_config.json'
CLIENT_ID_KEY = "client_id"
DEFAULT_HOST = "client.link-ai.tech"


class LinkAIClient:
    def __init__(self, api_key: str, host: str = "", client_type: str = "", heartbeat_interval=30, reconnect_times=2, reconnect_interval=10):
        self.client_id = self.fetch_client_id()
        self.client_type = client_type
        self.api_key = api_key
        self.host = host or DEFAULT_HOST
        self.check_host()
        self.port = 7071
        self.socket = None
        self.connected = False
        self.connect_failed_times = 0
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_times = reconnect_times
        self.reconnect_interval = reconnect_interval
        self.need_connect = True
        self.config = {}

    def on_message(self, push_msg: PushMsg):
        """
        client push msg callback
        :param push_msg: manual push msg
        :return:
        """
        raise NotImplementedError("Please implement the on_message method.")

    def on_config(self, config: dict):
        """
        client config refresh
        :param config: client config data
        :return:
        """
        pass

    def start(self):
        """
        client startup
        """
        try:
            self._connect()
            threading.Thread(target=self._receive_messages).start()
            threading.Thread(target=self._send_heartbeat).start()
        except socket.error as e:
            logger.error(f"Unable to connect to the server: {e}")

    @staticmethod
    def fetch_client_id():
        if os.path.exists(CLIENT_CONFIG_FILE):
            with open(CLIENT_CONFIG_FILE, 'r') as file:
                client_config = json.load(file)
                if client_config:
                    return client_config.get(CLIENT_ID_KEY)
        return None

    @staticmethod
    def save_client_id(client_id: str):
        data = {
            CLIENT_ID_KEY: client_id
        }
        with open(CLIENT_CONFIG_FILE, 'w') as file:
            json.dump(data, file, indent=4)

    def _connect(self):
        if not self.need_connect:
            return
        attempts = 0
        while attempts < self.reconnect_times and not self.connected and self.need_connect:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.host, self.port))
                self.connected = True
                self._send_login()
                self.connect_failed_times = 0
            except socket.error as e:
                # logger.warn(f"Connection failed: {e}")
                attempts += 1
                self.connect_failed_times += 1
                time.sleep(self.reconnect_interval)
        if not self.connected:
            logger.warn("Could not connect to server after several attempts")

    def _send_login(self):
        login_data = {
            "apiKey": self.api_key,
            "clientType": self.client_type
        }
        if self.client_id:
            login_data["clientId"] = self.client_id
        login_msg = {
            "type": ClientMsgType.LOGIN.name,
            "data": login_data
        }
        message = json.dumps(login_msg) + "\r\n"
        self.socket.sendall(message.encode('utf-8'))

    def send_login_success(self):
        if self.client_id:
            msg = self._build_package(ClientMsgType.CHANNEL_LOGIN)
            self._send_package(msg)

    def send_logout(self):
        if self.client_id:
            msg = self._build_package(ClientMsgType.CHANNEL_LOGOUT)
            self._send_package(msg)

    def send_qrcode(self, urls: list):
        if self.client_id:
            msg = self._build_package(ClientMsgType.CHANNEL_QRCODE)
            msg["data"]["qrcodeUrls"] = urls
            self._send_package(msg)

    def _send_local_config(self):
        if self.client_id and self.config:
            msg = self._build_package(ClientMsgType.LOCAL_CONFIG)
            msg["data"]["config"] = self.config
            self._send_package(msg)

    def _build_package(self, msg_type: ClientMsgType):
        data = {
            "apiKey": self.api_key,
            "clientType": self.client_type,
            "clientId": self.client_id
        }
        msg = {
            "type": msg_type.name,
            "data": data
        }
        return msg

    def _send_package(self, msg):
        message = json.dumps(msg) + "\r\n"
        self.socket.sendall(message.encode('utf-8'))


    def _send_heartbeat(self):
        while True:
            if not self.need_connect:
                break
            if self.connected:
                if not self.client_id:
                    continue
                try:
                    heart_beat = {
                        "type": ClientMsgType.HEARTBEAT.name,
                        "data": {
                            "clientId": self.client_id
                        }
                    }
                    message = json.dumps(heart_beat) + "\r\n"
                    self.socket.sendall(message.encode('utf-8'))
                    # logger.debug("[Client] send heartbeat")
                except socket.error:
                    self.connected = False
            time.sleep(self.heartbeat_interval)
            if not self.connected:
                # logger.debug("Heartbeat try to reconnect...")
                self._connect()
            if self.connect_failed_times > 120:
                break

    def _receive_messages(self):
        while True:
            try:
                message = self.socket.recv(4096)
                if message:
                    self._msg_handler(message)
                    time.sleep(0.01)
                else:
                    self.connected = False
            except ConnectionResetError:
                # 如果服务端关闭了连接，会抛出 ConnectionResetError 异常
                self.connected = False
                # logger.debug("Server closed the connection.")
            except socket.error as e:
                self.connected = False
                # logger.debug("Server closed the connection.")
            except Exception as e:
                time.sleep(1)
                # 其他错误处理
                logger.warn(f"An error occurred: {e}")

            if not self.need_connect or self.connect_failed_times > 120:
                break

            if not self.connected:
                self._connect()
                time.sleep(1)

    def _msg_handler(self, message):
        msg_str = message.decode('utf-8').strip("\x00")
        msg_str = msg_str.split("\0")[0]
        msg = json.loads(msg_str)

        if msg.get("type") == ClientMsgType.PUSH.name:
            data = msg.get("data")
            session_id = data.get("sessionId")
            msg = data.get("msgContent")
            is_group = data.get("inGroup")
            msg = PushMsg(session_id=session_id, msg_content=msg, is_group=is_group)
            logger.debug(f"Received message: {msg}, session_id={session_id}")  # 打印接收到的消息
            self.on_message(msg)

        elif msg.get("type") == ClientMsgType.LOGIN.name:
            if msg.get("code") == 200:
                if not self.client_id:
                    client_id = msg.get("data").get("clientId")
                    self.client_id = client_id
                    self.save_client_id(client_id)
                config = msg.get("data").get("config")
                if config:
                    self.on_config(config)
                else:
                    self._send_local_config()
                logger.info(f"Client login success, client_id={self.client_id}")
            elif msg.get("code") == 409:
                logger.info(f"Client no need connect, ignore")
                self.need_connect = False
                self.socket.close()
            else:
                logger.warn(f"Client login failed, res={msg}")

        elif msg.get("type") == ClientMsgType.CONFIG.name:
            data = msg.get("data")
            logger.debug(f"Received config refresh: {msg}")  # 打印接收到的消息
            del data["channelId"]
            self.on_config(data)

    def check_host(self):
        pattern = re.compile(r'^(.*\.)?(link-ai\.tech|link-ai\.chat|link-ai\.pro|link-ai\.cloud)$')
        if not bool(pattern.match(self.host)):
            raise RuntimeError("Can not connect")
