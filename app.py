"""
회의문서 자동 생성 AI - 백엔드 서버
Python Flask + Groq API
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os, json, hashlib
from datetime import datetime

app = Flask(__name__, static_folder='static')
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
USERS_FILE = 'users.json'

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'api_key_set': bool(GROQ_API_KEY), 'time': datetime.now().isoformat()})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user_id = data.get('id', '').strip()
    pw = data.get('pw', '').strip()
    if not user_id or not pw:
        return jsonify({'ok': False, 'msg': '아이디와 비밀번호를 입력해 주세요.'}), 400
    if len(user_id) < 2:
        return jsonify({'ok': False, 'msg': '아이디는 2자 이상 입력해 주세요.'}), 400
    if len(pw) < 2:
        return jsonify({'ok': False, 'msg': '비밀번호는 2자 이상 입력해 주세요.'}), 400
    users = load_users()
    pw_hashed = hash_pw(pw)
    if user_id not in users:
        users[user_id] = {'pw': pw_hashed, 'name': user_id, 'created': datetime.now().isoformat()}
        save_users(users)
        return jsonify({'ok': True, 'msg': '계정이 생성됐습니다.', 'new': True, 'name': user_id})
    elif users[user_id]['pw'] == pw_hashed:
        return jsonify({'ok': True, 'msg': '로그인 성공', 'new': False, 'name': users[user_id].get('name', user_id)})
    else:
        return jsonify({'ok': False, 'msg': '비밀번호가 올바르지 않습니다.'}), 401

@app.route('/api/ai', methods=['POST'])
def ai_polish():
    if not GROQ_API_KEY:
        return jsonify({'ok': False, 'msg': '서버에 API 키가 설정되지 않았습니다.'}), 500

    data = request.get_json()
    doc_type = data.get('doc_type', 'plan')
    raw_text = data.get('raw_text', '')
    if not raw_text:
        return jsonify({'ok': False, 'msg': '내용이 없습니다.'}), 400

    doc_name = '회의개최계획' if doc_type == 'plan' else '회의결과보고'

    prompt = (
        "당신은 대한민국 공공기관 및 단체의 공문서 작성 전문가입니다.\n"
        "아래 회의 메모를 바탕으로 " + doc_name + " 공문서를 전문적으로 작성해 주세요.\n\n"
        "[회의 메모]\n"
        + raw_text + "\n\n"
        "[핵심 작성 원칙 - 반드시 준수]\n"
        "1. 절대 원문을 그대로 복사하지 말 것\n"
        "2. 전문가가 직접 작성하듯 살을 붙이고 내용을 풍부하게 재창작\n"
        "3. 회의 맥락을 파악하여 일반적으로 포함되어야 할 내용을 스스로 추가\n"
        "4. 모든 문장은 명사형으로 마무리 (예: ~보고, ~논의, ~수립, ~도출)\n"
        "5. '~함', '~임', '~됨' 같은 서술형 절대 금지\n\n"
        "[항목별 작성 기준]\n"
        "- 제목: 기관/단체명 + 회의 성격 + 회의\n"
        "- 목적: 회의의 핵심 목적을 2~3줄로 구체적이고 풍부하게 작성\n"
        "- 주요내용: 각 항목마다 세부항목(subs) 2개 이상 포함, 구체적으로 작성\n"
        "  (입력에 없더라도 이 회의에서 당연히 다룰 내용을 전문가 판단으로 추가)\n"
        "- 행정사항: 날짜, 담당부서, 제출처 등 구체적 정보 포함\n"
        "- 소요예산: 항목명, 단가, 인원, 합계 계산식 포함\n\n"
        "반드시 아래 JSON만 반환 (마크다운 없이 순수 JSON):\n"
        "{\n"
        '  "title": "회의 제목",\n'
        '  "purpose": "목적 (명사형, 2~3줄 분량으로 구체적으로)",\n'
        '  "date_display": "\'26.6.21.(목) 형식",\n'
        '  "date_raw": "2026-06-21 형식 (YYYY-MM-DD)",\n'
        '  "time": "14:00~ 형식",\n'
        '  "place": "장소",\n'
        '  "attendees": "참석대상",\n'
        '  "attend_note": "비고 또는 빈문자열",\n'
        '  "content_items": [{"text": "주요내용 항목 (명사형)", "subs": ["세부항목1", "세부항목2"]}],\n'
        '  "result_items": ["회의결과 (결과보고만, 아니면 빈배열)"],\n'
        '  "admin_items": ["행정사항 (날짜·기관명 포함, 구체적)"],\n'
        '  "budget_type": "소요예산",\n'
        '  "budget_item": "예산항목명 또는 빈문자열",\n'
        '  "budget_unit": 0,\n'
        '  "budget_count": 0,\n'
        '  "budget_kor": "한글금액 또는 빈문자열",\n'
        '  "budget_subject": "예산과목 또는 빈문자열",\n'
        '  "attach_items": ["붙임 항목 또는 빈배열"]\n'
        "}"
    )

    try:
        print(f"[AI] Groq 호출, 키: {GROQ_API_KEY[:8]}...")
        res = requests.post(
            GROQ_URL,
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.3,
                'max_tokens': 4000,
                'response_format': {'type': 'json_object'}
            },
            timeout=30
        )
        print(f"[AI] 응답 코드: {res.status_code}")

        if not res.ok:
            print(f"[AI] 오류: {res.text[:200]}")
            return jsonify({'ok': False, 'msg': f'AI 오류: {res.status_code}'}), 500

        result = res.json()
        text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print(f"[AI] 응답 앞부분: {text[:200]}")

        if not text:
            return jsonify({'ok': False, 'msg': 'AI 응답이 비어있습니다.'}), 500

        clean = text.strip()
        if '```json' in clean:
            clean = clean.split('```json')[1].split('```')[0].strip()
        elif '```' in clean:
            clean = clean.split('```')[1].split('```')[0].strip()
        start = clean.find('{')
        end = clean.rfind('}')
        if start >= 0 and end >= 0:
            clean = clean[start:end+1]

        parsed = json.loads(clean)
        print(f"[AI] 파싱 성공: title={parsed.get('title','')}")
        return jsonify({'ok': True, 'data': parsed})

    except json.JSONDecodeError as e:
        print(f"[AI] JSON 파싱 오류: {e}")
        return jsonify({'ok': False, 'msg': 'AI 응답 파싱 오류. 다시 시도해 주세요.'}), 500
    except requests.Timeout:
        return jsonify({'ok': False, 'msg': '응답 시간 초과. 다시 시도해 주세요.'}), 504
    except Exception as e:
        print(f"[AI] 오류: {type(e).__name__}: {str(e)}")
        return jsonify({'ok': False, 'msg': f'서버 오류: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
