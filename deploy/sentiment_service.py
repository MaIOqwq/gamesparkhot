import logging
from flask import Flask, request, jsonify
from paddlenlp import Taskflow

app = Flask(__name__)

_sentiment_pipeline = None

def get_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        logging.info("Loading ERNIE 3.0 Tiny sentiment model...")
        _sentiment_pipeline = Taskflow('sentiment_analysis')
        logging.info("Model loaded")
    return _sentiment_pipeline

@app.route('/sentiment', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing text'}), 400

        text = data['text'].strip()
        if not text:
            return jsonify({'error': 'Empty text'}), 400

        if len(text) > 200:
            text = text[:200]

        pipe = get_pipeline()
        result = pipe(text)
        item = result[0]
        label = item['label']
        score = item['score']

        if label == 'positive':
            sentiment_score = score
        else:
            sentiment_score = -score

        return jsonify({
            'label': label,
            'confidence': score,
            'sentiment_score': sentiment_score,
            'text': text
        })
    except Exception as e:
        logging.error(f"Prediction error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=False, threaded=False)
