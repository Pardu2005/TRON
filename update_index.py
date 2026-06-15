import re

ui_file = r'c:\Users\pardu\Downloads\tron_assistant_colored.html'
with open(ui_file, 'r', encoding='utf-8') as f:
    text = f.read()

# Extract the HTML up to the <script> tag
match = re.search(r'(.*?<script>)', text, re.DOTALL)
if not match:
    print('Could not find script tag')
    exit(1)

html_part = match.group(1)

script_part = r"""
        document.addEventListener('DOMContentLoaded', function() {
            // DOM Elements
            const featureButtons = document.querySelectorAll('.feature-btn');
            const submitBtn = document.getElementById('submitBtn');
            const queryInput = document.getElementById('queryInput');
            const responseOutput = document.getElementById('responseOutput');
            const fileBtn = document.getElementById('fileBtn');
            const resumeFile = document.getElementById('resumeFile');
            const inputModeSelect = document.getElementById('inputMode');
            
            const speakBtn = document.getElementById('speakBtn');
            const stopSpeakBtn = document.getElementById('stopSpeakBtn');
            const voiceBtn = document.getElementById('voiceBtn');
            const clearHistoryBtn = document.getElementById('clearHistoryBtn');
            const voiceStatus = document.getElementById('voiceStatus');
            const historyOutput = document.getElementById('historyOutput');

            let currentMode = null;
            let recognition = null;
            let isListening = false;
            let speechSynthesis = window.speechSynthesis;
            let currentUtterance = null;
            let history = [];

            // Check System Status
            const checkStatus = async () => {
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();
                    const statusIndicator = document.querySelector('.text-green-400.font-semibold');
                    if (statusIndicator) {
                        if (data.status === 'online') {
                            statusIndicator.innerHTML = '🟢 Online';
                            statusIndicator.className = 'text-green-400 font-semibold';
                        } else {
                            statusIndicator.innerHTML = '🔴 Offline';
                            statusIndicator.className = 'text-red-400 font-semibold';
                        }
                    }
                } catch (e) {
                    console.error('Status error', e);
                }
            };
            checkStatus();

            function showStatus(message, type = 'info', persistent = false) {
                const statusClass = type === 'success' ? 'status-success' : 
                                  type === 'error' ? 'status-error' : 'status-info';
                
                voiceStatus.innerHTML = `<div class="status-indicator ${statusClass}">${message}</div>`;
                
                if (!persistent) {
                    setTimeout(() => { voiceStatus.innerHTML = ''; }, 5000);
                }
            }

            function clearStatus() {
                voiceStatus.innerHTML = '';
            }

            // Load History
            const loadHistory = async () => {
                try {
                    const response = await fetch('/api/history');
                    const data = await response.json();
                    
                    if (data.status === 'success' && data.history && data.history.length > 0) {
                        history = data.history;
                        updateHistoryDisplay();
                    } else {
                        history = [];
                        updateHistoryDisplay();
                    }
                } catch (error) {
                    console.error('Error loading history:', error);
                }
            };
            loadHistory();

            function updateHistoryDisplay() {
                if (history.length === 0) {
                    historyOutput.innerHTML = `
                        <div class="text-center text-gray-500 py-4">
                            <i class="fas fa-clock opacity-50 mb-2 block"></i>
                            <p class="text-sm">No session history</p>
                        </div>
                    `;
                    return;
                }

                const modeColors = {
                    'Quiz Generator': 'text-cyan-400',
                    'Doubt Solver': 'text-purple-400',
                    'Code Debugger': 'text-red-400',
                    'Resume Analyzer': 'text-yellow-400'
                };
                const modeMap = {
                    'Quiz Generator': 'quiz',
                    'Doubt Solver': 'doubt',
                    'Code Debugger': 'code',
                    'Resume Analyzer': 'resume'
                };

                historyOutput.innerHTML = history.map(item => {
                    const uiMode = modeMap[item.mode] || 'text';
                    const colorClass = modeColors[item.mode] || 'text-gray-400';
                    const escapedQuery = item.query.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                    
                    return `
                    <div class="history-item" onclick="loadHistoryItem('${uiMode}', '${escapedQuery}')">
                        <div class="flex justify-between items-start mb-2">
                            <span class="text-xs ${colorClass} font-semibold uppercase">${item.mode}</span>
                            <span class="text-xs text-gray-500">${item.timestamp.split(' ')[1] || item.timestamp}</span>
                        </div>
                        <p class="text-sm text-gray-300 truncate">${item.query.substring(0, 60)}${item.query.length > 60 ? '...' : ''}</p>
                    </div>
                `}).join('');
            }

            window.loadHistoryItem = function(mode, query) {
                queryInput.value = query;
                const modeBtn = document.getElementById(mode + 'Btn');
                if (modeBtn) modeBtn.click();
                showStatus(`Loaded previous ${mode} query`, 'info');
            };

            // Speech Recognition
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = true;
                recognition.lang = 'en-US';

                recognition.onstart = function() {
                    isListening = true;
                    showStatus('🎤 Listening for voice input...', 'info', true);
                    speakBtn.classList.add('hidden');
                    stopSpeakBtn.classList.remove('hidden');
                };

                recognition.onresult = function(event) {
                    let finalTranscript = '';
                    let interimTranscript = '';
                    
                    for (let i = event.resultIndex; i < event.results.length; i++) {
                        if (event.results[i].isFinal) {
                            finalTranscript += event.results[i][0].transcript;
                        } else {
                            interimTranscript += event.results[i][0].transcript;
                        }
                    }
                    
                    if (finalTranscript) {
                        queryInput.value = finalTranscript;
                        showStatus(`✓ Voice captured: "${finalTranscript}"`, 'success');
                    } else if (interimTranscript) {
                        showStatus(`🎤 Listening: "${interimTranscript}"`, 'info', true);
                    }
                };

                recognition.onerror = function(event) {
                    showStatus(`❌ Speech recognition error: ${event.error}`, 'error');
                    resetSpeechButtons();
                };

                recognition.onend = function() {
                    resetSpeechButtons();
                };
            }

            function resetSpeechButtons() {
                isListening = false;
                speakBtn.classList.remove('hidden');
                stopSpeakBtn.classList.add('hidden');
                clearStatus();
            }

            // TTS
            voiceBtn.addEventListener('click', function() {
                if (!speechSynthesis) return;

                if (this.innerHTML.includes('Stop')) {
                    speechSynthesis.cancel();
                    resetTTSButton();
                    return;
                }

                const responseDiv = responseOutput.querySelector('.prose') || responseOutput;
                let textToRead = responseDiv.innerText || responseDiv.textContent;
                textToRead = textToRead.trim();

                if (!textToRead || textToRead.includes('Welcome to TRON Assistant') || textToRead.includes('Generating response')) {
                    showStatus('No content to read', 'error');
                    return;
                }

                speechSynthesis.cancel();
                currentUtterance = new SpeechSynthesisUtterance(textToRead);
                
                currentUtterance.onstart = () => {
                    voiceBtn.innerHTML = '<i class="fas fa-volume-mute mr-2"></i>Stop Reading';
                    showStatus('🔊 Reading response aloud...', 'info', true);
                };

                currentUtterance.onend = () => {
                    resetTTSButton();
                    clearStatus();
                };
                
                currentUtterance.onerror = () => {
                    resetTTSButton();
                    clearStatus();
                };

                speechSynthesis.speak(currentUtterance);
            });

            function resetTTSButton() {
                voiceBtn.innerHTML = '<i class="fas fa-volume-up mr-2"></i>Read Output';
            }

            // Controls
            speakBtn.addEventListener('click', function() {
                if (recognition && !isListening) {
                    recognition.start();
                } else {
                    showStatus('Speech recognition not supported in this browser', 'error');
                }
            });

            stopSpeakBtn.addEventListener('click', function() {
                if (recognition && isListening) {
                    recognition.stop();
                }
            });

            fileBtn.addEventListener('click', function() {
                resumeFile.click();
            });

            resumeFile.addEventListener('change', async function() {
                const file = this.files[0];
                if (!file) return;

                showStatus(`Uploading ${file.name}...`, 'info', true);
                const formData = new FormData();
                formData.append('file', file);

                try {
                    const response = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        showStatus(`✓ File "${file.name}" uploaded successfully`, 'success');
                        queryInput.value = `Analyze my resume`;
                        if (currentMode === 'resume') {
                            submitBtn.click();
                        }
                    } else {
                        showStatus(`❌ ${data.error}`, 'error');
                    }
                } catch (err) {
                    showStatus(`❌ Upload failed`, 'error');
                }
            });

            clearHistoryBtn.addEventListener('click', async function() {
                if (!confirm('Clear all history?')) return;
                try {
                    const response = await fetch('/api/history/clear', { method: 'POST' });
                    const data = await response.json();
                    if (data.status === 'success') {
                        history = [];
                        updateHistoryDisplay();
                        showStatus('History cleared', 'info');
                    }
                } catch(e) {
                    showStatus('Failed to clear history', 'error');
                }
            });

            inputModeSelect.addEventListener('change', function() {
                const mode = this.value;
                const placeholders = {
                    text: "Select a service module above and enter your query...",
                    speech: "Click Voice Input to speak your query...",
                    hybrid: "Type your query or use voice input..."
                };
                queryInput.placeholder = placeholders[mode] || placeholders.text;
                showStatus(`Switched to ${mode.toUpperCase()} mode`, 'info');
            });

            featureButtons.forEach(btn => {
                btn.addEventListener('click', function() {
                    featureButtons.forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentMode = this.id.replace('Btn', '');
                    
                    if (currentMode === 'resume') {
                        fileBtn.classList.remove('hidden');
                    } else {
                        fileBtn.classList.add('hidden');
                    }
                    
                    const placeholders = {
                        quiz: 'Enter topic for quiz generation (e.g., "JavaScript fundamentals")',
                        doubt: 'Describe your doubt or paste the concept you need help with',
                        code: 'Paste your code snippet and describe the issue you\'re facing',
                        resume: 'Upload your resume file or paste resume content for analysis'
                    };
                    queryInput.placeholder = placeholders[currentMode];
                    showStatus(`${this.title} mode activated`, 'success');
                });
            });

            submitBtn.addEventListener('click', async function() {
                const query = queryInput.value.trim();
                const inputMode = inputModeSelect.value;
                
                if (!currentMode) {
                    showStatus('Please select a service module first', 'error');
                    return;
                }
                if (!query && currentMode !== 'resume') {
                    showStatus('Please enter your query', 'error');
                    return;
                }

                submitBtn.innerHTML = '<i class="loading-spinner mr-2"></i>Processing...';
                submitBtn.disabled = true;
                responseOutput.innerHTML = '<div class="text-cyan-400 flex items-center justify-center h-full"><i class="fas fa-circle-notch fa-spin text-3xl mr-3"></i> Generating response...</div>';

                try {
                    const response = await fetch('/api/process', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ mode: currentMode, query, inputMode })
                    });
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        responseOutput.innerHTML = data.response;
                        queryInput.value = '';
                        showStatus('Query processed successfully', 'success');
                        setTimeout(loadHistory, 1000); // refresh history
                        
                        if (inputMode === 'speech' || inputMode === 'hybrid') {
                            setTimeout(() => voiceBtn.click(), 1000);
                        }
                    } else {
                        responseOutput.innerHTML = `<div class="text-red-500 p-4 bg-red-900 bg-opacity-20 border border-red-500 rounded">❌ Error: ${data.error}</div>`;
                    }
                } catch (error) {
                    responseOutput.innerHTML = `<div class="text-red-500 p-4 bg-red-900 bg-opacity-20 border border-red-500 rounded">❌ Network Error: Failed to communicate with server</div>`;
                }

                submitBtn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Execute';
                submitBtn.disabled = false;
            });

            // Auto-resize
            queryInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 200) + 'px';
            });
            
            // Clean up the dangling mock HTML content left over from old design output
            responseOutput.innerHTML = `
                <div class="text-center text-gray-400 py-8">
                    <i class="fas fa-robot text-4xl mb-4 opacity-50"></i>
                    <p>Welcome to TRON Assistant</p>
                    <p class="text-sm mt-2">Select a service module and enter your query to begin</p>
                </div>
            `;
        });
    </script>
</body>
</html>
"""

output_file = r'c:\Users\pardu\PycharmProjects\TRON\index.html'
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_part + script_part)

print('File written successfully')
