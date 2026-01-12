from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv
import os
from datetime import datetime

# 初始化Flask应用
app = Flask(__name__)
# 加载环境变量（本地测试用，Vercel上用平台环境变量替代）
load_dotenv()

# 核心配置（从环境变量读取，避免硬编码）
COZE_PAT = os.getenv("COZE_PAT")
COZE_BOT_ID = os.getenv("COZE_BOT_ID")
COZE_API_URL = "https://api.coze.cn/v1/chat/completions"

# 跨域配置（允许插件端跨域调用）
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

# 核心中转接口（插件对接此接口）
@app.route("/api/relay", methods=["POST", "OPTIONS"])
def relay_data():
    # 处理OPTIONS预检请求
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200
    
    try:
        # 1. 接收插件传来的LinkedIn数据和用户ID
        data = request.get_json()
        plugin_data = data.get("pluginData")  # 插件采集的联系人全量文本
        user_id = data.get("userId")          # 终端用户唯一标识
        
        # 参数校验
        if not plugin_data or not user_id:
            return jsonify({
                "success": False,
                "message": "缺少pluginData或userId参数"
            }), 400
        
        print(f"✅ 收到插件数据（用户ID：{user_id}）：{plugin_data[:50]}...")

        # 2. 数据加工（添加外贸业务规则）
        processed_data = {
            "user_id": user_id,
            "query": f"分析该LinkedIn联系人与我的外贸业务（主营：女装外贸，目标市场：欧美，客户类型：批发商/零售商）的匹配度，输出：1.匹配评分（0-100分）2.核心匹配点3.不匹配点，格式清晰。联系人信息：{plugin_data}",
            "bot_id": COZE_BOT_ID,
            "stream": False  # 关闭流式响应，方便后端处理
        }

        # 3. 调用扣子LLM API
        print("🔄 调用扣子LLM API...")
        headers = {
            "Authorization": f"Bearer {COZE_PAT}",
            "Content-Type": "application/json"
        }
        # 调用API并处理超时
        coze_response = requests.post(
            COZE_API_URL,
            json=processed_data,
            headers=headers,
            timeout=30  # 超时时间30秒，适配Vercel函数限制
        )
        coze_response.raise_for_status()  # 触发HTTP错误（如401/500）
        llm_result = coze_response.json()["messages"][0]["content"]

        # 4. 返回结果给插件
        return jsonify({
            "success": True,
            "message": "信息中转完成",
            "data": {
                "matchingResult": llm_result,
                "userId": user_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }), 200

    # 异常处理（覆盖所有可能的错误）
    except requests.exceptions.RequestException as e:
        error_msg = f"LLM调用失败：{str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({
            "success": False,
            "message": "信息中转失败",
            "error": error_msg
        }), 500
    except Exception as e:
        error_msg = f"系统错误：{str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({
            "success": False,
            "message": "信息中转失败",
            "error": error_msg
        }), 500

# Vercel适配：启动逻辑（无需修改）
if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(debug=False, port=port)  # Vercel上必须关闭debug