"""
智慧交通詢問聊天機器人 - LINE Messaging API 版本
Smart Transit Inquiry Chatbot - LINE Messaging API Version

作者 / Author: Chiu-Hung SU
機構 / Affiliation: NTUST Department of Information Management
"""

import os
import json
import math
import jieba
import logging
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# ── 初始化 Flask ──────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── LINE API 設定（從環境變數讀取，不要寫死在程式裡）──────────
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ── 停用詞 ────────────────────────────────────────────────────
STOPWORDS = set([
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
    "一", "個", "上", "也", "很", "到", "說", "要", "去", "你", "會",
    "看", "好", "沒", "她", "他", "如", "請問", "想", "知道", "什麼",
    "可以", "嗎", "呢", "嗯", "那", "這", "嗎", "請", "幫", "告訴"
])

# ── 知識庫 ────────────────────────────────────────────────────
KNOWLEDGE_BASE = [
    {
        "category": "票價資訊",
        "keywords": ["票價", "費用", "悠遊卡", "月票", "單程", "優惠", "折扣",
                     "付款", "價格", "多少錢", "學生票", "敬老票", "一日票",
                     "定期票", "計費", "刷卡"],
        "answer": (
            "🎫 捷運票價資訊：\n\n"
            "• 起跳價：20 元，最高 65 元（依距離計費）\n"
            "• 單程票：依里程計費\n"
            "• 悠遊卡：享 8 折優惠\n"
            "• 定期票（月票）：1,280 元，無限次搭乘\n"
            "• 65 歲以上長者：半價優惠\n\n"
            "建議使用悠遊卡，不僅享折扣，轉乘公車也可享優惠。"
        )
    },
    {
        "category": "路線查詢",
        "keywords": ["路線", "怎麼搭", "如何到", "怎麼去", "前往", "到達",
                     "台北車站", "忠孝復興", "捷運站", "換乘", "轉乘站",
                     "哪條線", "搭到", "幾號出口", "路線圖"],
        "answer": (
            "🗺️ 路線查詢建議：\n\n"
            "• 台北捷運共有 6 條路線（紅、藍、綠、橘、棕、環狀線）\n"
            "• 可於各站入口查看路線圖，或使用「台北捷運 Go」App\n"
            "• 跨線需在轉乘站換乘，主要轉乘站：\n"
            "  - 台北車站（紅線 × 藍線）\n"
            "  - 忠孝復興（藍線 × 棕線）\n"
            "  - 忠孝敦化（藍線 × 棕線）\n\n"
            "請問您要從哪一站到哪一站？"
        )
    },
    {
        "category": "班次時刻",
        "keywords": ["幾點", "幾分", "班次", "時刻", "首班車", "末班車",
                     "幾分鐘", "班距", "幾點開始", "幾點結束", "幾點營運",
                     "最晚", "最早", "時間"],
        "answer": (
            "🕐 班次時刻資訊：\n\n"
            "• 首班車：約 06:00（各站略有差異）\n"
            "• 末班車：約 24:00（各站略有差異）\n"
            "• 尖峰時段（07:30-09:00 / 17:30-19:30）：\n"
            "  班距約 3-4 分鐘\n"
            "• 離峰時段：班距約 6-8 分鐘\n"
            "• 週末與假日：班距略長，末班車時間相同\n\n"
            "建議出發前查詢「台北捷運 Go」App 確認最新時刻。"
        )
    },
    {
        "category": "轉乘資訊",
        "keywords": ["轉乘", "公車", "YouBike", "換搭", "接駁", "停車場",
                     "高鐵", "台鐵", "機場", "悠遊卡轉乘", "一小時優惠",
                     "腳踏車", "共乘"],
        "answer": (
            "🚌 轉乘資訊：\n\n"
            "• 捷運轉公車：使用悠遊卡，1 小時內享 8 元折扣\n"
            "• YouBike：各捷運站出口附近均設有租借站\n"
            "  - 前 30 分鐘免費（需辦理會員）\n"
            "• 台北車站可轉乘高鐵、台鐵、長途客運\n"
            "• 部分站設有 P+R 停車場，可先開車後搭捷運\n\n"
            "悠遊卡是最方便的轉乘工具，建議儲值後使用。"
        )
    },
    {
        "category": "無障礙設施",
        "keywords": ["無障礙", "電梯", "輪椅", "身障", "視障", "聽障",
                     "無障礙廁所", "無障礙閘口", "博愛座", "協助",
                     "行動不便", "長者", "嬰兒車"],
        "answer": (
            "♿ 無障礙設施資訊：\n\n"
            "• 各站均設有無障礙電梯（請認明 ♿ 標誌）\n"
            "• 輪椅使用者請走無障礙閘口，站務人員將協助\n"
            "• 月台與車廂間縫隙：部分站設有活動踏板補足\n"
            "• 視障人士：站內設有點字磚及語音廣播\n"
            "• 聽障人士：站內設有字幕顯示板\n"
            "• 無障礙廁所：各站均設有，位於閘門內側\n\n"
            "如需特別協助，請洽服務台，站務人員將全程陪同。"
        )
    },
    {
        "category": "站點設施",
        "keywords": ["廁所", "服務台", "超商", "置物箱", "失物", "ATM",
                     "哺乳室", "商店", "餐飲", "充電", "寵物", "行李",
                     "腳踏車", "設施"],
        "answer": (
            "🏢 站點設施查詢：\n\n"
            "• 各站均設有服務台，可協助乘客查詢資訊\n"
            "• 主要站點設有超商、餐飲等商業設施\n"
            "• 置物箱：24 小時可使用，費用 30-100 元/天\n"
            "• 失物招領：請洽服務台或撥打客服專線\n"
            "• 哺乳室：主要大站均設有，請洽服務台\n"
            "• 寵物：裝入寵物袋（籠）可攜帶上車\n\n"
            "各站設施略有不同，建議現場詢問站務人員。"
        )
    }
]

