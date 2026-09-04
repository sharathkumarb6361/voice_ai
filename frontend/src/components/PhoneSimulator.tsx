import React, { useState, useEffect, useRef } from 'react';
import { Business, Workflow, ChatMessage } from '../types';
import { sendChatMessage, generateTTS } from '../lib/api';

interface PhoneSimulatorProps {
  businesses: Business[];
  workflows: Workflow[];
  selectedLanguage: string;
  initialWorkflowId?: string;
}

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
  const [isProcessing, setIsProcessing] = useState(false);
  const [lastExecutedTools, setLastExecutedTools] = useState<any[]>([]);
  const [activeUrgency, setActiveUrgency] = useState<string>('Normal');
  const [activeLanguage, setActiveLanguage] = useState<string>('en');
  const [languageSwitchNotice, setLanguageSwitchNotice] = useState<string | null>(null);
  const [micStatusNotice, setMicStatusNotice] = useState<string | null>(null);

  // Audio Playback & Mic Recording Refs
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Keep refs synced for event handlers
  const callStateRef = useRef(callState);
  const isHandsFreeRef = useRef(isHandsFree);

  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  useEffect(() => {
    isHandsFreeRef.current = isHandsFree;
  }, [isHandsFree]);

  useEffect(() => {
    if (initialWorkflowId) {
      setSelectedWorkflowId(initialWorkflowId);
    }
  }, [initialWorkflowId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Start Call Simulation
  const startCall = () => {
    setCallState('ringing');
    setMessages([]);
    setLastExecutedTools([]);
    setActiveUrgency('Normal');
    setActiveLanguage('en');
    setLanguageSwitchNotice(null);

    setTimeout(() => {
      setCallState('active');
      const initialGreeting: ChatMessage = {
        role: 'assistant',
        content: activeWorkflow?.greeting || 'Hello! Thank you for calling. We missed your call.'
      };
      setMessages([initialGreeting]);
      speakText(initialGreeting.content, 'en', true);
    }, 1500);
  };

  const endCall = () => {
    setCallState('ended');
    setIsRecording(false);
    setIsPlayingAudio(false);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop(); } catch (e) {}
    }
  };

  // Speak AI text using server TTS audio synthesis (Supports English, Hindi, Kannada)
  const speakText = async (text: string, languageOverride?: string, autoListenNext: boolean = false) => {
    try {
      setIsPlayingAudio(true);
      const targetLang = languageOverride || (selectedLanguage === 'auto' ? activeLanguage : selectedLanguage);
      const lang = targetLang === 'kn' ? 'kn' : (targetLang === 'hi' ? 'hi' : 'en');
      const ttsData = await generateTTS(text, lang);

      if (ttsData?.audio_base64) {
        const audioSrc = `data:${ttsData.format || 'audio/wav'};base64,${ttsData.audio_base64}`;
        if (!audioRef.current) {
          audioRef.current = new Audio(audioSrc);
        } else {
          audioRef.current.src = audioSrc;
        }

        audioRef.current.onended = () => {
          setIsPlayingAudio(false);
          // If Hands-Free Live Phone Mode is enabled, automatically start listening to caller mic!
          if (autoListenNext || (isHandsFreeRef.current && callStateRef.current === 'active')) {
            setTimeout(() => {
              if (callStateRef.current === 'active') {
                startRecordingMic();
              }
            }, 600);
          }
        };

        await audioRef.current.play();
      } else {
        setIsPlayingAudio(false);
        if (autoListenNext || (isHandsFreeRef.current && callStateRef.current === 'active')) {
          setTimeout(() => startRecordingMic(), 600);
        }
      }
    } catch (err) {
      console.warn('TTS playback notice:', err);
      setIsPlayingAudio(false);
      if (autoListenNext || (isHandsFreeRef.current && callStateRef.current === 'active')) {
        setTimeout(() => startRecordingMic(), 600);
      }
    }
  };

  // Submit turn message
  const handleSendMessage = async (customText?: string) => {
    const textToSend = customText || inputMessage;
    if (!textToSend.trim() || isProcessing || !activeWorkflow) return;

    setInputMessage('');
    const userMsg: ChatMessage = { role: 'user', content: textToSend };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setIsProcessing(true);
    setLanguageSwitchNotice(null);

    try {
      const response = await sendChatMessage({
        business_id: activeBusiness.id,
        workflow_id: activeWorkflow.id,
        caller_name: callerName,
        caller_phone: callerPhone,
        language: selectedLanguage,
        messages: updatedMessages
      });

      const assistantMsg: ChatMessage = { role: 'assistant', content: response.assistant_reply };
      setMessages([...updatedMessages, assistantMsg]);
      setLastExecutedTools(response.executed_tools || []);
      if (response.urgency) setActiveUrgency(response.urgency);
      if (response.language) setActiveLanguage(response.language);

      // Check for Natural Language Switch Notice
      if (response.language_switched) {
        const switchLog = (response.executed_tools || []).find((t: any) => t.tool === 'language_switch_detected');
        if (switchLog && switchLog.args) {
          setLanguageSwitchNotice(`🔄 Language Switch: ${switchLog.args.from} ➔ ${switchLog.args.to}`);
        } else {
          setLanguageSwitchNotice(`🔄 Dynamic Language Switch Detected!`);
        }
      }

      speakText(response.assistant_reply, response.language, isHandsFree);
    } catch (err: any) {
      alert(`AI Call Error: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  // Dual-Engine Microphone Recording (Web Speech API + MediaRecorder Backup)
  const startRecordingMic = () => {
    if (isRecording || isProcessing || callStateRef.current !== 'active') return;

    // Stop any existing active recognition instance first
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
      recognitionRef.current = null;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognitionRef.current = recognition;
        recognition.continuous = false;
        recognition.interimResults = false;

        // Accurate language code mapping for Speech-to-Text
        const targetLang = activeLanguage === 'kn' ? 'kn-IN' : (activeLanguage === 'hi' ? 'hi-IN' : 'en-IN');
        recognition.lang = targetLang;

        recognition.onstart = () => {
          setIsRecording(true);
          setMicStatusNotice(null);
        };

        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0]?.transcript;
          setIsRecording(false);
          if (transcript && transcript.trim()) {
            handleSendMessage(transcript.trim());
          }
        };

        recognition.onerror = (event: any) => {
          setIsRecording(false);
          const errorType = event?.error;
          console.log('[Web Speech API] Recognition event:', errorType);

          if (errorType === 'no-speech') {
            setMicStatusNotice('No speech detected. Click the microphone or type to speak.');
          } else if (errorType === 'audio-capture' || errorType === 'not-allowed') {
            setMicStatusNotice('Microphone access blocked. Please check browser microphone permissions.');
          } else if (errorType !== 'aborted') {
            setMicStatusNotice(`Speech recognition paused (${errorType || 'idle'}). Click microphone to retry.`);
          }
        };

        recognition.onend = () => {
          setIsRecording(false);
          recognitionRef.current = null;
        };

        recognition.start();
        return;
      } catch (err) {
        console.warn('Web Speech API notice:', err);
      }
    }

    // Backup HTML5 MediaRecorder
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
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
          if (audioBlob.size > 0) {
            try {
              setIsProcessing(true);
              const formData = new FormData();
              formData.append('audio', audioBlob, 'recording.webm');
              const sttRes = await fetch('/api/ai/stt', { method: 'POST', body: formData });
              const sttJson = await sttRes.json();
              if (sttJson.success && sttJson.data?.text) {
                handleSendMessage(sttJson.data.text);
              } else {
                setMicStatusNotice('Speech not recognized. Click microphone to speak again.');
              }
            } catch (err) {
              setMicStatusNotice('Microphone recording error. Click microphone to retry.');
            } finally {
              setIsProcessing(false);
            }
          }
        };

        mediaRecorder.start();
        setIsRecording(true);
        setTimeout(() => {
          if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            setIsRecording(false);
          }
        }, 4000);
      }).catch(() => {
        setMicStatusNotice('Microphone permission required for live voice input.');
      });
    } else {
      setMicStatusNotice('Microphone is not supported in this browser environment.');
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (e) {}
        recognitionRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
      return;
    }
    startRecordingMic();
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

            {/* Audio Waveform Equalizer Indicator */}
            {(isPlayingAudio || isRecording) && (
              <div className="bg-gradient-to-r from-slate-900 via-indigo-950/80 to-slate-900 p-3.5 rounded-2xl border border-indigo-500/40 mb-4 flex items-center justify-between shadow-xl">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-400/40 flex items-center justify-center animate-pulse">
                    <i className="fa-solid fa-volume-high text-indigo-400 text-sm" />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-white block">
                      {isPlayingAudio ? `AI Voice Assistant Speaking (${langInfo.label})` : `Listening to Caller Speech (${langInfo.label})`}
                    </span>
                    <span className="text-[10px] text-indigo-300">Live Audio Stream • Real-time Processing</span>
                  </div>
                </div>
                {/* 8-Bar Equalizer */}
                <div className="flex items-center gap-1.5 h-8 px-2 bg-slate-950/60 rounded-xl border border-indigo-500/20">
                  <div className="w-1.5 bg-indigo-500 eq-bar" />
                  <div className="w-1.5 bg-blue-400 eq-bar" />
                  <div className="w-1.5 bg-indigo-400 eq-bar" />
                  <div className="w-1.5 bg-purple-500 eq-bar" />
                  <div className="w-1.5 bg-indigo-500 eq-bar" />
                  <div className="w-1.5 bg-blue-500 eq-bar" />
                  <div className="w-1.5 bg-cyan-400 eq-bar" />
                  <div className="w-1.5 bg-indigo-400 eq-bar" />
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
                  className={`p-3 rounded-xl border transition-all ${
                    isRecording
                      ? 'bg-rose-600 text-white border-rose-500 animate-pulse'
                      : 'bg-slate-900 text-indigo-400 border-white/10 hover:border-indigo-500/40'
                  }`}
                  title={isRecording ? 'Stop Recording' : 'Speak Voice Microphone'}
                >
                  <i className={`fa-solid ${isRecording ? 'fa-microphone-slash' : 'fa-microphone'} text-lg`} />
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
                  className="p-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition-all disabled:opacity-50"
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
