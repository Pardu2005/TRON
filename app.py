import os
import logging
import logging.handlers
from groq import Groq
from dataclasses import dataclass
import sys
import re
import time
import csv
import threading
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import json
from datetime import datetime

# Import features
from features import doubt_solver, quiz_generator, code_debugger, resume_analyzer

# Configure logging with rotation
log_handler = logging.handlers.RotatingFileHandler('tron_server.log', maxBytes=10_000_000, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[log_handler, logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# =====================================================
# 🔑 API KEY CONFIGURATION
# Paste your Groq API key below (get it from https://console.groq.com)
# =====================================================
GROQ_API_KEY = "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"   # <-- PASTE YOUR GROQ API KEY HERE e.g. "gsk_xxxxxxxxxxxx"

# Falls back to environment variable if the field above is left empty
if not GROQ_API_KEY:
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY is not set. Paste your key in the field above.")

HISTORY_FILE = "tron_history.csv"
MAX_HISTORY_ENTRIES = 1000
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder='.')
CORS(app, origins=["*"])
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}


class MockTkinter:
    def __init__(self, *args, **kwargs): pass
    def __getattr__(self, name): return MockTkinter()
    def __call__(self, *args, **kwargs): return MockTkinter()


def setup_mock_tkinter():
    mock_tk = MockTkinter()
    mock_tk.Tk = MockTkinter
    mock_tk.filedialog = MockTkinter()
    mock_tk.filedialog.askopenfilename = lambda **kwargs: None
    mock_tk.messagebox = MockTkinter()
    for mod in ['tkinter','tkinter.filedialog','tkinter.messagebox','tkinter.ttk','tkinter.font','tkinter.constants','_tkinter']:
        sys.modules[mod] = mock_tk
    logger.info("Tkinter mocked for web deployment")

setup_mock_tkinter()


@dataclass
class Config:
    input_mode: str = "text"
    max_retries: int = 3
    retry_delay: int = 2

    def __post_init__(self):
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is required. Set it as an environment variable.")
        try:
            Groq(api_key=GROQ_API_KEY)
            logger.info("Groq AI configured successfully")
        except Exception as e:
            logger.warning(f"Groq API configuration failed: {e}")
            raise


class AudioHandler:
    def __init__(self, config: Config):
        self.config = config
        self.audio_available = False
        logger.info("Audio features delegated to frontend")

    def speak(self, text): return "Speech handled by frontend"
    def stop_speech(self): return "Stop speech handled by frontend"
    def listen(self): return None


class ResponseHandler:
    def __init__(self):
        try:
            self.client = Groq(api_key=GROQ_API_KEY)
            self.history = []
            self.model = True
            self.chat = self
            logger.info("Groq model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Groq model: {e}", exc_info=True)
            self.client = None
            self.model = None
            self.chat = None

    def send_message(self, prompt):
        self._last_response = self.get_response(prompt)
        return self

    @property
    def text(self):
        return getattr(self, '_last_response', '')

    def get_response(self, prompt):
        if not self.client:
            return "Error: AI service unavailable. Please check configuration."

        for attempt in range(3):
            try:
                if attempt > 0:
                    time.sleep(2 * attempt)

                self.history.append({"role": "user", "content": prompt})
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=self.history,
                    max_tokens=1000,
                    temperature=0.7,
                )
                response_text = response.choices[0].message.content.strip()
                self.history.append({"role": "assistant", "content": response_text})
                if len(self.history) > 20:
                    self.history = self.history[-20:]
                return response_text or "No meaningful response generated."

            except Exception as e:
                error_message = str(e).lower()
                if 'quota' in error_message or 'rate' in error_message or 'limit' in error_message:
                    logger.error(f"Rate limit error (attempt {attempt + 1}): {e}")
                    if attempt < 2:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    return "Error: API rate limit exceeded. Please try again later."
                elif 'invalid' in error_message and 'api' in error_message:
                    return "Error: Invalid API configuration."
                else:
                    logger.error(f"Error (attempt {attempt + 1}): {e}", exc_info=True)
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    return f"Error: Failed after 3 attempts."

        return "Error: Maximum retries reached."