# 相似度閾值
THRESHOLD = 0.12

# ── 使用者回饋紀錄（存在記憶體，可改成資料庫）──────────────
feedback_log = []


def tokenize(text: str) -> list[str]:
    """中文斷詞 + 停用詞過濾"""
    tokens = list(jieba.cut(text, cut_all=False))
    return [t for t in tokens if t.strip() and t not in STOPWORDS and len(t) > 0]


def compute_tfidf_similarity(query_tokens: list[str], kb_keywords: list[str]) -> float:
    """計算 TF-IDF 加權餘弦相似度"""
    if not query_tokens or not kb_keywords:
        return 0.0

    # 建立詞彙表
    vocab = list(set(query_tokens + kb_keywords))
    if not vocab:
        return 0.0

    def tfidf_vector(tokens, vocab):
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) if tokens else 1
        vec = []
        for v in vocab:
            tf_val = tf.get(v, 0) / total
            idf_val = math.log(2 / (1 + (1 if v in tokens else 0)) + 1)
            vec.append(tf_val * idf_val)
        return vec

    v1 = tfidf_vector(query_tokens, vocab)
    v2 = tfidf_vector(kb_keywords, vocab)

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a ** 2 for a in v1))
    norm2 = math.sqrt(sum(b ** 2 for b in v2))

    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def find_best_match(query: str):
    """找出最佳匹配的知識庫條目"""
    tokens = tokenize(query)
    if not tokens:
        return None, 0.0

    best_score = 0.0
    best_entry = None

    for entry in KNOWLEDGE_BASE:
        score = compute_tfidf_similarity(tokens, entry["keywords"])
        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry, best_score


def log_interaction(user_id: str, query: str, response: str,
                    matched: bool, category: str, score: float):
    """記錄使用者互動（用於收集回饋數據）"""
    record = {
        "user_id": user_id,
        "query": query,
        "response_category": category,
        "matched": matched,
        "similarity_score": round(score, 4),
    }
    feedback_log.append(record)
    logger.info(f"Interaction logged: {record}")


def build_guided_prompt() -> str:
    """建立引導提示訊息"""
    return (
        "抱歉，我無法確定您的問題類別。請問您想了解的是：\n\n"
        "① 票價資訊　② 路線查詢　③ 班次時刻\n"
        "④ 轉乘資訊　⑤ 無障礙設施　⑥ 站點設施\n\n"
        "請選擇或重新輸入您的問題。"
    )


# ── Flask 路由 ────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health_check():
    """健康檢查端點（讓 Render 知道服務正常運作）"""
    return "Smart Transit Chatbot is running! 🚇", 200


@app.route("/callback", methods=["POST"])
def callback():
    """LINE Webhook 端點"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)

    return "OK"


@app.route("/feedback", methods=["GET"])
def get_feedback():
    """查看收集到的互動數據（研究用）"""
    total = len(feedback_log)
    matched = sum(1 for r in feedback_log if r["matched"])
    accuracy = round(matched / total * 100, 1) if total > 0 else 0

    summary = {
        "total_queries": total,
        "matched": matched,
        "unmatched": total - matched,
        "accuracy_percent": accuracy,
        "recent_10": feedback_log[-10:] if feedback_log else []
    }
    return json.dumps(summary, ensure_ascii=False, indent=2), 200, {
        "Content-Type": "application/json"
    }


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    """處理使用者文字訊息"""
    user_id = event.source.user_id
    query = event.message.text.strip()

    logger.info(f"Received from {user_id}: {query}")

    # 找最佳匹配
    best_entry, best_score = find_best_match(query)

    if best_entry and best_score >= THRESHOLD:
        reply_text = best_entry["answer"]
        category = best_entry["category"]
        matched = True
    else:
        reply_text = build_guided_prompt()
        category = "unmatched"
        matched = False

    # 記錄互動數據
    log_interaction(
        user_id=user_id,
        query=query,
        response=reply_text,
        matched=matched,
        category=category,
        score=best_score
    )

    # 回傳訊息
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
