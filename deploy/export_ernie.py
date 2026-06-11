"""Export PaddleNLP sentiment model properly."""
import os
import paddle
from paddlenlp import Taskflow

CACHE_DIR = os.path.expanduser('~/.paddlenlp/taskflow/sentiment_analysis/bilstm')
STATIC_DIR = os.path.join(CACHE_DIR, 'static')

if os.path.exists(os.path.join(STATIC_DIR, 'inference.pdmodel')):
    print('Inference model already exists, skipping export')
else:
    print('Creating Taskflow instance...', flush=True)
    model = Taskflow('sentiment_analysis', batch_size=1)

    print('Triggering model load...', flush=True)
    # Try to do warm-up; ignore errors
    try:
        result = model('test')
        print(f'Warm-up OK: {result}', flush=True)
    except Exception as e:
        print(f'Warm-up error (expected): {e}', flush=True)

    # Check if inference model was created
    if os.path.exists(os.path.join(STATIC_DIR, 'inference.pdmodel')):
        print('Inference model exported successfully!', flush=True)
    else:
        # Try manual save
        print('Attempting manual save...', flush=True)
        from paddlenlp.transformers import AutoModelForSequenceClassification, AutoTokenizer
        model_name = 'bilstm'
        model_path = CACHE_DIR

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSequenceClassification.from_pretrained(model_path, from_hf_hub=False)

        # Save to inference format
        model.eval()
        input_spec = [paddle.static.InputSpec(shape=[None, None], dtype='int64', name='input_ids')]
        paddle.jit.save(model, os.path.join(STATIC_DIR, 'inference'), input_spec=input_spec)
        print('Manual save done!', flush=True)
