# Pokémon Duel Client 🎮⚡

一个基于 Python 的宝可梦对战猜谜游戏客户端，通过 WebSocket 实现实时双人对战。

![Pokémon Logo](https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/25.png)  
*(示例：皮卡丘官方艺术图)*

## 功能特性 ✨

- 🏠 **创建/加入房间**：支持房主模式和加入模式
- 🔍 **实时对战**：通过 Socket.IO 实现猜谜对战
- 📊 **自动答题**：智能解析答案并提交
- ⏱️ **心跳检测**：自动维持连接稳定性
- 📝 **日志记录**：可配置的日志级别（WARNING+）

## 技术栈 🛠️

- Python 3.8+
- `socketio-client` - WebSocket 通信
- `requests` - HTTP 请求处理
- `logging` - 日志系统
- 多线程处理

## 快速开始 🚀

### 安装依赖
```bash
pip install python-socketio requests
```
###运行客户端
```bash
# 房主模式
python Pokemon.py
```
```bash
# 加入模式（需指定房间号）
python Pokemon.py --mode join --room 1234-5678-9012
```
###参数说明
参数|说明|示例值
----|---|---
mode|模式| (host/join)	host
room|房间号（加入时必需|4552-4256-9306
name|玩家名称|"皮卡丘"
##代码架构 🏗️
```
#python
PokemonDuelClient
├── __init__()          # 初始化客户端
├── connect()           # 连接服务器
├── _initial_polling()  # 握手协议
├── _play_room_game()   # 开始游戏逻辑
├── _submit_answer()    # 自动提交答案
└── _create_ans()       # 生成答案数据结构
```
##协议细节 📡
###连接流程
1. 发送轮询请求获取 SID
3. 建立 WebSocket 连接
5. 发送加入房间事件

###关键事件
事件名称|方向|说明
---|---|---
`join_event` | 服务器→客户端 | 房间状态更新
`start_guess`| 服务器→客户端 | 游戏开始
`answer_result`| 服务器→客户端|答案验证结果
##贡献指南 🤝
欢迎通过 Issue 或 PR 贡献代码！建议流程：

1. Fork 本项目

3. 创建特性分支 (git checkout -b feature/新功能)

5. 提交更改 (git commit -am '添加新功能')

7. 推送到分支 (git push origin feature/新功能)

9. 创建 Pull Request

##免责声明 ⚠️
本项目为学习用途，与 Pokémon Company 无关。遵守以下规则：

- 勿用于商业用途

- 遵守服务器使用政策

- 避免高频请求造成服务器压力

需要调整任何部分或添加更多细节请随时告诉我！