class TRONAssistant:
    def __init__(self):
        try:
            self.config = Config()
            self.audio_handler = AudioHandler(self.config)
            self.response_handler = ResponseHandler()
            self.speech_thread = None
        except Exception as e:
            logger.error(f"Failed to initialize TRONAssistant: {e}", exc_info=True)
            self.config = None
            self.audio_handler = None
            self.response_handler = ResponseHandler()
            self.speech_thread = None

    def save_history(self, mode, query, response):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    lines = list(csv.reader(f))
                    if len(lines) > MAX_HISTORY_ENTRIES:
                        with open(HISTORY_FILE, 'w', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow(['timestamp', 'mode', 'query', 'response'])
                            writer.writerows(lines[-MAX_HISTORY_ENTRIES + 1:])

            with open(HISTORY_FILE, 'a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), mode, query, response])

            os.makedirs("projects", exist_ok=True)
            output_file = os.path.join("projects", "TRON_project_conversation.txt")
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mode}\n")
                f.write(f"Query: {query}\nResponse: {response}\n\n")
        except Exception as e:
            logger.error(f"Failed to save history: {e}", exc_info=True)

    def format_response_for_web(self, response, mode):
        mode = mode.lower()
        formatters = {
            'quiz': self._format_quiz_content,
            'doubt': self._format_explanation_content,
            'code': self._format_code_content,
            'resume': self._format_resume_content
        }
        if mode in formatters:
            try:
                formatted_content = formatters[mode](response)
                return self._wrap_formatted_content(formatted_content, mode)
            except Exception as e:
                logger.error(f"Formatting error for {mode}: {e}", exc_info=True)
                return self._format_fallback(response)
        return self._format_fallback(response)

    def _wrap_formatted_content(self, content, mode):
        mode_config = {
            'quiz': {'color': 'cyan', 'icon': '🧠', 'title': 'Quiz Generated'},
            'doubt': {'color': 'purple', 'icon': '🤔', 'title': 'Doubt Resolved'},
            'code': {'color': 'red', 'icon': '🐛', 'title': 'Code Analysis'},
            'resume': {'color': 'yellow', 'icon': '📄', 'title': 'Resume Analysis'}
        }
        cfg = mode_config.get(mode, {'color': 'gray', 'icon': '', 'title': 'Response'})
        return f"""
        <div class="space-y-4">
            <div class="border-l-4 border-{cfg['color']}-400 pl-4">
                <h4 class="text-{cfg['color']}-400 font-semibold mb-2">{cfg['icon']} {cfg['title']}</h4>
            </div>
            <div class="bg-gray-800 p-4 rounded border border-{cfg['color']}-600">
                <div class="prose prose-invert max-w-none">{content}</div>
            </div>
        </div>"""

    def _format_fallback(self, response):
        safe = response.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br>')
        return f'<div class="space-y-4"><div class="bg-gray-800 p-4 rounded border border-gray-600"><div class="prose prose-invert max-w-none"><p class="text-gray-200">{safe}</p></div></div></div>'

    def _format_quiz_content(self, content):
        lines = content.split('\n')
        formatted_lines = []
        question_count = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            # Escape first, then apply markdown bold
            safe = self._escape_html(line)
            safe = re.sub(r'\*\*(.*?)\*\*', r'<strong class="text-cyan-300">\1</strong>', safe)
            if any(m in line.lower() for m in ['question','q:','q.']) and not line.startswith(('a)','b)','c)','d)')):
                question_count += 1
                if question_count > 1: formatted_lines.append('</div>')
                formatted_lines.append('<div class="question-block mt-4 p-3 bg-gray-700 rounded border border-cyan-500">')
                formatted_lines.append(f'<strong class="text-cyan-300">Question {question_count}:</strong>')
                formatted_lines.append(f'<p class="mt-2 text-gray-200">{safe}</p>')
            elif line.startswith(('a)','b)','c)','d)','A)','B)','C)','D)')):
                formatted_lines.append(f'<div class="option ml-4 mt-1 text-gray-300">• {safe}</div>')
            elif 'answer' in line.lower():
                formatted_lines.append('<div class="answer mt-2 p-2 bg-green-800 bg-opacity-50 rounded border border-green-500">')
                formatted_lines.append(f'<strong class="text-green-300">{safe}</strong>')
                formatted_lines.append('</div>')
            else:
                formatted_lines.append(f'<p class="text-gray-200">{safe}</p>')
        if question_count > 0: formatted_lines.append('</div>')
        return ''.join(formatted_lines)

    def _format_explanation_content(self, content):
        # Escape HTML first, then apply markdown so tags aren't double-escaped
        content = self._escape_html(content)
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong class="text-purple-300">\1</strong>', content)
        content = re.sub(r'\*(.*?)\*', r'<em class="text-purple-200">\1</em>', content)
        content = re.sub(r'`(.*?)`', r'<code class="bg-gray-700 px-2 py-1 rounded">\1</code>', content)
        paragraphs = content.split('\n\n')
        return ''.join(f'<p class="mt-3 text-gray-200">{p.replace(chr(10), "<br>")}</p>' for p in paragraphs if p.strip())

    def _format_code_content(self, content):
        lines = content.split('\n')
        formatted_lines = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith('```'):
                if in_code_block:
                    formatted_lines.append('</code></pre>')
                    in_code_block = False
                else:
                    formatted_lines.append('<pre class="bg-gray-900 p-3 rounded border border-red-500 mt-3"><code class="text-red-200">')
                    in_code_block = True
                continue
            if in_code_block:
                formatted_lines.append(f'{self._escape_html(line)}\n')
            else:
                # Escape first, then apply bold markdown
                safe_line = self._escape_html(line)
                safe_line = re.sub(r'\*\*(.*?)\*\*', r'<strong class="text-red-300">\1</strong>', safe_line)
                if safe_line.strip():
                    formatted_lines.append(f'<p class="text-gray-200 mt-2">{safe_line}</p>')
        if in_code_block: formatted_lines.append('</code></pre>')
        return ''.join(formatted_lines)

    def _format_resume_content(self, content):
        lines = content.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            # Escape first, then apply bold markdown
            if line.startswith('* '):
                safe = self._escape_html(line[2:].strip())
                safe = re.sub(r'\*\*(.*?)\*\*', r'<strong class="text-yellow-300">\1</strong>', safe)
                formatted_lines.append(f'<div class="ml-4 mt-2 text-gray-200">• {safe}</div>')
            else:
                safe = self._escape_html(line)
                safe = re.sub(r'\*\*(.*?)\*\*', r'<strong class="text-yellow-300">\1</strong>', safe)
                formatted_lines.append(f'<p class="text-gray-200 mt-2">{safe}</p>')
        return ''.join(formatted_lines)

    def _escape_html(self, text):
        return text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'","&#x27;")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def initialize_history_file():
    if not os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['timestamp', 'mode', 'query', 'response'])
        except IOError as e:
            logger.error(f"Failed to create history file: {e}")


