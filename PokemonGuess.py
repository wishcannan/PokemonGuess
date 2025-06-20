import json
import socketio
import requests
import random
import string
import time
import logging
import threading
from urllib.parse import urlencode
from typing import Dict, Optional


# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("PokemonDuelClient")

class PokemonDuelClient:
    def __init__(self):
        self.sio = socketio.Client(
            reconnection=False,
            # logger=True,
            # engineio_logger=True
            logger=False,          # 关闭Socket.IO的日志
            engineio_logger=False  # 关闭Engine.IO的日志
        )
        self.session = requests.Session()
        self.sid = None
        self.ping_interval = None
        self.ping_timeout = None
        self.last_ping = None
        self.connected_event = threading.Event()  # 连接状态事件
        
        # 注册事件处理器
        self.sio.on('connect', self._on_connect)
        self.sio.on('disconnect', self._on_disconnect)
        self.sio.on('join_event', self._on_join_event)
        self.sio.on('setting_event',self._on_setting_event)#同步一下设置
        self.sio.on('start_guess', self._on_game_start)
        self.sio.on('answer_result',self._on_answer_result)#答案结果
        self.sio.on('leave_event',self._on_leave_event)


    def connect(self, mode: str, username: str, room_id: Optional[str] = None):
        """
        完整实现Socket.IO握手协议
        """
        self.mode = mode
        self.username = username
        self.room_id = room_id or self._generate_room_id()
        
        # 第一步：初始轮询请求
        self._initial_polling_request()
        
        # 第二步：在后台线程中建立WebSocket连接
        self._start_websocket_thread()
        
        # 第三步：等待连接建立后发送加入请求
        self._send_join_request_after_connect()

    def _initial_polling_request(self):
        """第一步：初始轮询请求（获取SID和配置）"""
        params = {
            'EIO': '4',
            'transport': 'polling',
            't': self._generate_vue_token()
        }
        
        url = f"http://1.14.255.210:9000/socket.io/?{urlencode(params)}"
        logger.debug(f"步骤1: 发送初始轮询请求 -> {url}")
        
        response = self.session.get(url)
        if response.status_code != 200:
            raise ConnectionError(f"初始轮询失败: HTTP {response.status_code}")
        
        # 解析响应 (格式: '0{"sid":"...","upgrades":[],"pingInterval":25000,"pingTimeout":5000}')
        if not response.text.startswith('0'):
            raise ValueError("无效的握手响应格式")
        
        config = eval(response.text[1:])  # 安全解析JSON
        self.sid = config['sid']
        self.ping_interval = config['pingInterval'] / 1000  # 毫秒转秒
        self.ping_timeout = config['pingTimeout'] / 1000
        
        logger.debug(f"步骤1完成: SID={self.sid}, ping_interval={self.ping_interval}s, ping_timeout={self.ping_timeout}s")
        
        # 发送第二轮轮询请求
        params = {
            'EIO': '4',
            'transport': 'polling',
            'sid': self.sid,
            't': self._generate_vue_token()
        }
        url = f"http://1.14.255.210:9000/socket.io/?{urlencode(params)}"
        logger.debug(f"步骤2: 发送第二轮轮询请求 -> {url}")
        response = self.session.post(url, data='40')
        if response.status_code != 200:
            raise ConnectionError(f"第二轮轮询失败: HTTP {response.status_code}")
        
        if response.text != 'OK':
            logger.warning(f"非预期响应: {response.text}")
        else:
            logger.debug("第二轮轮询成功: 收到 'OK'")

    def _start_websocket_thread(self):
        """在后台线程中建立WebSocket连接"""
        def connect_thread():
            try:
                self._connect_websocket()
            except Exception as e:
                logger.error(f"WebSocket连接失败: {str(e)}")
        
        threading.Thread(target=connect_thread, daemon=True).start()

    def _connect_websocket(self):
        """建立WebSocket连接"""
        params = {
            'EIO': '4',
            'transport': 'websocket',
            'sid': self.sid,
        }
        
        logger.debug("步骤3: 建立WebSocket连接")
        self.sio.connect(
            "http://1.14.255.210:9000",
            transports=['websocket'],
            socketio_path='/socket.io/',
            namespaces=['/']
        )
        
        # 记录最后ping时间
        self.last_ping = time.time()
        logger.debug("步骤3完成: WebSocket连接已建立")
        
        # 启动心跳检测
        self._start_heartbeat()
        
        # 等待并处理事件
        self.sio.wait()

    def _send_join_request_after_connect(self):
        """等待连接建立后发送加入请求"""
        # 等待连接建立（最多10秒）
        if not self.connected_event.wait(10):
            raise TimeoutError("等待WebSocket连接超时")
        
        logger.debug("连接已确认，发送加入请求")
        
        # 构造符合协议的载荷
        join_payload = {
            'username': self.username,
            'room': self.room_id,
            'action': 'init' if self.mode == 'host' else 'join',
        }
        
        if self.mode == 'host':
            join_payload.update({
                'hardid': '普通模式',
                'selectedGens': [True] * 9,#世代选择
                'battleOpen': False,
                'shapeOpen': False,
                'catchOpen': False,
                'showGenArrow': False,
                'cheatOpen': False,      # 新增参数
                'reverseDisplay': True,  # 新增参数
                'maxGuess': 4            # 猜测次数
            })
        
        # 发送加入请求
        self.sio.emit('join', join_payload)
        logger.debug(f"已发送join事件: {join_payload}")

    def _on_connect(self):
        """连接成功回调"""
        logger.warning("✓ WebSocket连接成功")
        
        # 设置连接事件，允许发送加入请求
        self.connected_event.set()

    def _start_heartbeat(self):
        """启动心跳检测线程"""
        def heartbeat():
            while self.sio.connected:
                # 检查是否需要发送ping
                if time.time() - self.last_ping > self.ping_interval:
                    try:
                        self.sio.eio.send('2')  # 发送ping
                        self.last_ping = time.time()
                        logger.debug("发送ping")
                    except Exception as e:
                        logger.error(f"发送ping失败: {str(e)}")
                        break
                
                time.sleep(1)
        
        threading.Thread(target=heartbeat, daemon=True).start()

    def _on_disconnect(self):
        """连接断开回调"""
        logger.warning("✗ 连接已断开")
        self.connected_event.clear()  # 重置连接状态

    def _on_join_event(self, data):
        """处理加入事件"""
        event_type = data.get('message')
        
        if event_type == 'host':
            # logger.info(f"🎮 你已成为房主 | 房间号: {data['room']}")
            print(f"🎮 你已成为房主 | 房间号: {data['room']}")
            self.room_id = data['room']  # 更新为服务器分配的房间号
            # logger.info(f"  分享房间号: {self.room_id}")
            print(f"  分享房间号: {self.room_id}")
            
        elif event_type == 'join':
            username = data.get('username')
            
            if username == self.username:
                # logger.info(f"✅ 加入成功 | 房主: {data.get('hostname')}")
                print(f"✅ 加入成功 | 房主: {data.get('hostname')}")
                # logger.info(f"  房间号: {data['room']}")
                print(f"  房间号: {data['room']}")
            else:
                # logger.info(f"👥 玩家 {username} 加入了房间")
                print(f"👥 玩家 {username} 加入了房间")
                #主动调用room_game_init
                time.sleep(5)
                self._play_room_game()

    def _play_room_game(self):
        """开始游戏 据我分析可以强行撬动游戏开始按钮 后端没有做验证"""
        # time.wait(1)
        #gen = 10 + [True]*9 对应的index 将 i << index位 这样第一代就是1 第9带就是1 * 2^8
        self.sio.emit("room_game_init", {
            "difficulty": 0,#普通模式0 or 简单模式!0
            "gen": 521,#9代全选就是521=10 + 0b111111111 顺便吐槽后端 10加的莫名奇妙 是不是为了凑521啊 检查怎么会检查<=9啊
            "room": self.room_id,
        })
        logger.info(f"已发送开始事件: {self.room_id}")

    def _submit_answer(self):
        """提交答案"""
        url = f'http://1.14.255.210:9000/getanswerDual?room={self.room_id}'
        response = requests.get(url)
        if response.status_code==200:
            data = response.json()
            self.sio.emit("submit_answer", {
                "username":self.username,
                "data": self._create_ans(data),
                "room": self.room_id,
            })
            logger.info(f"已发送答案事件: {self.room_id}")

    def _create_ans(self,temp:json):
        #用于生成答案
        ans = {
            "name": temp["name"],
            "answer": temp["answer"],
            "type": [],
            "pow": {},
            "speed": {},
            "attack": {},
            "defense": {},
            "gen": {},
            "ability": [],
            "evo": {},
            "stage": {},
            "egg": [],
            "catrate": {},
            "shape": {},
            "col": {},
            "label": []
        }
        #是不是很多都可以写死啊 毕竟我100%对
        # 处理属性
        for type_info in temp["type"]:
            if type_info["key"] != "无":
                col = "success" if type_info["value"] == "True" else "info"
                ans["type"].append({"key": type_info["key"], "col": col})
        # 处理种族值
        ans["pow"] = {
            "key": temp["pow"]["key"],
            "value": temp["pow"]["value"],
            "col": "success" if temp["pow"]["value"] == "equiv" 
                else "info" if temp["pow"]["dis"] == "far" 
                else "warning"#dis表示是否接近
        }
        # 处理速度
        ans["speed"] = {
            "key": temp["speed"]["key"],
            "value": temp["speed"]["value"],
            "col": "success" if temp["speed"]["value"] == "equiv" 
                else "info" if temp["speed"]["dis"] == "far" 
                else "warning"
        }
        # 处理攻击防御
        ans["attack"] = {
            "key": temp["attack"]["key"],
            "value": temp["attack"]["value"],
            "col": "success" if temp["attack"]["value"] == "True" else "info"
        }
        ans["defense"] = {
            "key": temp["defense"]["key"],
            "value": temp["defense"]["value"],
            "col": "success" if temp["defense"]["value"] == "True" else "info"
        }
        # 处理世代
        ans["gen"] = {
            "key": temp["gen"]["key"],
            "value": temp["gen"]["value"],
            "col": "success" if temp["gen"]["value"] == "equiv" 
                else "info" if temp["gen"]["dis"] == "far" 
                else "warning"
        }
        # 处理特性
        for ability in temp["ability"]:
            col = "success" if ability["value"] == "True" else "info"
            ans["ability"].append({"key": ability["key"], "col": col})
        # 处理进化
        ans["evo"] = {
            "key": temp["evo"]["key"],
            "col": "success" if temp["evo"]["value"] == "equiv" 
                else "info" if temp["evo"]["value"] == "far" 
                else "warning"
        }
        if ans["evo"]["key"] is not None:
            # ans["evo"]["key"] = truncate_string(ans["evo"]["key"], 6 if is_mobile else 12)
            #拒绝兼容手机 ans由一个客户端生成 要另一个客户端适用也太难受了吧
            ans["evo"]["key"] = self._truncate_string(ans["evo"]["key"], 6)

        ans["stage"] = {
            "key": temp["stage"]["key"],
            "value": temp["stage"]["value"],
            "col": "success" if temp["stage"]["value"] == "True" else "info"
        }
        # 处理蛋组
        for egg in temp["egg"]:
            col = "success" if egg["value"] == "True" else "info"
            ans["egg"].append({"key": egg["key"], "col": col})
        # 处理捕获率
        ans["catrate"] = {
            "key": temp["catrate"]["key"],
            "value": temp["catrate"]["value"],
            "col": "success" if temp["catrate"]["value"] == "equiv" else "info"
        }
        # 处理外形
        ans["shape"] = {
            "key": temp["shape"]["key"],
            "value": temp["shape"]["value"],
            "col": "success" if temp["shape"]["value"] == "True" else "info"
        }
        # 处理颜色
        ans["col"] = {
            "key": temp["col"]["key"],
            "value": temp["col"]["value"],
            "col": "success" if temp["col"]["value"] == "equiv" else "info"
        }
        # 处理标签
        for label in temp["label"]:
            if label["value"] == "True":
                col = "success"
            elif label.get("similarity") == "similar":
                col = "warning"
            else:
                col = "info"
            ans["label"].append({"key": label["key"], "col": col})
        return ans





    def _on_setting_event(self,data):
        """处理同步设置"""
        # logger.info(f'同步设置:{data}')
        #原则上没什么好打印的
        pass


    def _on_game_start(self, data):
        """处理游戏开始事件"""
        logger.warning("\n★ 游戏开始! ★")
        if data.get('message') == 'success':
            # logger.info("双方玩家已准备就绪")
            print("双方玩家已准备就绪")
        time.sleep(2)
        self._submit_answer()

    def _on_answer_result(self,data):
        """处理玩家发的答案"""
        logger.warning(f'玩家{data["username"]}回答了{data["result"]["name"]}---{data['result']['answer']}')
        if self.mode == 'host':
            time.sleep(5)
            self._play_room_game()

    def _on_leave_event(self,data):
        """处理有人离开"""
        logger.warning("\n★ 游戏结束! ★")
        logger.warning(f"玩家 {data['username']} 离开了房间")

        self.sio.disconnect()
        logger.warning("客户端已退出")
        # sys.exit(0)


    # 工具方法
    @staticmethod
    def _generate_vue_token() -> str:
        """生成与Vue客户端相同的8位随机token（如：9vvdggyp）"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    @staticmethod
    def _generate_room_id() -> str:
        """生成房间号（格式：XXXX-XXXX-XXXX）"""
        return f"{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

    @staticmethod
    def _truncate_string(s: str, max_length: int) -> str:
        """截断字符串并在末尾添加省略号"""
        if len(s) > max_length:
            return s[:max_length] + '...'
        return s



    def wait(self):
        """保持主线程运行"""
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.sio.disconnect()
            logger.warning("客户端已退出")

if __name__ == "__main__":
    client = PokemonDuelClient()
    #访问http://1.14.255.210:888/#/dualCreate 开始双人游戏 host是主机模式 join是客户端b模式 
    #主机模式
    client.connect(
        mode='host',
        username='图图犬',#名字一定要是宝可梦名字
    )
    # join模式
    # client.connect(
    #     mode='join',
    #     username='图图犬',
    #     room_id="7443-6706-1223"
    # )


    client.wait()