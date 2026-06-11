# -*- coding: utf-8 -*-
"""
情感分析服务（ERNIE 3.0 Tiny）
替代 ModelScope StructBERT，更小更快

安装：
  pip install paddlepaddle paddlenlp

运行：
  python sentiment_service_ernie.py          # 8001 端口（与 Spark 配置一致）
  python sentiment_service_ernie.py --port 8002

API：
  POST /sentiment  {"text": "今天天气真好"}
  GET  /health     {"status": "ok"}
"""

import argparse
import logging
import time

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
_model = None  # lazy load


def load_model():
    global _model
    if _model is not None:
        return _model
    logger.info("Loading PaddleNLP sentiment model (SKEP/ERNIE)...")
    from paddlenlp import Taskflow
    # 使用百度SKEP情感分析模型，中文社交媒体场景表现优秀
    # 模型大小约 200MB，CPU 推理约 50-100ms/条
    _model = Taskflow(
        "sentiment_analysis"
    )
    logger.info("PaddleNLP sentiment model loaded")
    return _model


@app.route('/sentiment', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing text'}), 400

        text = data['text'].strip()
        if not text:
            return jsonify({'error': 'Empty text'}), 400

        # 截断输入
        if len(text) > 512:
            text = text[:512]

        start = time.time()
        model = load_model()
        result = model(text)
        elapsed = time.time() - start

        # 解析结果
        # uie-senta-base 返回 [{"text": "...", "predictions": [{"label": "positive", "score": 0.99}]}]
        if result and len(result) > 0:
            pred = result[0]
            if isinstance(pred, dict) and 'predictions' in pred:
                predictions = pred['predictions']
                if len(predictions) > 0:
                    top = predictions[0]
                    label = top.get('label', 'neutral')
                    score = float(top.get('score', 0.5))
                else:
                    label = 'neutral'
                    score = 0.5
            elif isinstance(pred, dict) and 'label' in pred:
                label = pred['label']
                score = float(pred.get('score', 0.5))
            else:
                label = 'neutral'
                score = 0.5
        else:
            label = 'neutral'
            score = 0.5

        # 映射为 -1 ~ 1 的情感得分
        if label in ('positive', 'POSITIVE', '正面'):
            sentiment_score = score
        elif label in ('negative', 'NEGATIVE', '负面'):
            sentiment_score = -score
        else:
            sentiment_score = 0.0

        logger.debug(f"分析完成: text_len={len(text)}, label={label}, score={score:.3f}, time={elapsed:.3f}s")

        return jsonify({
            'label': label,
            'confidence': score,
            'sentiment_score': sentiment_score,
            'text': text[:100],
        })
    except Exception as e:
        logger.error(f"分析出错: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    # 预加载模型
    logger.info("预加载模型...")
    load_model()
    logger.info(f"启动服务端口 {args.port}")

    app.run(host='0.0.0.0', port=args.port, debug=args.debug)