def setup_app():
    try:
        initialize_history_file()
        os.makedirs("projects", exist_ok=True)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        logger.info("Application setup complete")
    except Exception as e:
        logger.error(f"Setup error: {e}", exc_info=True)


setup_app()

try:
    tron_instance = TRONAssistant()
    logger.info("TRON Assistant initialized")
except Exception as e:
    logger.error(f"Failed to initialize TRON: {e}", exc_info=True)
    tron_instance = None


# ── Flask Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    for html_file in ['index.html', 'tron_assistant_colored.html', 'Index.html']:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    return abort(404, description="HTML file not found")


@app.route('/favicon.ico')
def serve_favicon():
    if os.path.exists('favicon.ico'):
        return send_from_directory('.', 'favicon.ico', mimetype='image/x-icon')
    return '', 204


@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'port': os.environ.get('PORT', 'unknown'),
        'tron_status': 'initialized' if tron_instance else 'failed'
    })


@app.route('/ping')
def ping():
    return jsonify({'status': 'pong', 'timestamp': datetime.now().isoformat()})


@app.route('/api/process', methods=['POST'])
def process_query():
    try:
        if not tron_instance:
            return jsonify({'error': 'Service unavailable', 'status': 'error'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received', 'status': 'error'}), 400

        mode = data.get('mode')
        query = data.get('query', '')
        input_mode = data.get('input_mode', 'text')  # text | speech | hybrid

        logger.info(f"Processing: mode={mode}, input_mode={input_mode}, query length={len(query)}")

        mode_map = {
            'quiz': ("Quiz Generator", quiz_generator.generate_quiz),
            'doubt': ("Doubt Solver", doubt_solver.solve_doubt),
            'code': ("Code Debugger", lambda chat, q: code_debugger.explain_or_debug_code(chat, q)),
            'resume': ("Resume Analyzer", resume_analyzer.analyze_resume)
        }

        if mode not in mode_map:
            return jsonify({'error': f'Invalid mode: {mode}', 'status': 'error'}), 400

        if not query and mode != 'resume':
            return jsonify({'error': 'Query required', 'status': 'error'}), 400

        if mode == 'resume' and not query:
            if not getattr(resume_analyzer, 'LOADED_RESUME', None):
                return jsonify({'error': 'Please upload a resume file or paste resume content.', 'status': 'error'}), 400
            query = resume_analyzer.LOADED_RESUME

        mode_name, handler = mode_map[mode]

        try:
            raw_response = handler(tron_instance.response_handler.chat, query)
            if not raw_response or not raw_response.strip():
                raw_response = "No response generated. Please try again."
        except Exception as ai_error:
            logger.error(f"AI error: {ai_error}", exc_info=True)
            error_msg = str(ai_error).lower()
            raw_response = ("API quota exceeded. Please try again later."
                           if 'quota' in error_msg or 'limit' in error_msg
                           else f"AI processing error: {str(ai_error)}")

        formatted_response = tron_instance.format_response_for_web(raw_response, mode)
        tron_instance.save_history(mode_name, query, raw_response)

        return jsonify({
            'response': formatted_response,
            'raw_response': raw_response,
            'mode': mode_name,
            'input_mode': input_mode,
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        })

    except Exception as e:
        logger.error(f"Process error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/speech/transcribe', methods=['POST'])
def speech_transcribe():
    """
    Lightweight endpoint — transcription is done in the browser via Web Speech API.
    Frontend sends the already-transcribed text in the normal /api/process call.
    This endpoint is kept for compatibility / future server-side transcription.
    """
    return jsonify({
        'status': 'info',
        'message': 'Speech transcription is handled by the browser Web Speech API.',
        'note': 'Send the transcribed text via /api/process as a normal query.'
    })


@app.route('/api/speech/listen', methods=['POST'])
def speech_listen():
    return jsonify({'status': 'info', 'message': 'Speech recognition handled by frontend'})


@app.route('/api/speech/speak', methods=['POST'])
def speech_speak():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received', 'status': 'error'}), 400
        text = data.get('text', '')
        if not text:
            return jsonify({'error': 'No text provided', 'status': 'error'}), 400
        return jsonify({'status': 'success', 'message': 'Speech handled by frontend', 'text': text})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/speech/stop', methods=['POST'])
def speech_stop():
    return jsonify({'status': 'success', 'message': 'Speech stop handled by frontend'})


@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided', 'status': 'error'}), 400
        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'No file selected', 'status': 'error'}), 400
        if file and allowed_file(file.filename):
            filename = file.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            logger.info(f"File uploaded: {filename}")
            if filename.lower().endswith(('.pdf', '.doc', '.docx')):
                try:
                    extracted_text = resume_analyzer.extract_text_from_file(filepath)
                    resume_analyzer.LOADED_RESUME = extracted_text
                    return jsonify({'status': 'success', 'message': f'File {filename} uploaded and processed', 'filename': filename})
                except Exception as e:
                    logger.error(f"Text extraction failed: {e}", exc_info=True)
                    return jsonify({'status': 'error', 'message': f'Failed to extract text: {str(e)}'}), 400
            return jsonify({'status': 'success', 'message': f'File {filename} uploaded', 'filename': filename})
        return jsonify({'error': 'Invalid file type', 'status': 'error'}), 400
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        history_data = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 4:
                        history_data.append({
                            'timestamp': row[0],
                            'mode': row[1],
                            'query': row[2][:100] + '...' if len(row[2]) > 100 else row[2],
                            'response': row[3][:200] + '...' if len(row[3]) > 200 else row[3]
                        })
        history_data.reverse()
        return jsonify({'history': history_data[:20], 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
            initialize_history_file()
        return jsonify({'status': 'success', 'message': 'History cleared'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    ai_status = 'available' if tron_instance and tron_instance.response_handler.model else 'unavailable'
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'speech_recognition': 'browser_web_speech_api',
            'text_to_speech': 'browser_speech_synthesis',
            'ai_processing': ai_status
        }
    })


@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': getattr(error, 'description', 'Bad request'), 'status': 'error'}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': getattr(error, 'description', 'Not found'), 'status': 'error'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error', 'status': 'error'}), 500


application = app

if __name__ == "__main__":
    try:
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Starting TRON Assistant server on port {port}")
        app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)