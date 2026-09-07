import React, { useState, useEffect, useRef } from 'react';
import { Business, Workflow, ChatMessage } from '../types';
import { sendChatMessage, generateTTS } from '../lib/api';

interface PhoneSimulatorProps {
  businesses: Business[];
  workflows: Workflow[];
  selectedLanguage: string;
  initialWorkflowId?: string;
}

// Cleans text of markdown, technical tokens, parentheticals, and emojis for human-sounding speech
const cleanTextForSpeech = (rawText: string): string => {
  if (!rawText) return '';
  return rawText
    .replace(/^\*\([^*]+\)\*\s*/g, '')
    .replace(/\([A-Za-z\s]+switched to[^\)]+\)/gi, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/#+\s*/g, '')
    .replace(/^[ \t]*[-*+]\s+/gm, '')
    .replace(/`[^`]*`/g, '')
    .replace(/\bINR\s*(\d+)/gi, '$1 rupees')
    .replace(/\bRs\.?\s*(\d+)/gi, '$1 rupees')
    .replace(/\b(\d+)\s*kg\b/gi, '$1 kilograms')
    .replace(/TRK-([A-Za-z0-9-]+)/gi, 'tracking number $1')
    .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')
    .replace(/[✓✔✕✖•●★☆🍰🎂🚚📦📞🤖👤🗓️📅🔄⚠️]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
};

export const PhoneSimulator: React.FC<PhoneSimulatorProps> = ({
  businesses,
  workflows,
  selectedLanguage,
  initialWorkflowId
}) => {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>(
    initialWorkflowId || workflows[0]?.id || 'wf-cake-01'
  );

  const activeWorkflow = workflows.find(w => w.id === selectedWorkflowId) || workflows[0];
  const activeBusiness = businesses.find(b => b.id === activeWorkflow?.business_id) || businesses[0];

  // Call State
  const [callState, setCallState] = useState<'idle' | 'ringing' | 'active' | 'ended'>('idle');
  const [callerName, setCallerName] = useState('Ankit Mehta');
  const [callerPhone, setCallerPhone] = useState('+91 98765 12345');
  const [isHandsFree, setIsHandsFree] = useState<boolean>(true);

  // Conversation State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState<string>('');
  const [voiceActivityState, setVoiceActivityState] = useState<'idle' | 'listening' | 'speaking' | 'processing'>('idle');
  const [lastExecutedTools, setLastExecutedTools] = useState<any[]>([]);
  const [currentRecordId, setCurrentRecordId] = useState<string | null>(null);
  const [collectedData, setCollectedData] = useState<Record<string, any>>({});
  const [activeUrgency, setActiveUrgency] = useState<string>('Normal');
  const [activeLanguage, setActiveLanguage] = useState<string>('en');
  const [languageSwitchNotice, setLanguageSwitchNotice] = useState<string | null>(null);
  const [micStatusNotice, setMicStatusNotice] = useState<string | null>(null);

  // Audio Playback & Mic Recording Refs (Guards against state closure race conditions)
  const callStateRef = useRef(callState);
  const isHandsFreeRef = useRef(isHandsFree);
  const isPlayingAudioRef = useRef(false);
  const isProcessingRef = useRef(false);
  const isMicMutedByUserRef = useRef(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const restartTimerRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  useEffect(() => {
    isHandsFreeRef.current = isHandsFree;
    if (callState === 'active' && isHandsFree && !isPlayingAudioRef.current && !isProcessingRef.current && !isRecording) {
      startContinuousListening();
    }
  }, [isHandsFree, callState]);

  useEffect(() => {
    if (initialWorkflowId) {
      setSelectedWorkflowId(initialWorkflowId);
    }
  }, [initialWorkflowId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveTranscript, isProcessing]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopMicOnly();
      if (audioRef.current) {
        try { audioRef.current.pause(); } catch (e) {}
      }
      if ('speechSynthesis' in window) {
        try { window.speechSynthesis.cancel(); } catch (e) {}
      }
    };
  }, []);

  // Natural Browser Speech Synthesis Fallback (guarantees voice output if server audio is blocked/offline)
  const speakBrowserFallback = (text: string, lang: string, onDone: () => void) => {
    if (!('speechSynthesis' in window)) {
      onDone();
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(cleanTextForSpeech(text));
      const voices = window.speechSynthesis.getVoices();
      
      const langPrefix = lang === 'hi' ? 'hi' : (lang === 'kn' ? 'kn' : 'en');
      const naturalVoice = voices.find(v => 
        v.lang.toLowerCase().startsWith(langPrefix) && 
        (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Neural') || v.name.includes('Online'))
      ) || voices.find(v => v.lang.toLowerCase().startsWith(langPrefix)) || voices[0];

      if (naturalVoice) utterance.voice = naturalVoice;
      utterance.rate = 0.96; // Conversational human pace
      utterance.pitch = 1.0;
      utterance.lang = lang === 'hi' ? 'hi-IN' : (lang === 'kn' ? 'kn-IN' : 'en-IN');

      utterance.onend = () => { onDone(); };
      utterance.onerror = () => { onDone(); };

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      onDone();
    }
  };

  // Safely stop only the microphone recognition without ending call session
  const stopMicOnly = () => {
    clearTimeout(restartTimerRef.current);
    clearTimeout(silenceTimerRef.current);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.onend = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onresult = null;
        recognitionRef.current.abort();
      } catch (e) {}
      recognitionRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop(); } catch (e) {}
    }
    setIsRecording(false);
    setLiveTranscript('');
  };

  // Continuous Hands-Free Listening Loop
  const startContinuousListening = () => {
    // Only listen if call is active and bot is not speaking/thinking
    if (callStateRef.current !== 'active' || isPlayingAudioRef.current || isProcessingRef.current || isMicMutedByUserRef.current) {
      return;
    }

    stopMicOnly();

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      // Fallback to HTML5 MediaRecorder
      startMediaRecorderFallback();
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;
      recognition.continuous = false; // Fast boundary detection with auto-restart loop delivers infinite continuous listening
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      // Accurate language code mapping
      const targetLang = activeLanguage === 'kn' ? 'kn-IN' : (activeLanguage === 'hi' ? 'hi-IN' : 'en-IN');
      recognition.lang = targetLang;

      recognition.onstart = () => {
        setIsRecording(true);
        setVoiceActivityState('listening');
        setMicStatusNotice(null);
      };

      let finalCaptured = false;

      recognition.onresult = (event: any) => {
        let interim = '';
        let finalStr = '';

        for (let i = 0; i < event.results.length; ++i) {
          const item = event.results[i];
          if (item.isFinal) {
            finalStr += item[0].transcript;
          } else {
            interim += item[0].transcript;
          }
        }

        if (interim.trim()) {
          setLiveTranscript(interim.trim());
          // If speaker pauses after interim speech, automatically trigger after 1.5s silence
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => {
            if (interim.trim() && callStateRef.current === 'active' && !isProcessingRef.current && !finalCaptured) {
              finalCaptured = true;
              stopMicOnly();
              handleSendMessage(interim.trim());
            }
          }, 1500);
        }

        if (finalStr.trim()) {
          finalCaptured = true;
          clearTimeout(silenceTimerRef.current);
          setLiveTranscript('');
          stopMicOnly();
          handleSendMessage(finalStr.trim());
        }
      };

      recognition.onerror = (event: any) => {
        const err = event?.error;
        // 'no-speech' or 'aborted' is expected when caller is thinking/pausing
        if (err === 'no-speech' || err === 'aborted') {
          return;
        }
        if (err === 'not-allowed' || err === 'audio-capture') {
          setMicStatusNotice('Microphone access blocked. Please allow mic in browser settings.');
        }
      };

      recognition.onend = () => {
        setIsRecording(false);
        recognitionRef.current = null;

        // CONTINUOUS TURN-TAKING AUTO-RESTART:
        // Automatically restart listening if call is active and assistant is not speaking/processing
        if (
          callStateRef.current === 'active' &&
          isHandsFreeRef.current &&
          !isMicMutedByUserRef.current &&
          !isPlayingAudioRef.current &&
          !isProcessingRef.current &&
          !finalCaptured
        ) {
          clearTimeout(restartTimerRef.current);
          restartTimerRef.current = setTimeout(() => {
            if (
              callStateRef.current === 'active' &&
              !isPlayingAudioRef.current &&
              !isProcessingRef.current &&
              !isMicMutedByUserRef.current
            ) {
              startContinuousListening();
            }
          }, 150);
        }
      };

      recognition.start();
    } catch (err) {
      console.warn('SpeechRecognition error, scheduling retry:', err);
      if (callStateRef.current === 'active' && isHandsFreeRef.current && !isPlayingAudioRef.current) {
        clearTimeout(restartTimerRef.current);
        restartTimerRef.current = setTimeout(startContinuousListening, 600);
      }
    }
  };

  // MediaRecorder Fallback if Web Speech Recognition is absent
  const startMediaRecorderFallback = () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicStatusNotice('Microphone not supported in this browser. Please use text input.');
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        const audioBlob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType || 'audio/webm' });
        if (audioBlob.size > 0 && callStateRef.current === 'active') {
          try {
            isProcessingRef.current = true;
            setIsProcessing(true);
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');
            const sttRes = await fetch('/api/ai/stt', { method: 'POST', body: formData });
            const sttJson = await sttRes.json();
            if (sttJson.success && sttJson.data?.text) {
              handleSendMessage(sttJson.data.text);
            } else if (callStateRef.current === 'active' && isHandsFreeRef.current) {
              startContinuousListening();
            }
          } catch (err) {
            if (callStateRef.current === 'active' && isHandsFreeRef.current) {
              startContinuousListening();
            }
          } finally {
            isProcessingRef.current = false;
            setIsProcessing(false);
          }
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      setVoiceActivityState('listening');

      // 4-second chunking for fallback
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, 4000);
    }).catch(() => {
      setMicStatusNotice('Microphone permission required for voice calls.');
    });
  };

  // Start Call Simulation (Auto-starts continuous turn-taking)
  const startCall = () => {
    setCallState('ringing');
    setCurrentRecordId(null);
    setCollectedData({});
    setMessages([]);
    setLastExecutedTools([]);
    setActiveUrgency('Normal');
    setActiveLanguage('en');
    setLanguageSwitchNotice(null);
    setMicStatusNotice(null);
    setLiveTranscript('');
    isMicMutedByUserRef.current = false;

    setTimeout(() => {
      setCallState('active');
      callStateRef.current = 'active';
      isHandsFreeRef.current = true;
      setIsHandsFree(true);

      const initialGreeting: ChatMessage = {
        role: 'assistant',
        content: activeWorkflow?.greeting || 'Hello! Thank you for calling. We missed your call.'
      };
      setMessages([initialGreeting]);
      // Speak greeting, then automatically activate continuous microphone
      speakText(initialGreeting.content, 'en');
    }, 1200);
  };

  const endCall = () => {
    setCallState('ended');
    callStateRef.current = 'ended';
    setVoiceActivityState('idle');
    stopMicOnly();
    if (audioRef.current) {
      try { audioRef.current.pause(); } catch (e) {}
    }
    if ('speechSynthesis' in window) {
      try { window.speechSynthesis.cancel(); } catch (e) {}
    }
    setIsPlayingAudio(false);
    setIsRecording(false);
    setIsProcessing(false);
    setLiveTranscript('');
  };

  // Speak AI text with ultra-natural human voice and automatically resume continuous listening
  const speakText = async (text: string, languageOverride?: string) => {
    // 1. Mute microphone during speech to prevent audio echo loop
    stopMicOnly();

    isPlayingAudioRef.current = true;
    setIsPlayingAudio(true);
    setVoiceActivityState('speaking');

    const cleanSpeech = cleanTextForSpeech(text);
    const targetLang = languageOverride || (selectedLanguage === 'auto' ? activeLanguage : selectedLanguage);
    const lang = targetLang === 'kn' ? 'kn' : (targetLang === 'hi' ? 'hi' : 'en');

    const onSpeechFinished = () => {
      isPlayingAudioRef.current = false;
      setIsPlayingAudio(false);

      // AUTOMATICALLY RESUME LISTENING: User never has to click mic again!
      if (callStateRef.current === 'active' && isHandsFreeRef.current && !isMicMutedByUserRef.current) {
        setVoiceActivityState('listening');
        clearTimeout(restartTimerRef.current);
        // Buffer 350ms to allow room echo to decay before mic opens
        restartTimerRef.current = setTimeout(() => {
          if (callStateRef.current === 'active' && !isPlayingAudioRef.current && !isProcessingRef.current) {
            startContinuousListening();
          }
        }, 350);
      } else {
        setVoiceActivityState('idle');
      }
    };

    try {
      const ttsData = await generateTTS(cleanSpeech, lang);

      if (ttsData?.audio_base64) {
        const audioSrc = `data:${ttsData.format || 'audio/wav'};base64,${ttsData.audio_base64}`;
        if (!audioRef.current) {
          audioRef.current = new Audio(audioSrc);
        } else {
          audioRef.current.pause();
          audioRef.current.src = audioSrc;
        }

        audioRef.current.onended = () => {
          onSpeechFinished();
        };

        audioRef.current.onerror = () => {
          console.warn('Audio element error, utilizing natural browser speech fallback');
          speakBrowserFallback(cleanSpeech, lang, onSpeechFinished);
        };

        await audioRef.current.play();
      } else {
        speakBrowserFallback(cleanSpeech, lang, onSpeechFinished);
      }
    } catch (err) {
      console.warn('Server TTS error, using natural client voice synthesis:', err);
      speakBrowserFallback(cleanSpeech, lang, onSpeechFinished);
    }
  };

  // Submit turn message and orchestrate next AI turn
  const handleSendMessage = async (customText?: string) => {
    const textToSend = customText || inputMessage;
    if (!textToSend.trim() || isProcessingRef.current || !activeWorkflow) return;

    stopMicOnly();
    isProcessingRef.current = true;
    setIsProcessing(true);
    setVoiceActivityState('processing');
    setInputMessage('');
    setLiveTranscript('');

    const userMsg: ChatMessage = { role: 'user', content: textToSend };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setLanguageSwitchNotice(null);

    try {
      const response = await sendChatMessage({
        business_id: activeBusiness.id,
        workflow_id: activeWorkflow.id,
        caller_name: callerName,
        caller_phone: callerPhone,
        language: selectedLanguage,
        messages: updatedMessages,
        record_id: currentRecordId || undefined
      });

      if (response.record_id) {
        setCurrentRecordId(response.record_id);
      }
      if (response.collected_data) {
        setCollectedData(response.collected_data);
      }

      const assistantMsg: ChatMessage = { role: 'assistant', content: response.assistant_reply };
      setMessages([...updatedMessages, assistantMsg]);
      setLastExecutedTools(response.executed_tools || []);
      if (response.urgency) setActiveUrgency(response.urgency);
      if (response.language) setActiveLanguage(response.language);

      // Natural language switch banner
      if (response.language_switched) {
        const switchLog = (response.executed_tools || []).find((t: any) => t.tool === 'language_switch_detected');
        if (switchLog && switchLog.args) {
          setLanguageSwitchNotice(`🔄 Language Switch: ${switchLog.args.from} ➔ ${switchLog.args.to}`);
        } else {
          setLanguageSwitchNotice(`🔄 Dynamic Language Switch Detected!`);
        }
      }

      isProcessingRef.current = false;
      setIsProcessing(false);

      // Speak AI response with human-like voice; continuous listening automatically resumes when done
      await speakText(response.assistant_reply, response.language);
    } catch (err: any) {
      isProcessingRef.current = false;
      setIsProcessing(false);
      setVoiceActivityState('idle');
      alert(`AI Call Error: ${err.message}`);
      // Resume listening so call does not freeze on network glitch
      if (callStateRef.current === 'active' && isHandsFreeRef.current) {
        startContinuousListening();
      }
    }
  };

  // Manual Mic Toggle (Mute/Unmute without dropping the call)
  const toggleRecording = () => {
    if (callState !== 'active') {
      startCall();
      return;
    }
    if (isRecording) {
      isMicMutedByUserRef.current = true;
      stopMicOnly();
      setMicStatusNotice('Microphone paused. Click again to resume continuous voice listening.');
    } else {
      isMicMutedByUserRef.current = false;
      setMicStatusNotice(null);
      startContinuousListening();
    }
  };

  const getLanguageBadge = (lang: string) => {
    switch (lang) {
      case 'hi':
        return { label: 'Hindi (हिन्दी)', class: 'bg-orange-500/20 text-orange-300 border-orange-500/30' };
      case 'kn':
        return { label: 'Kannada (ಕನ್ನಡ)', class: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' };
      default:
        return { label: 'English (EN)', class: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' };
    }
  };

  const langInfo = getLanguageBadge(activeLanguage);

  return (
    <div className="space-y-8">
      {/* Header & Scenario Selector */}
      <div className="glass-panel p-5 flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-phone text-indigo-400" />
            Real-Time Live Voice Phone Simulator
          </h2>
          <p className="text-xs text-slate-400">Continuous hands-free phone conversation with sub-300ms Groq LPU LLM & Sarvam AI voice synthesis</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Hands-Free Live Call Toggle */}
          <label className="flex items-center gap-2 bg-slate-900 border border-white/10 px-3 py-1.5 rounded-xl text-xs font-semibold cursor-pointer">
            <input
              type="checkbox"
              checked={isHandsFree}
              onChange={(e) => setIsHandsFree(e.target.checked)}
              className="rounded border-white/20 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
            />
            <span className={isHandsFree ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
              {isHandsFree ? '🎙️ Hands-Free Live Call ON' : 'Manual Mic Mode'}
            </span>
          </label>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Workflow Scenario:</span>
            <select
              value={selectedWorkflowId}
              onChange={(e) => {
                setSelectedWorkflowId(e.target.value);
                setCallState('idle');
                setMessages([]);
              }}
              className="bg-slate-900 border border-white/10 text-xs font-bold rounded-xl px-3 py-2 text-indigo-300 focus:outline-none focus:border-indigo-500 cursor-pointer"
            >
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.industry})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Main Simulator Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Config Controls */}
        <div className="lg:col-span-4 space-y-4">

          {/* Caller Details Config */}
          <div className="glass-panel p-5 space-y-3">
            <h3 className="text-xs font-bold text-slate-300 uppercase">Simulated Caller Profile</h3>
            <div className="space-y-2">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Caller Name</label>
                <input
                  type="text"
                  value={callerName}
                  onChange={(e) => setCallerName(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Caller Phone Number</label>
                <input
                  type="text"
                  value={callerPhone}
                  onChange={(e) => setCallerPhone(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* Live Database Fields Tracking Card */}
          <div className="glass-panel p-5 space-y-3 border border-indigo-500/30 shadow-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-slate-200 uppercase flex items-center gap-1.5">
                <i className="fa-solid fa-database text-indigo-400" /> Database Fields (Live)
              </h3>
              {currentRecordId && (
                <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-500/40">
                  {currentRecordId}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400">
              Questions asked dynamically per workflow schema. Data is saved in SQLite <code className="text-indigo-300">records.collected_data</code>.
            </p>

            {/* Dynamic Field Progress & List */}
            {(() => {
              const allFields = activeWorkflow?.fields || [];
              const reqFields = allFields.filter(f => f.required);
              const filledReqCount = reqFields.filter(f => !!collectedData[f.key]).length;
              const percent = reqFields.length > 0 ? Math.round((filledReqCount / reqFields.length) * 100) : 100;
              const isAllDone = percent === 100 && reqFields.length > 0;

              return (
                <div className="space-y-3 pt-1">
                  <div>
                    <div className="flex justify-between text-[11px] mb-1 font-semibold">
                      <span className="text-slate-300">Required Fields Captured</span>
                      <span className={isAllDone ? "text-emerald-400 font-bold" : "text-amber-400"}>
                        {filledReqCount} / {reqFields.length} ({percent}%)
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-white/10">
                      <div
                        className={`h-full transition-all duration-500 ${isAllDone ? 'bg-gradient-to-r from-emerald-500 to-teal-400' : 'bg-gradient-to-r from-indigo-500 to-amber-500'}`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>

                  {isAllDone && (
                    <div className="bg-emerald-950/40 border border-emerald-500/40 px-3 py-2 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
                      <i className="fa-solid fa-circle-check text-emerald-400 text-sm flex-shrink-0" />
                      <div>
                        <div className="font-bold">All Database Fields Captured!</div>
                        <div className="text-[10px] text-emerald-400/80">Workflow completion tools executed & saved to SQLite database.</div>
                      </div>
                    </div>
                  )}

                  {/* Individual Fields List */}
                  <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                    {allFields.map((field) => {
                      const val = collectedData[field.key];
                      const isFilled = val !== undefined && val !== null && val !== '';

                      return (
                        <div
                          key={field.key}
                          className={`p-2.5 rounded-xl border text-xs transition-all ${
                            isFilled
                              ? 'bg-slate-900/90 border-emerald-500/50 shadow-sm'
                              : field.required
                              ? 'bg-slate-900/50 border-amber-500/30'
                              : 'bg-slate-900/30 border-white/5'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-semibold text-slate-200 text-[11px] flex items-center gap-1">
                              {field.label}
                              {field.required && <span className="text-amber-400 font-bold" title="Required">*</span>}
                            </span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 ${
                              isFilled
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : field.required
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse'
                                : 'bg-slate-800 text-slate-400'
                            }`}>
                              {isFilled ? '✓ Stored' : field.required ? 'Pending Question' : 'Optional'}
                            </span>
                          </div>

                          <div className="mt-1 text-[11px]">
                            {isFilled ? (
                              <span className="font-mono text-emerald-400 font-semibold truncate block">
                                {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                              </span>
                            ) : (
                              <span className="text-slate-500 italic text-[10px]">
                                {field.required ? 'AI will ask caller for this field...' : 'Optional field'}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>

        {/* Center & Right Column: Interactive Phone Device Frame */}
        <div className="lg:col-span-8">
          <div className="glass-panel p-3.5 sm:p-6 max-w-2xl mx-auto border-2 border-indigo-500/30 shadow-2xl relative">
            {/* Phone Top Notch & Status */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-white/10 pb-4 mb-4 gap-3">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full flex-shrink-0 ${callState === 'active' ? 'bg-emerald-500 animate-ping' : callState === 'ringing' ? 'bg-amber-500 animate-pulse' : 'bg-slate-600'}`} />
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-white truncate">
                    {activeBusiness?.name || 'Voice Assistant'}
                  </h3>
                  <p className="text-[11px] text-indigo-300 truncate">{activeWorkflow?.name}</p>
                </div>
              </div>

              <div className="flex items-center flex-wrap gap-2 w-full sm:w-auto justify-between sm:justify-end">
                <div className="flex items-center gap-2">
                  {/* Active Detected Language Badge */}
                  <span className={`px-2.5 py-1 rounded text-[10px] font-bold border flex items-center gap-1 ${langInfo.class}`}>
                    <i className="fa-solid fa-language" /> {langInfo.label}
                  </span>

                  {activeUrgency !== 'Normal' && (
                    <span className="px-2 py-1 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                      <i className="fa-solid fa-triangle-exclamation" /> {activeUrgency}
                    </span>
                  )}
                </div>

                {callState === 'idle' && (
                  <button
                    onClick={startCall}
                    className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-lg shadow-emerald-500/25 transition-all cursor-pointer"
                  >
                    <i className="fa-solid fa-phone" /> Start Live Voice Call
                  </button>
                )}

                {callState === 'ringing' && (
                  <span className="text-xs font-bold text-amber-300 animate-pulse">
                    <i className="fa-solid fa-phone-volume mr-1" /> Call Connected...
                  </span>
                )}

                {callState === 'active' && (
                  <button
                    onClick={endCall}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 text-rose-200 border border-rose-500/30 text-xs font-bold transition-all cursor-pointer"
                  >
                    <i className="fa-solid fa-phone-slash" /> End Call
                  </button>
                )}
              </div>
            </div>

            {/* Dynamic Natural Language Switch Banner Notice */}
            {languageSwitchNotice && (
              <div className="bg-gradient-to-r from-indigo-950 to-slate-900 p-2.5 rounded-xl border border-indigo-500/40 mb-4 flex items-center justify-between text-xs text-indigo-200 animate-bounce">
                <span className="font-bold flex items-center gap-2">
                  <i className="fa-solid fa-arrows-rotate text-indigo-300" />
                  {languageSwitchNotice}
                </span>
                <span className="text-[10px] text-indigo-300">Sarvam AI / ElevenLabs voice updated</span>
              </div>
            )}

            {/* Continuous Voice Session Active Notification */}
            {callState === 'active' && isHandsFree && (
              <div className="bg-emerald-950/40 border border-emerald-500/30 px-3.5 py-2 rounded-xl mb-4 flex items-center justify-between text-xs text-emerald-200">
                <span className="flex items-center gap-2 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  🎙️ Continuous Voice Testing Active: Mic stays ON after each AI reply. Speak turn-by-turn hands-free!
                </span>
                <span className="text-[10px] text-emerald-400 font-bold bg-emerald-900/50 px-2 py-0.5 rounded-lg border border-emerald-500/20">
                  Turn-by-Turn
                </span>
              </div>
            )}

            {/* Microphone Status / Guidance Notice */}
            {micStatusNotice && (
              <div className="bg-slate-900/90 p-2.5 rounded-xl border border-amber-500/30 mb-4 flex items-center justify-between text-xs text-amber-200 animate-fade-in">
                <span className="font-semibold flex items-center gap-2">
                  <i className="fa-solid fa-info-circle text-amber-400" />
                  {micStatusNotice}
                </span>
                <button onClick={() => setMicStatusNotice(null)} className="text-slate-400 hover:text-white text-xs">✕</button>
              </div>
            )}

            {/* Audio Waveform Equalizer & Live Voice Status */}
            {(isPlayingAudio || isRecording || isProcessing || liveTranscript) && (
              <div className="bg-gradient-to-r from-slate-900 via-indigo-950/80 to-slate-900 p-3.5 rounded-2xl border border-indigo-500/40 mb-4 flex items-center justify-between shadow-xl">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full border flex items-center justify-center animate-pulse ${
                    isPlayingAudio
                      ? 'bg-indigo-500/20 border-indigo-400/40 text-indigo-400'
                      : isRecording
                      ? 'bg-emerald-500/20 border-emerald-400/40 text-emerald-400'
                      : 'bg-amber-500/20 border-amber-400/40 text-amber-400'
                  }`}>
                    <i className={`fa-solid text-sm ${
                      isPlayingAudio ? 'fa-volume-high' : isRecording ? 'fa-microphone' : 'fa-spinner animate-spin'
                    }`} />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-white block">
                      {isPlayingAudio
                        ? `AI Assistant Speaking (Human Voice • ${langInfo.label})`
                        : liveTranscript
                        ? `Hearing: "${liveTranscript}..."`
                        : isRecording
                        ? `🎙️ Listening... Continuous Session Active (Speak your reply)`
                        : `AI Assistant thinking & checking tools...`}
                    </span>
                    <span className="text-[10px] text-indigo-300">
                      {isPlayingAudio
                        ? 'Natural speech streaming • Mic temporarily paused to prevent echo'
                        : isRecording
                        ? 'Hands-free continuous mode • Mic remains active turn-by-turn'
                        : 'Evaluating conversation state & executing tools'}
                    </span>
                  </div>
                </div>
                {/* 8-Bar Dynamic Equalizer */}
                <div className="flex items-center gap-1.5 h-8 px-2 bg-slate-950/60 rounded-xl border border-indigo-500/20">
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-indigo-500' : isRecording ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-blue-400' : isRecording ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-indigo-400' : isRecording ? 'bg-cyan-400' : 'bg-amber-400'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-purple-500' : isRecording ? 'bg-emerald-400' : 'bg-amber-300'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-indigo-500' : isRecording ? 'bg-teal-400' : 'bg-amber-500'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-blue-500' : isRecording ? 'bg-emerald-500' : 'bg-amber-400'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-cyan-400' : isRecording ? 'bg-cyan-400' : 'bg-amber-300'}`} />
                  <div className={`w-1.5 eq-bar ${isPlayingAudio ? 'bg-indigo-400' : isRecording ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                </div>
              </div>
            )}

            {/* Executed Tools Live Badges */}
            {lastExecutedTools.length > 0 && (
              <div className="mb-4 space-y-1.5">
                <div className="text-[10px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1">
                  <i className="fa-solid fa-calendar-days text-indigo-400" /> Real-time Tool Calling Executed:
                </div>
                <div className="flex flex-wrap gap-2">
                  {lastExecutedTools.map((t, idx) => (
                    <div key={idx} className="bg-slate-900 border border-indigo-500/30 px-3 py-1.5 rounded-lg text-xs font-mono text-indigo-200 flex items-center gap-2">
                      <span className="text-emerald-400">✓ {t.tool}</span>
                      <span className="text-[10px] text-slate-400">({JSON.stringify(t.args)})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Chat Transcript Area */}
            <div className="bg-slate-900/90 rounded-2xl p-4 min-h-[320px] max-h-[420px] overflow-y-auto border border-white/5 space-y-3">
              {messages.length === 0 ? (
                <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-xs space-y-2">
                  <i className="fa-solid fa-phone-slash text-3xl text-slate-600 animate-bounce" />
                  <p>Click "Start Live Voice Call" or start speaking to initiate the phone call!</p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-2xl max-w-[85%] text-xs space-y-1 ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white ml-auto rounded-br-none shadow-md shadow-indigo-500/20'
                        : 'bg-slate-800 border border-white/10 text-slate-200 mr-auto rounded-bl-none'
                    }`}
                  >
                    <div className="text-[10px] font-bold text-slate-400 flex items-center justify-between">
                      <span>{msg.role === 'user' ? `👤 ${callerName}` : `🤖 AI Voice Assistant`}</span>
                      {msg.role === 'assistant' && (
                        <button
                          onClick={() => speakText(msg.content)}
                          className="hover:text-indigo-300"
                          title="Replay Voice Audio"
                        >
                          <i className="fa-solid fa-volume-high" />
                        </button>
                      )}
                    </div>
                    <div className="leading-relaxed">{msg.content}</div>
                  </div>
                ))
              )}
              {/* Live Speech Interim Bubble */}
              {liveTranscript && isRecording && (
                <div className="bg-emerald-950/60 border border-emerald-500/30 text-emerald-200 p-3 rounded-2xl ml-auto rounded-br-none text-xs flex items-center gap-2 max-w-[85%] animate-pulse">
                  <i className="fa-solid fa-microphone text-emerald-400 text-xs" />
                  <span className="font-semibold text-emerald-300">Hearing:</span>
                  <span>"{liveTranscript}..."</span>
                </div>
              )}
              {isProcessing && (
                <div className="bg-slate-800 border border-white/10 text-slate-400 p-3 rounded-2xl mr-auto rounded-bl-none text-xs flex items-center gap-2">
                  <i className="fa-solid fa-spinner animate-spin text-indigo-400 text-sm" />
                  AI Voice Assistant thinking & checking tools...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Controls Bar: Text Input & Voice Recording */}
            {callState === 'active' && (
              <div className="mt-4 flex items-center gap-2">
                <button
                  type="button"
                  onClick={toggleRecording}
                  className={`p-3 rounded-xl border transition-all cursor-pointer ${
                    isRecording
                      ? 'bg-emerald-600 text-white border-emerald-500 shadow-lg shadow-emerald-500/25 animate-pulse'
                      : 'bg-slate-900 text-slate-400 border-white/10 hover:border-emerald-500/40 hover:text-emerald-400'
                  }`}
                  title={isRecording ? 'Microphone Active (Continuous Hands-Free) • Click to Pause/Mute' : 'Microphone Paused • Click to Resume Continuous Listening'}
                >
                  <i className={`fa-solid ${isRecording ? 'fa-microphone' : 'fa-microphone-slash'} text-lg`} />
                </button>

                <input
                  type="text"
                  placeholder="Type customer reply in English, Hindi (हिन्दी), or Kannada (ಕನ್ನಡ)..."
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                  className="flex-1 bg-slate-900 border border-white/10 rounded-xl px-4 py-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />

                <button
                  type="button"
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() || isProcessing}
                  className="p-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition-all disabled:opacity-50 cursor-pointer"
                >
                  <i className="fa-solid fa-paper-plane text-lg" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
