/* ── NyayaVoice — Frontend UI Logic (Backend-Connected) ──── */

(function () {
  'use strict';

  const API_BASE = window.location.origin;

  /* ── State ───────────────────────────────────────────────── */
  let userId = localStorage.getItem('nyayavoice_user_id') || ('user_' + Math.random().toString(36).slice(2, 10));
  localStorage.setItem('nyayavoice_user_id', userId);

  let conversationHistory = [];
  let generatedDocs = JSON.parse(localStorage.getItem('nyayavoice_docs') || '[]');
  let messageCount = parseInt(localStorage.getItem('nyayavoice_msg_count') || '0', 10);

  /* ── Vapi ────────────────────────────────────────────────── */
  let vapiInstance = null;
  let vapiPublicKey = '';

  async function initVapi() {
    try {
      const res = await fetch(API_BASE + '/api/config');
      const cfg = await res.json();
      vapiPublicKey = cfg.vapi_public_key || '';
      if (vapiPublicKey && window.Vapi) {
        vapiInstance = new window.Vapi(vapiPublicKey);
        setupVapiEvents();
      }
    } catch (e) {
      console.warn('Vapi init skipped:', e.message);
    }
  }

  function setupVapiEvents() {
    if (!vapiInstance) return;

    vapiInstance.on('speech-start', () => {
      newMicBtn.classList.add('listening');
      newMicStatus.textContent = t('vcListening');
    });
    vapiInstance.on('speech-end', () => {
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcProcessing');
    });
    vapiInstance.on('message', (msg) => {
      // Handle transcript events (final transcripts from user/assistant)
      if (msg.type === 'transcript' && msg.transcriptType === 'final') {
        if (msg.role === 'user') {
          showPage('chat');
          addMessage(msg.transcript, true);
        } else if (msg.role === 'assistant') {
          showPage('chat');
          addMessage(markdownToHtml(msg.transcript), false, getLang());
        }
      }
      // Handle conversation-update events (Vapi SDK v2 emits these for assistant responses)
      if (msg.type === 'conversation-update') {
        const msgs = msg.conversation || [];
        const last = msgs[msgs.length - 1];
        if (last && last.role === 'assistant' && last.content) {
          showPage('chat');
          addMessage(markdownToHtml(last.content), false, getLang());
        }
      }
    });
    vapiInstance.on('call-end', () => {
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
    });
    vapiInstance.on('error', (err) => {
      console.error('Vapi error:', err);
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      // Show error in chat so user knows what happened
      addMessage(
        getLang() === 'hi'
          ? '⚠️ वॉइस कॉल में त्रुटि हुई। कृपया टेक्स्ट चैट का उपयोग करें।'
          : '⚠️ Voice call error. Please use text chat instead.',
        false
      );
    });
  }

  /* ── DOM refs ──────────────────────────────────────────── */
  const sidebar = document.getElementById('sidebar');
  const mainContent = document.getElementById('mainContent');
  const mobileHeader = document.getElementById('mobileHeader');
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  const langSwitch = document.getElementById('langSwitch');
  const langMobile = document.getElementById('langSwitchMobile');
  const settingsLang = document.getElementById('settingsLang');
  const themeToggle = document.getElementById('themeToggle');
  const micBtn = document.getElementById('micBtn');
  const micStatus = document.getElementById('micStatus');
  const chatInput = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendBtn');
  const chatMessages = document.getElementById('chatMessages');
  const offlineBanner = document.getElementById('offlineBanner');

  let overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  document.body.appendChild(overlay);

  /* ── NAVIGATION ────────────────────────────────────────── */
  const navBtns = document.querySelectorAll('.nav-btn[data-page]');
  const pages = document.querySelectorAll('.page');

  function showPage(pageId) {
    pages.forEach(p => p.classList.remove('active'));
    navBtns.forEach(b => b.classList.remove('active'));
    const target = document.getElementById('page-' + pageId);
    if (target) target.classList.add('active');
    navBtns.forEach(b => { if (b.dataset.page === pageId) b.classList.add('active'); });
    closeSidebar();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (pageId === 'docs') renderDocsList();
  }

  navBtns.forEach(btn => btn.addEventListener('click', () => showPage(btn.dataset.page)));

  document.querySelectorAll('.quick-action-card[data-page]').forEach(card => {
    card.addEventListener('click', () => showPage(card.dataset.page));
  });

  /* ── SIDEBAR MOBILE ────────────────────────────────────── */
  function openSidebar() { sidebar.classList.add('open'); overlay.classList.add('active'); }
  function closeSidebar() { sidebar.classList.remove('open'); overlay.classList.remove('active'); }
  hamburgerBtn.addEventListener('click', () => sidebar.classList.contains('open') ? closeSidebar() : openSidebar());
  overlay.addEventListener('click', closeSidebar);

  /* ── LANGUAGE SWITCHING ────────────────────────────────── */
  function switchLang(code) {
    applyLang(code);
    [langSwitch, langMobile, settingsLang].forEach(sel => { if (sel) sel.value = code; });
  }
  langSwitch.addEventListener('change', e => switchLang(e.target.value));
  langMobile.addEventListener('change', e => switchLang(e.target.value));
  settingsLang.addEventListener('change', e => switchLang(e.target.value));

  /* ── THEME TOGGLE ──────────────────────────────────────── */
  function initTheme() {
    const savedTheme = localStorage.getItem('nyayavoice_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    if (themeToggle) {
      themeToggle.addEventListener('click', toggleTheme);
    }
  }

  function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('nyayavoice_theme', newTheme);
  }

  /* ── HELPER: API call ──────────────────────────────────── */
  async function apiCall(endpoint, body) {
    const res = await fetch(API_BASE + endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `API error ${res.status}`);
    }
    return res.json();
  }

  /* ── HELPER: Convert basic markdown to HTML ────────────── */
  function markdownToHtml(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')   // **bold**
      .replace(/\*(.+?)\*/g, '<em>$1</em>')                // *italic*
      .replace(/^- (.+)$/gm, '<li>$1</li>')                // - list items
      .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')          // wrap lists
      .replace(/\n\n/g, '</p><p>')                         // paragraphs
      .replace(/\n/g, '<br>');                             // line breaks
  }

  /* ── HELPER: Strip HTML/markdown for TTS ───────────────── */
  function stripForSpeech(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, '$1')      // remove **bold**
      .replace(/\*(.+?)\*/g, '$1')           // remove *italic*
      .replace(/<[^>]+>/g, ' ')              // remove HTML tags
      .replace(/#+\s/g, '')                  // remove markdown headers
      .replace(/\[(.+?)\]/g, '$1')           // remove [brackets]
      .replace(/https?:\/\/\S+/g, '')        // remove URLs
      .replace(/\s{2,}/g, ' ')              // collapse spaces
      .trim();
  }

  /* ── TEXT-TO-SPEECH ENGINE ──────────────────────────────── */
  let ttsEnabled = true;
  let currentUtterance = null;

  function speakResponse(text, lang) {
    if (!ttsEnabled) return;
    if (!window.speechSynthesis) return;

    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    const clean = stripForSpeech(text);
    if (!clean) return;

    const utterance = new SpeechSynthesisUtterance(clean);

    // Set language for TTS
    const ttsLangMap = {
      'hi': 'hi-IN', 'en': 'en-IN',
      'ta': 'ta-IN', 'bn': 'bn-IN',
      'mr': 'mr-IN', 'te': 'te-IN',
      'gu': 'gu-IN', 'kn': 'kn-IN',
      'pa': 'pa-IN', 'ur': 'ur-IN',
    };
    utterance.lang = ttsLangMap[lang || getLang()] || 'en-IN';
    utterance.rate = 0.92;   // slightly slower for clarity
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // Pick best available voice for the language
    const voices = window.speechSynthesis.getVoices();
    const langCode = utterance.lang.split('-')[0];
    const match = voices.find(v => v.lang.startsWith(langCode))
      || voices.find(v => v.lang.startsWith('en'));
    if (match) utterance.voice = match;

    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeech() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    currentUtterance = null;
  }

  // Voices load async in some browsers — preload them
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }

  /* ── CHAT ──────────────────────────────────────────────── */
  function addMessage(text, isUser, lang) {
    const wrapper = document.createElement('div');
    wrapper.className = 'msg ' + (isUser ? 'msg-user' : 'msg-bot');
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = text;

    // Add a small speaker button on bot messages so user can replay
    if (!isUser) {
      const speakBtn = document.createElement('button');
      speakBtn.className = 'tts-replay-btn';
      speakBtn.title = 'Read aloud';
      speakBtn.innerHTML = '🔊';
      speakBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:0.85rem;opacity:0.6;margin-left:6px;padding:2px 4px;vertical-align:middle;';
      speakBtn.addEventListener('click', () => speakResponse(text, lang || getLang()));
      bubble.appendChild(speakBtn);
    }

    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Auto-speak bot responses
    if (!isUser) {
      speakResponse(text, lang || getLang());
    }
  }

  function addTypingIndicator() {
    const wrapper = document.createElement('div');
    wrapper.className = 'msg msg-bot typing-indicator';
    wrapper.id = 'typingIndicator';
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = '<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>';
    wrapper.appendChild(bubble);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeTypingIndicator() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
  }

  async function sendToBackend(userText) {
    // Stop any ongoing speech when user sends a new message
    stopSpeech();
    addTypingIndicator();
    try {
      const result = await apiCall('/api/query', {
        user_id: userId,
        text: userText,
        language: getLang(),
        conversation: conversationHistory.slice(-8),
      });

      removeTypingIndicator();

      conversationHistory.push({ role: 'user', text: userText });
      conversationHistory.push({ role: 'assistant', text: result.response });

      // Convert markdown to HTML so **bold** and *italic* render correctly
      let responseHtml = markdownToHtml(result.response);

      if (result.urgency) {
        responseHtml =
          '<div style="background:#fef2f2;border-left:4px solid #ef4444;padding:8px 12px;border-radius:6px;margin-bottom:8px;">' +
          '<strong style="color:#ef4444;">⚠️ ' + (getLang() === 'hi' ? 'आपातकाल' : 'EMERGENCY') + '</strong></div>' +
          responseHtml;
      }
      // Pass detected language so TTS uses the right voice
      addMessage(responseHtml, false, result.language || getLang());

      messageCount++;
      localStorage.setItem('nyayavoice_msg_count', messageCount);
      updateStats();

    } catch (err) {
      removeTypingIndicator();
      console.error('Backend query failed:', err);
      const errMsg = getLang() === 'hi'
        ? '⚠️ सर्वर से जुड़ने में समस्या हुई। कृपया जाँचें कि बैकएंड चल रहा है।<br><br>आपातकाल: पुलिस <strong>100</strong> | महिला <strong>181</strong> | आपातकाल <strong>112</strong>'
        : '⚠️ Could not reach the server. Please check the backend is running.<br><br>Emergency: Police <strong>100</strong> | Women <strong>181</strong> | Emergency <strong>112</strong>';
      addMessage(errMsg, false, getLang());
    }
  }

  /* ── FALLBACK (offline / no backend) ───────────────────── */
  const LEGAL_RESPONSES = {
    en: {
      theft: '<strong>Theft — Your Legal Rights:</strong><br><br>IPC Section 378/379: Theft is a cognizable offence. Police MUST register your FIR — free of cost.<br><br>Zero FIR: You can file at ANY police station regardless of where the crime happened.<br><br><em>Would you like me to help you draft an FIR? Go to the <strong>FIR Wizard</strong> section.</em>',
      violence: '<strong>Domestic Violence — Your Legal Protection:</strong><br><br>Protection of Women from Domestic Violence Act 2005 covers physical, emotional, verbal, sexual, and economic abuse.<br><br>Immediate help: Women Helpline <strong>181</strong> (24/7) | Police <strong>100</strong><br><br><em>You are not alone. Help is available right now.</em>',
      default: 'I\'m currently unable to reach the server. Please check if the backend is running. In the meantime, here are emergency numbers:<br><br>Police: <strong>100</strong> | Women Helpline: <strong>181</strong> | Emergency: <strong>112</strong> | NALSA Legal Aid: <strong>15100</strong>'
    },
    hi: {
      theft: '<strong>चोरी — आपके कानूनी अधिकार:</strong><br><br>भारतीय दण्ड संहिता धारा 378/379: चोरी संज्ञेय अपराध है। पुलिस को आपकी एफ़आईआर निःशुल्क दर्ज करनी होगी।<br><br><em>एफ़आईआर विज़ार्ड में जाकर प्रारूप तैयार करें।</em>',
      violence: '<strong>घरेलू हिंसा — आपकी कानूनी सुरक्षा:</strong><br><br>घरेलू हिंसा से महिलाओं की सुरक्षा अधिनियम 2005 के तहत शिकायत दर्ज कराएँ।<br><br>तुरन्त सहायता: महिला हेल्पलाइन <strong>181</strong> | पुलिस <strong>100</strong>',
      default: 'सर्वर से कनेक्ट नहीं हो पा रहा। कृपया जाँचें कि बैकएंड चल रहा है।<br><br>आपातकालीन नम्बर: पुलिस <strong>100</strong> | महिला हेल्पलाइन <strong>181</strong> | आपातकाल <strong>112</strong>'
    }
  };

  function fallbackReply(userText) {
    const lang = getLang();
    const lower = userText.toLowerCase();
    const r = LEGAL_RESPONSES[lang] || LEGAL_RESPONSES.en;
    let reply = r.default;
    if (/chori|theft|stolen|चोरी|phone|फ़ोन|snatch/.test(lower)) reply = r.theft;
    else if (/violen|hinsa|हिंसा|domestic|abuse|beat|पीट/.test(lower)) reply = r.violence;
    addMessage(reply, false);
  }

  sendBtn.addEventListener('click', () => {
    const text = chatInput.value.trim();
    if (!text) return;
    addMessage(text, true);
    chatInput.value = '';
    sendToBackend(text);
  });

  chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendBtn.click(); });

  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      showPage('chat');
      const text = chip.textContent.trim();
      addMessage(text, true);
      sendToBackend(text);
    });
  });

  /* ── STATS ─────────────────────────────────────────────── */
  function updateStats() {
    const statNums = document.querySelectorAll('.stat-card .stat-num');
    if (statNums.length >= 2) {
      statNums[0].textContent = messageCount;
      statNums[1].textContent = generatedDocs.length;
    }
  }

  /* ── MIC BUTTON — Vapi Voice Call OR Web Speech API ────── */
  micBtn.replaceWith(micBtn.cloneNode(true));
  const newMicBtn = document.getElementById('micBtn');
  const newMicStatus = document.getElementById('micStatus');

  newMicBtn.addEventListener('click', () => {
    if (vapiInstance) {
      startVapiCall();
    } else {
      startWebSpeechDashboard();
    }
  });

  function startVapiCall() {
    if (newMicBtn.classList.contains('listening')) {
      vapiInstance.stop();
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      return;
    }
    newMicBtn.classList.add('listening');
    newMicStatus.textContent = t('vcListening');

    vapiInstance.start({
      serverUrl: API_BASE + '/vapi-webhook',
      serverUrlSecret: '',
      metadata: { user_id: userId, language: getLang() },
    }).catch(err => {
      console.error('Vapi call failed:', err);
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      startWebSpeechDashboard();
    });
  }

  /* ── WEB SPEECH API — Fallback Voice Input ─────────────── */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let activeRecognition = null;

  function getSpeechLang() {
    const lang = getLang();
    const speechLangMap = {
      'hi': 'hi-IN',
      'en': 'en-IN',
      'ta': 'ta-IN',
      'bn': 'bn-IN',
      'mr': 'mr-IN',
      'te': 'te-IN',
      'gu': 'gu-IN',
      'kn': 'kn-IN',
      'pa': 'pa-IN',
      'ur': 'ur-IN',
    };
    return speechLangMap[lang] || 'en-IN';
  }

  function startWebSpeechDashboard() {
    if (!SpeechRecognition) {
      alert(getLang() === 'hi' ? 'आपका ब्राउज़र वॉइस इनपुट का समर्थन नहीं करता।' : 'Your browser does not support voice input.');
      return;
    }

    if (newMicBtn.classList.contains('listening')) {
      if (activeRecognition) activeRecognition.stop();
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = getSpeechLang();
    recognition.interimResults = false;
    recognition.continuous = false;
    activeRecognition = recognition;

    newMicBtn.classList.add('listening');
    newMicStatus.textContent = t('vcListening');

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      activeRecognition = null;
      stopSpeech(); // stop any ongoing TTS before processing new input
      showPage('chat');
      addMessage(transcript, true);
      sendToBackend(transcript);
    };

    recognition.onerror = (event) => {
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      activeRecognition = null;
      // Show a visible error so user knows what happened
      let errMsg = '';
      if (event.error === 'not-allowed') {
        errMsg = getLang() === 'hi'
          ? '⚠️ माइक्रोफ़ोन की अनुमति नहीं मिली। ब्राउज़र सेटिंग में माइक्रोफ़ोन की अनुमति दें।'
          : '⚠️ Microphone permission denied. Please allow microphone access in your browser settings.';
      } else if (event.error === 'no-speech') {
        errMsg = getLang() === 'hi'
          ? '⚠️ कोई आवाज़ नहीं सुनी। कृपया फिर से बोलें।'
          : '⚠️ No speech detected. Please try speaking again.';
      } else {
        errMsg = getLang() === 'hi'
          ? '⚠️ वॉइस इनपुट में त्रुटि हुई। कृपया टेक्स्ट टाइप करें।'
          : '⚠️ Voice input error. Please type your question instead.';
      }
      showPage('chat');
      addMessage(errMsg, false);
    };

    recognition.onend = () => {
      newMicBtn.classList.remove('listening');
      newMicStatus.textContent = t('vcReady');
      activeRecognition = null;
    };

    recognition.start();
  }

  /* ── Voice input for form fields ───────────────────────── */
  function startVoiceInput(targetId, btn) {
    if (!SpeechRecognition) {
      alert(getLang() === 'hi' ? 'आपका ब्राउज़र वॉइस इनपुट का समर्थन नहीं करता। कृपया Chrome उपयोग करें।' : 'Your browser does not support voice input. Please use Chrome.');
      return;
    }

    if (activeRecognition) {
      activeRecognition.stop();
      activeRecognition = null;
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = getSpeechLang();
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    activeRecognition = recognition;

    btn.classList.add('voice-active');

    const target = document.getElementById(targetId);
    let finalTranscript = target.value || '';

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += (finalTranscript ? ' ' : '') + event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      target.value = finalTranscript + (interim ? ' ' + interim : '');
    };

    recognition.onerror = () => {
      btn.classList.remove('voice-active');
      activeRecognition = null;
    };

    recognition.onend = () => {
      btn.classList.remove('voice-active');
      activeRecognition = null;
      target.value = finalTranscript;
    };

    recognition.start();
  }

  document.querySelectorAll('.voice-input-btn[data-voice-target]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      startVoiceInput(btn.dataset.voiceTarget, btn);
    });
  });

  /* ── CHAT MIC — Real Speech Recognition ────────────────── */
  const chatMicBtn = document.getElementById('chatMicBtn');
  let chatRecognition = null;

  if (chatMicBtn) {
    chatMicBtn.addEventListener('click', () => {
      if (!SpeechRecognition) {
        alert(getLang() === 'hi' ? 'आपका ब्राउज़र वॉइस इनपुट का समर्थन नहीं करता।' : 'Your browser does not support voice input.');
        return;
      }

      if (chatRecognition) {
        chatRecognition.stop();
        chatRecognition = null;
        chatMicBtn.classList.remove('voice-active');
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.lang = getSpeechLang();
      recognition.interimResults = false;
      recognition.continuous = false;
      chatRecognition = recognition;

      chatMicBtn.classList.add('voice-active');

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
        chatMicBtn.classList.remove('voice-active');
        chatRecognition = null;
        stopSpeech(); // stop any ongoing TTS before processing new input
        // Show the transcript as user message and send to backend directly
        addMessage(transcript, true);
        chatInput.value = '';
        sendToBackend(transcript);
      };

      recognition.onerror = (event) => {
        chatMicBtn.classList.remove('voice-active');
        chatRecognition = null;
        if (event.error === 'not-allowed') {
          addMessage(
            getLang() === 'hi'
              ? '⚠️ माइक्रोफ़ोन की अनुमति नहीं मिली। ब्राउज़र सेटिंग में माइक्रोफ़ोन की अनुमति दें।'
              : '⚠️ Microphone permission denied. Please allow microphone access in your browser settings.',
            false
          );
        } else if (event.error === 'no-speech') {
          addMessage(
            getLang() === 'hi' ? '⚠️ कोई आवाज़ नहीं सुनी। कृपया फिर से बोलें।' : '⚠️ No speech detected. Please try again.',
            false
          );
        }
      };

      recognition.onend = () => {
        chatMicBtn.classList.remove('voice-active');
        chatRecognition = null;
      };

      recognition.start();
    });
  }

  /* ── FIR WIZARD ────────────────────────────────────────── */
  const firWizard = document.getElementById('firWizard');
  let firStep = 1;

  function showFirStep(n) {
    firStep = n;
    firWizard.querySelectorAll('.wizard-step').forEach(s => { s.classList.remove('active'); s.style.display = 'none'; });
    const target = firWizard.querySelector(`[data-step="${n}"]`);
    if (target) { target.style.display = ''; target.classList.add('active'); }
  }

  firWizard.addEventListener('click', e => {
    if (e.target.classList.contains('wizard-next')) {
      if (firStep === 1 && !document.getElementById('firIncident').value.trim()) {
        alert(t('alertIncident')); return;
      }
      if (firStep === 2 && !document.getElementById('firDate').value) {
        alert(t('alertDate')); return;
      }
      if (firStep === 3 && !document.getElementById('firLocation').value.trim()) {
        alert(t('alertLocation')); return;
      }
      if (firStep < 5) showFirStep(firStep + 1);
      if (firStep === 5) buildFirReview();
    }
    if (e.target.classList.contains('wizard-back')) {
      if (firStep > 1) showFirStep(firStep - 1);
    }
  });

  function buildFirReview() {
    const lang = getLang();
    const labels = lang === 'hi'
      ? { what: 'क्या हुआ', when: 'कब हुआ', where: 'कहाँ हुआ', suspect: 'आरोपी', witness: 'गवाह' }
      : { what: 'What happened', when: 'When', where: 'Where', suspect: 'Suspect', witness: 'Witness' };

    document.getElementById('firReview').innerHTML = `
      <p><strong>${labels.what}:</strong> ${document.getElementById('firIncident').value || '—'}</p>
      <p><strong>${labels.when}:</strong> ${document.getElementById('firDate').value || '—'}</p>
      <p><strong>${labels.where}:</strong> ${document.getElementById('firLocation').value || '—'}</p>
      <p><strong>${labels.suspect}:</strong> ${document.getElementById('firSuspect').value || '—'}</p>
      <p><strong>${labels.witness}:</strong> ${document.getElementById('firWitness').value || '—'}</p>
    `;
  }

  /* ── FIR Generate — calls backend /generate-document ───── */
  document.getElementById('firGenerateBtn').addEventListener('click', async () => {
    const incident = document.getElementById('firIncident').value;
    const date = document.getElementById('firDate').value;
    const location = document.getElementById('firLocation').value;
    const suspect = document.getElementById('firSuspect').value;
    const witness = document.getElementById('firWitness').value;

    const generateBtn = document.getElementById('firGenerateBtn');
    generateBtn.disabled = true;
    generateBtn.textContent = getLang() === 'hi' ? 'तैयार हो रहा है...' : 'Generating...';

    try {
      const result = await apiCall('/api/generate-document', {
        user_id: userId,
        doc_type: 'FIR',
        details: {
          incident_description: incident,
          date_time: date,
          location: location,
          suspect_description: suspect || 'Unknown',
          witness: witness || 'None',
          complainant_id: userId,
        },
      });

      generatedDocs.push({
        name: result.filename,
        url: result.document_url,
        type: 'FIR',
        date: new Date().toLocaleDateString(),
      });
      localStorage.setItem('nyayavoice_docs', JSON.stringify(generatedDocs));
      updateStats();

      showFirStep('done');

      const downloadBtn = firWizard.querySelector('[data-step="done"] .btn-primary');
      if (downloadBtn) {
        downloadBtn.onclick = () => window.open(result.document_url, '_blank');
      }

    } catch (err) {
      console.error('FIR generation failed:', err);
      alert((getLang() === 'hi' ? 'एफ़आईआर बनाने में त्रुटि: ' : 'FIR generation failed: ') + err.message);
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = t('firGenerate');
    }
  });

  document.getElementById('firNewBtn').addEventListener('click', () => {
    ['firIncident', 'firDate', 'firLocation', 'firSuspect', 'firWitness'].forEach(id => document.getElementById(id).value = '');
    showFirStep(1);
  });

  const detectBtn = document.getElementById('detectLocationBtn');
  detectBtn.addEventListener('click', () => {
    detectBtn.querySelector('span').textContent = t('firDetecting');
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          document.getElementById('firLocation').value =
            `Lat: ${pos.coords.latitude.toFixed(4)}, Lon: ${pos.coords.longitude.toFixed(4)}`;
          detectBtn.querySelector('span').textContent = t('firDetected');
          setTimeout(() => detectBtn.querySelector('span').textContent = t('firDetect'), 2000);
        },
        () => {
          document.getElementById('firLocation').value =
            getLang() === 'hi' ? 'मुख्य बाज़ार, सेक्टर 12, दिल्ली' : 'Main Bazaar, Sector 12, Delhi';
          detectBtn.querySelector('span').textContent = t('firDetected');
          setTimeout(() => detectBtn.querySelector('span').textContent = t('firDetect'), 2000);
        }
      );
    } else {
      document.getElementById('firLocation').value =
        getLang() === 'hi' ? 'मुख्य बाज़ार, सेक्टर 12, दिल्ली' : 'Main Bazaar, Sector 12, Delhi';
      detectBtn.querySelector('span').textContent = t('firDetected');
      setTimeout(() => detectBtn.querySelector('span').textContent = t('firDetect'), 2000);
    }
  });

  /* ── FILE UPLOAD (Case Predictor) ──────────────────────── */
  const uploadZone = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileUploadInput');
  const filesList = document.getElementById('uploadedFilesList');
  let uploadedFiles = [];

  uploadZone.addEventListener('click', () => fileInput.click());
  uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
  uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => { handleFiles(fileInput.files); fileInput.value = ''; });

  function handleFiles(files) {
    for (const file of files) {
      if (file.size > 25 * 1024 * 1024) {
        alert(getLang() === 'hi' ? `${file.name} बहुत बड़ी है (अधिकतम 25MB)` : `${file.name} is too large (max 25MB)`);
        continue;
      }
      uploadedFiles.push(file);
    }
    renderUploadedFiles();
  }

  function getFileIcon(name) {
    const ext = name.split('.').pop().toLowerCase();
    if (['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) return '&#127909;';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return '&#128247;';
    if (['pdf'].includes(ext)) return '&#128196;';
    if (['doc', 'docx'].includes(ext)) return '&#128209;';
    return '&#128206;';
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function renderUploadedFiles() {
    filesList.innerHTML = '';
    uploadedFiles.forEach((file, i) => {
      const div = document.createElement('div');
      div.className = 'uploaded-file';
      div.innerHTML = `
        <span class="uploaded-file-icon">${getFileIcon(file.name)}</span>
        <div class="uploaded-file-info">
          <div class="uploaded-file-name">${file.name}</div>
          <div class="uploaded-file-size">${formatSize(file.size)}</div>
        </div>
        <button class="uploaded-file-remove" data-idx="${i}" title="Remove">&times;</button>
      `;
      filesList.appendChild(div);
    });

    filesList.querySelectorAll('.uploaded-file-remove').forEach(btn => {
      btn.addEventListener('click', e => {
        uploadedFiles.splice(parseInt(e.target.dataset.idx), 1);
        renderUploadedFiles();
      });
    });
  }

  /* ── CASE PREDICTOR ────────────────────────────────────── */
  const CASE_DATA = {
    theft: { success: 68, time: '3-6', cost: '₹2-5K', similar: 24, won: 55, settled: 20, lost: 25, laws: ['IPC 378', 'IPC 379', 'IPC 411', 'CrPC 154'] },
    dv: { success: 75, time: '6-12', cost: '₹5-15K', similar: 32, won: 60, settled: 25, lost: 15, laws: ['DV Act 2005', 'IPC 498A', 'CrPC 125', 'HMA 1955'] },
    wage: { success: 80, time: '3-9', cost: '₹1-3K', similar: 28, won: 65, settled: 25, lost: 10, laws: ['Payment of Wages Act', 'Min. Wages Act', 'ID Act 1947'] },
    harass: { success: 70, time: '6-18', cost: '₹10-30K', similar: 18, won: 50, settled: 30, lost: 20, laws: ['POSH Act 2013', 'IPC 354A', 'IPC 509'] },
    land: { success: 55, time: '12-36', cost: '₹20-80K', similar: 20, won: 45, settled: 30, lost: 25, laws: ['TPA 1882', 'Registration Act', 'Specific Relief Act'] },
    cyber: { success: 62, time: '6-12', cost: '₹5-15K', similar: 15, won: 50, settled: 25, lost: 25, laws: ['IT Act 2000', 'IT Amdt. 2008', 'IPC 420', 'IPC 468'] },
    consumer: { success: 78, time: '3-12', cost: '₹1-5K', similar: 35, won: 65, settled: 20, lost: 15, laws: ['CPA 2019', 'Legal Metrology Act', 'FSSAI Act'] }
  };

  document.getElementById('predictBtn').addEventListener('click', () => {
    const caseType = document.getElementById('predictCaseType').value;
    if (!caseType) { alert(t('alertCaseType')); return; }

    const data = CASE_DATA[caseType] || CASE_DATA.theft;
    const results = document.getElementById('predictResults');
    const lang = getLang();

    document.getElementById('meterSuccess').style.width = data.success + '%';
    document.getElementById('meterSuccessVal').textContent = data.success + '%';
    document.getElementById('predTimeVal').textContent = data.time + (lang === 'hi' ? ' माह' : ' months');
    document.getElementById('predCostVal').textContent = data.cost;
    document.getElementById('predSimilarVal').textContent = data.similar;

    document.getElementById('scWon').style.width = data.won + '%';
    document.getElementById('scWon').innerHTML = `<span>${t('predWon')}</span> ${data.won}%`;
    document.getElementById('scSettled').style.width = data.settled + '%';
    document.getElementById('scSettled').innerHTML = `<span>${t('predSettled')}</span> ${data.settled}%`;
    document.getElementById('scLost').style.width = data.lost + '%';
    document.getElementById('scLost').innerHTML = `<span>${t('predLost')}</span> ${data.lost}%`;

    const lawsDiv = document.getElementById('predLawsList');
    lawsDiv.innerHTML = data.laws.map(l => `<span class="law-tag">${l}</span>`).join('');

    const steps = lang === 'hi'
      ? ['सभी साक्ष्य और दस्तावेज़ एकत्र करें', 'निकटतम थाने में एफ़आईआर दर्ज करें या सम्बन्धित प्राधिकरण में शिकायत दर्ज करें', 'निःशुल्क कानूनी सहायता हेतु नालसा हेल्पलाइन 15100 पर सम्पर्क करें', 'किसी योग्य वकील से परामर्श करें']
      : ['Gather all evidence and documents', 'File FIR at nearest police station or lodge complaint with relevant authority', 'Contact NALSA Helpline 15100 for free legal aid', 'Consult a qualified lawyer for formal advice'];

    document.getElementById('predActionsList').innerHTML = steps.map(s => `<li>${s}</li>`).join('');

    results.style.display = 'block';
    results.scrollIntoView({ behavior: 'smooth' });
  });

  /* ── RISK SCORE ────────────────────────────────────────── */
  const RISK_DATA = {
    theft: { base: 35, laws: ['IPC 378/379', 'CrPC 154', 'IPC 166A'] },
    dv: { base: 55, laws: ['DV Act 2005', 'IPC 498A', 'CrPC 125'] },
    wage: { base: 30, laws: ['Payment of Wages Act', 'Min. Wages Act'] },
    harass: { base: 50, laws: ['POSH Act 2013', 'IPC 354A'] },
    land: { base: 60, laws: ['TPA 1882', 'Registration Act', 'Limitation Act'] },
    cyber: { base: 45, laws: ['IT Act 2000', 'IPC 420', 'IPC 468'] },
    consumer: { base: 25, laws: ['CPA 2019', 'Legal Metrology Act'] }
  };

  document.getElementById('riskCalcBtn').addEventListener('click', () => {
    const category = document.getElementById('riskCategory').value;
    if (!document.getElementById('riskSituation').value.trim()) { alert(t('alertSituation')); return; }

    const rd = RISK_DATA[category] || { base: 40, laws: ['IPC', 'CrPC'] };
    const factors = document.querySelectorAll('input[name="rf"]:checked');
    let score = rd.base + (factors.length * 10);
    score = Math.min(score, 95);

    const lang = getLang();
    const result = document.getElementById('riskResult');
    const circle = document.getElementById('gaugeCircle');

    document.getElementById('gaugeNum').textContent = score;
    circle.classList.remove('low', 'medium', 'high');

    if (score <= 35) {
      circle.classList.add('low');
      document.getElementById('gaugeLabel').textContent = t('riskLow');
    } else if (score <= 65) {
      circle.classList.add('medium');
      document.getElementById('gaugeLabel').textContent = t('riskMedium');
    } else {
      circle.classList.add('high');
      document.getElementById('gaugeLabel').textContent = t('riskHigh');
    }

    document.getElementById('urgencyFill').style.width = Math.min(score + 15, 100) + '%';
    document.getElementById('complexityFill').style.width = Math.min(score, 100) + '%';
    document.getElementById('evidenceFill').style.width = Math.max(100 - score, 10) + '%';

    document.getElementById('riskLawsList').innerHTML = rd.laws.map(l => `<span class="law-tag">${l}</span>`).join('');

    const actions = lang === 'hi'
      ? [
        { title: 'साक्ष्य सुरक्षित करें', desc: 'सभी दस्तावेज़, फ़ोटो, वीडियो, स्क्रीनशॉट और गवाहों के विवरण एकत्र करें।' },
        { title: 'शिकायत दर्ज करें', desc: 'निकटतम थाने में एफ़आईआर दर्ज करें या सम्बन्धित प्राधिकरण में शिकायत करें।' },
        { title: 'कानूनी सहायता लें', desc: 'निःशुल्क कानूनी सहायता हेतु नालसा हेल्पलाइन 15100 या जिला विधिक सेवा प्राधिकरण से सम्पर्क करें।' },
        { title: 'समय सीमा का ध्यान रखें', desc: 'प्रत्येक कानूनी कार्यवाही की एक परिसीमा अवधि होती है। जितना जल्दी हो सके कार्यवाही करें।' }
      ]
      : [
        { title: 'Secure Your Evidence', desc: 'Gather all documents, photos, videos, screenshots, and witness details.' },
        { title: 'File Your Complaint', desc: 'File FIR at nearest police station or lodge complaint with the relevant authority.' },
        { title: 'Get Legal Aid', desc: 'Contact NALSA Helpline 15100 or DLSA for free legal assistance if you cannot afford a lawyer.' },
        { title: 'Mind the Deadline', desc: 'Every legal action has a limitation period. Act as soon as possible to preserve your rights.' }
      ];

    document.getElementById('riskActionsList').innerHTML = actions.map((a, i) =>
      `<li class="action-step"><span class="action-step-num">${i + 1}</span><div class="action-step-text"><strong>${a.title}</strong>${a.desc}</div></li>`
    ).join('');

    const phases = lang === 'hi'
      ? [['शिकायत', '1-2 सप्ताह'], ['जाँच', '1-3 माह'], ['कानूनी कार्यवाही', '3-12 माह'], ['निर्णय', '1-6 माह']]
      : [['File Complaint', '1-2 weeks'], ['Investigation', '1-3 months'], ['Legal Proceedings', '3-12 months'], ['Resolution', '1-6 months']];

    document.getElementById('riskTimelineBar').innerHTML = phases.map((p, i) =>
      `<div class="timeline-phase ${i === 0 ? 'tl-active' : 'tl-pending'}"><div class="timeline-phase-label">${p[0]}</div><div class="timeline-phase-dur">${p[1]}</div></div>`
    ).join('');

    result.style.display = 'block';
    result.scrollIntoView({ behavior: 'smooth' });
  });

  /* ── MY DOCUMENTS (dynamic from backend) ───────────────── */
  function renderDocsList() {
    const docsList = document.querySelector('#page-docs .docs-list');
    if (!docsList) return;

    if (generatedDocs.length === 0) {
      docsList.innerHTML = `<div style="text-align:center;padding:2rem;color:#64748b;">
        ${getLang() === 'hi' ? 'अभी तक कोई दस्तावेज़ नहीं बना। एफ़आईआर विज़ार्ड या चैट से दस्तावेज़ बनाएँ।' :
          'No documents generated yet. Use the FIR Wizard or Chat to generate documents.'}
      </div>`;
      return;
    }

    docsList.innerHTML = generatedDocs.map(doc => `
      <div class="doc-card">
        <div class="doc-icon">&#128196;</div>
        <div class="doc-info">
          <div class="doc-name">${doc.name}</div>
          <div class="doc-meta">${doc.type} &bull; ${doc.date}</div>
        </div>
        <button class="btn btn-outline btn-sm" onclick="window.open('${doc.url}', '_blank')">${t('firDownload')}</button>
      </div>
    `).join('');
  }

  /* ── FILTER BUTTONS ────────────────────────────────────── */
  document.querySelectorAll('.filter-row').forEach(row => {
    row.addEventListener('click', e => {
      if (e.target.classList.contains('filter-btn')) {
        row.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
      }
    });
  });

  /* ── CLEAR DATA ────────────────────────────────────────── */
  document.getElementById('clearDataBtn').addEventListener('click', () => {
    const msg = getLang() === 'hi' ? 'क्या आप वाकई सारा डेटा मिटाना चाहते हैं?' : 'Are you sure you want to clear all data?';
    if (confirm(msg)) { try { localStorage.clear(); } catch (_) { } location.reload(); }
  });

  /* ── OFFLINE DETECTION ─────────────────────────────────── */
  function updateOnline() { offlineBanner.style.display = navigator.onLine ? 'none' : 'block'; }
  window.addEventListener('online', updateOnline);
  window.addEventListener('offline', updateOnline);
  updateOnline();

  /* ── LANDING, AUTH, DEMO TOUR ─────────────────────────── */
  const landingScreen = document.getElementById('landingScreen');
  const getStartedBtn = document.getElementById('getStartedBtn');
  const liveDemoBtn = document.getElementById('liveDemoBtn');
  const landingLangToggle = document.getElementById('landingLangToggle');
  const authModal = document.getElementById('authModal');
  const authCloseBtn = document.getElementById('authCloseBtn');
  const authLoginTab = document.getElementById('authLoginTab');
  const authSignupTab = document.getElementById('authSignupTab');
  const authLoginForm = document.getElementById('authLoginForm');
  const authSignupForm = document.getElementById('authSignupForm');
  const authLoginBtn = document.getElementById('authLoginBtn');
  const authSignupBtn = document.getElementById('authSignupBtn');
  const userNameDisplay = document.getElementById('userNameDisplay');
  const demoTour = document.getElementById('demoTour');
  const demoTourStepIndicator = document.getElementById('demoTourStepIndicator');
  const demoTourNext = document.getElementById('demoTourNext');
  const demoTourSkip = document.getElementById('demoTourSkip');
  const demoTourFinish = document.getElementById('demoTourFinish');
  const demoStepPanels = document.querySelectorAll('.demo-step-panel');

  function enterMainApp() {
    if (landingScreen) landingScreen.style.display = 'none';
    if (sidebar) sidebar.style.display = '';
    if (mainContent) mainContent.style.display = '';
    if (mobileHeader) mobileHeader.style.display = '';
  }

  function openAuthModal() {
    if (authModal) authModal.classList.add('auth-modal-open');
  }
  function closeAuthModal() {
    if (authModal) authModal.classList.remove('auth-modal-open');
  }

  if (getStartedBtn) {
    getStartedBtn.addEventListener('click', () => {
      enterMainApp();
      openAuthModal();
    });
  }

  let demoStep = 1;
  function showDemoStep(n) {
    demoStep = n;
    demoStepPanels.forEach(p => {
      p.style.display = p.getAttribute('data-demo-step') === String(n) ? 'block' : 'none';
    });
    if (demoTourStepIndicator) demoTourStepIndicator.textContent = n + ' / 5';
    const last = n >= 5;
    if (demoTourNext) demoTourNext.style.display = last ? 'none' : '';
    if (demoTourFinish) demoTourFinish.style.display = last ? '' : 'none';
  }

  function openDemoTour() {
    enterMainApp();
    demoStep = 1;
    showDemoStep(1);
    if (demoTour) demoTour.style.display = 'flex';
  }

  function closeDemoTour() {
    if (demoTour) demoTour.style.display = 'none';
  }

  if (liveDemoBtn) liveDemoBtn.addEventListener('click', () => openDemoTour());

  if (landingLangToggle) {
    landingLangToggle.querySelectorAll('button[data-landing-lang]').forEach(btn => {
      btn.addEventListener('click', () => switchLang(btn.getAttribute('data-landing-lang')));
    });
  }

  if (authCloseBtn) authCloseBtn.addEventListener('click', closeAuthModal);

  if (authLoginTab && authSignupTab && authLoginForm && authSignupForm) {
    authLoginTab.addEventListener('click', () => {
      authLoginTab.classList.add('active');
      authSignupTab.classList.remove('active');
      authLoginForm.style.display = '';
      authSignupForm.style.display = 'none';
    });
    authSignupTab.addEventListener('click', () => {
      authSignupTab.classList.add('active');
      authLoginTab.classList.remove('active');
      authSignupForm.style.display = '';
      authLoginForm.style.display = 'none';
    });
  }

  function setUserGreetingFromAuth(nameOrEmail) {
    const v = (nameOrEmail || '').trim();
    if (!userNameDisplay) return;
    if (v) {
      userNameDisplay.removeAttribute('data-i18n');
      userNameDisplay.textContent = v;
      userId = v.replace(/[^a-zA-Z0-9_]/g, '_').substring(0, 20);
      localStorage.setItem('nyayavoice_user_id', userId);
    } else {
      userNameDisplay.setAttribute('data-i18n', 'anonUser');
      userNameDisplay.textContent = t('anonUser');
    }
  }

  if (authLoginBtn) {
    authLoginBtn.addEventListener('click', () => {
      const email = document.getElementById('authLoginEmail');
      setUserGreetingFromAuth(email && email.value ? email.value.split('@')[0] : '');
      closeAuthModal();
    });
  }
  if (authSignupBtn) {
    authSignupBtn.addEventListener('click', () => {
      const nameEl = document.getElementById('authSignupName');
      setUserGreetingFromAuth(nameEl && nameEl.value ? nameEl.value : '');
      closeAuthModal();
    });
  }

  document.querySelectorAll('.auth-forgot').forEach(a => {
    a.addEventListener('click', e => e.preventDefault());
  });

  if (demoTourNext) {
    demoTourNext.addEventListener('click', () => {
      if (demoStep < 5) showDemoStep(demoStep + 1);
    });
  }
  if (demoTourSkip) demoTourSkip.addEventListener('click', closeDemoTour);
  if (demoTourFinish) demoTourFinish.addEventListener('click', closeDemoTour);

  /* ── INTERACTIVE UI ENHANCEMENTS ────────────────────────── */
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.card, .stat-card, .accord-item, .helpline-card, .doc-card, .quick-action-card').forEach(el => {
    el.classList.add('animate-target');
    observer.observe(el);
  });

  document.querySelectorAll('.btn-primary, .btn-outline, .send-btn, .landing-btn').forEach(btn => {
    btn.addEventListener('click', function (e) {
      const ripple = document.createElement('span');
      ripple.className = 'btn-ripple';
      const rect = this.getBoundingClientRect();
      ripple.style.left = (e.clientX - rect.left) + 'px';
      ripple.style.top = (e.clientY - rect.top) + 'px';
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    });
  });

  /* ── User ID display in settings ───────────────────────── */
  const userIdDisplay = document.getElementById('userIdDisplay');
  if (userIdDisplay) userIdDisplay.textContent = userId;

  /* ── TTS TOGGLE BUTTON ─────────────────────────────────── */
  const ttsToggleBtn = document.getElementById('ttsToggleBtn');
  if (ttsToggleBtn) {
    ttsToggleBtn.addEventListener('click', () => {
      ttsEnabled = !ttsEnabled;
      ttsToggleBtn.textContent = ttsEnabled ? '🔊' : '🔇';
      ttsToggleBtn.title = ttsEnabled ? 'Voice response ON' : 'Voice response OFF';
      if (!ttsEnabled) stopSpeech();
    });
  }

  /* ── INIT ──────────────────────────────────────────────── */
  initTheme();
  initLang();
  const savedLang = getLang();
  [langSwitch, langMobile, settingsLang].forEach(sel => { if (sel) sel.value = savedLang; });
  updateStats();
  initVapi();

})();
