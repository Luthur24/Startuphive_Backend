# ═══════════════════════════════════════════════════════════════
# SERVER.PY — Treℵds Flask Backend
# ═══════════════════════════════════════════════════════════════

from flask import Flask, request, jsonify
from flask_cors import CORS
import Modules as M

app = Flask(__name__)
CORS(app, origins="*")

@app.route('/', methods=['POST'])
def handle():
    try:
        x     = request.get_json(force=True)
        token = None
        auth  = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
        #result = M.Frontend_request_executor(x, token)
        return jsonify(9)
    except Exception as e:
        return jsonify({'status': 500, 'message': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 200, 'message': 'Treℵds backend is live.'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
