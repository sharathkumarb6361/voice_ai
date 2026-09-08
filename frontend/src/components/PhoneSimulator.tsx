import React, { useState, useEffect, useRef } from 'react';
import { Business, Workflow, ChatMessage } from '../types';
import { sendChatMessage, generateTTS, transcribeAudio, triggerDeliveryMissedCall, triggerCakeMissedCall } from '../lib/api';


interface PhoneSimulatorProps {
  businesses: Business[];
  workflows: Workflow[];
  selectedLanguage: string;
  initialWorkflowId?: string;
  onDataChanged?: () => void;
  onNavigateToCalendar?: (targetDate?: string) => void;
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
  initialWorkflowId,
  onDataChanged,
  onNavigateToCalendar
}) => {
  const getConfiguredLanguage = () => (
    selectedLanguage === 'hi' || selectedLanguage === 'kn' ? selectedLanguage : 'en'
  );

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
  const [isManualRecording, setIsManualRecording] = useState(false);
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
  const [callCompletionNotice, setCallCompletionNotice] = useState<string | null>(null);
  const [calendarBookingNotice, setCalendarBookingNotice] = useState<{ title: string; time: string } | null>(null);
  const [isEndingCall, setIsEndingCall] = useState<boolean>(false);
  const [recentlyUpdatedFields, setRecentlyUpdatedFields] = useState<string[]>([]);
  const [showMobileSettings, setShowMobileSettings] = useState<boolean>(false);


  // Microphone Hardware & Diagnostic State
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [micPermission, setMicPermission] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [isMicTesting, setIsMicTesting] = useState(false);
  const [micTestResult, setMicTestResult] = useState<string | null>(null);

  // Audio Playback & Mic Recording Refs (Guards against state closure race conditions)
  const callStateRef = useRef(callState);
  const isHandsFreeRef = useRef(isHandsFree);
  const isPlayingAudioRef = useRef(false);
  const isProcessingRef = useRef(false);
  const isMicMutedByUserRef = useRef(false);
  const activeLanguageRef = useRef(activeLanguage);
  const audioLevelRef = useRef(0);
  const isManualRecordingRef = useRef(false);
  const preferServerSttRef = useRef(false);
  const hasSpokenRef = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);
  const currentRecordIdRef = useRef<string | null>(null);
  const collectedDataRef = useRef<Record<string, any>>({});
  const isEndingCallRef = useRef<boolean>(false);

  const updateMessages = (newMsgs: ChatMessage[]) => {
    messagesRef.current = newMsgs;
    setMessages(newMsgs);
  };

  const updateRecordId = (recId: string | null) => {
    currentRecordIdRef.current = recId;
    setCurrentRecordId(recId);
  };

  const updateCollectedData = (data: Record<string, any>) => {
    collectedDataRef.current = data;
    setCollectedData(data);
  };

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const restartTimerRef = useRef<any>(null);
  const silenceTimerRef = useRef<any>(null);
  const vadIntervalRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  useEffect(() => {
    activeLanguageRef.current = activeLanguage;
  }, [activeLanguage]);

  useEffect(() => {
    isHandsFreeRef.current = isHandsFree;
    if (callState === 'active' && isHandsFree && !isPlayingAudioRef.current && !isProcessingRef.current && !isRecording) {
      startListening();
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
      releaseMicStream();
      if (audioRef.current) {
        try { audioRef.current.pause(); } catch (e) {}
      }
      if ('speechSynthesis' in window) {
        try { window.speechSynthesis.cancel(); } catch (e) {}
      }
    };
  }, []);

  // Web Audio Analyser setup to calculate real microphone decibels/amplitude
  const setupAudioAnalyser = (stream: MediaStream) => {
    try {
      if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        audioContextRef.current = new AudioCtx();
      }
      if (audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume();
      }
      const ctx = audioContextRef.current;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.3;
      source.connect(analyser);
      analyserRef.current = analyser;

      const timeData = new Uint8Array(analyser.fftSize);

      const updateLoop = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteTimeDomainData(timeData);
        let sumSquares = 0;
        for (let i = 0; i < timeData.length; i++) {
          const val = (timeData[i] - 128) / 128;
          sumSquares += val * val;
        }
        const rms = Math.sqrt(sumSquares / timeData.length);
        const normalized = Math.min(100, Math.round(rms * 240));
        setAudioLevel(normalized);
        audioLevelRef.current = normalized;
        animFrameRef.current = requestAnimationFrame(updateLoop);
      };

      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = requestAnimationFrame(updateLoop);
    } catch (e) {
      console.warn('Audio analyser setup warning:', e);
    }
  };

  // Get or request microphone hardware stream
  const getOrInitMicStream = async (): Promise<MediaStream | null> => {
    if (micStreamRef.current && micStreamRef.current.active && micStreamRef.current.getAudioTracks().some(t => t.readyState === 'live')) {
      return micStreamRef.current;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicPermission('denied');
      setMicStatusNotice('Microphone not supported in this browser. Please use text input.');
      return null;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      micStreamRef.current = stream;
      setMicPermission('granted');
      setupAudioAnalyser(stream);
      return stream;
    } catch (err: any) {
      console.warn('Microphone permission error:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setMicPermission('denied');
        setMicStatusNotice('⚠️ Microphone permission blocked. Click the lock icon in your browser address bar and set Microphone to "Allow".');
      } else {
        setMicStatusNotice(`Microphone error: ${err.message || 'Check audio device.'}`);
      }
      return null;
    }
  };

  // Release microphone stream hardware
  const releaseMicStream = () => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach(t => t.stop());
      } catch (e) {}
      micStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try { audioContextRef.current.close(); } catch (e) {}
    }
    audioContextRef.current = null;
    analyserRef.current = null;
    setAudioLevel(0);
    audioLevelRef.current = 0;
  };

  // Quick 3-Second Microphone Diagnostic Test
  const runMicTest = async () => {
    setIsMicTesting(true);
    setMicTestResult('Connecting to microphone hardware...');
    const stream = await getOrInitMicStream();
    if (!stream) {
      setMicTestResult('❌ Microphone permission denied or no audio input found. Please allow mic in browser settings.');
      setIsMicTesting(false);
      return;
    }

    setMicTestResult('🎙️ Microphone active! Speak something now (e.g., "Hello testing 1 2 3")...');

    try {
      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
        else if (MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
        else if (MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
      }

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const testChunks: Blob[] = [];

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) testChunks.push(e.data);
      };

      recorder.onstop = async () => {
        setMicTestResult('⚙️ Transcribing test voice sample via AI Engine...');
        const blob = new Blob(testChunks, { type: recorder.mimeType || 'audio/webm' });
        if (blob.size < 400) {
          setMicTestResult('⚠️ Mic stream connected, but no audio was recorded. Please check your mic volume slider in Windows settings.');
          setIsMicTesting(false);
          return;
        }
        try {
          const res = await transcribeAudio(blob, activeLanguageRef.current);
          if (res && res.text && res.text.trim()) {
            setMicTestResult(`✅ Microphone Working! Heard: "${res.text}" (via ${res.provider || 'Sarvam / Whisper'})`);
          } else {
            setMicTestResult('⚠️ Microphone connected and audio captured, but speech was too quiet. Try speaking closer to mic.');
          }
        } catch (err: any) {
          setMicTestResult('⚠️ AI STT Server Notice: ' + (err.message || 'Transcribe error'));
        } finally {
          setIsMicTesting(false);
        }
      };

      recorder.start(100);
      setTimeout(() => {
        if (recorder.state === 'recording') recorder.stop();
      }, 3500);
    } catch (e: any) {
      setMicTestResult('❌ Recording error: ' + e.message);
      setIsMicTesting(false);
    }
  };

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

      let called = false;
      const safeDone = () => {
        if (!called) {
          called = true;
          onDone();
        }
      };

      utterance.onend = safeDone;
      utterance.onerror = safeDone;

      // Chrome speech synthesis safety watchdog
      const estimatedSec = Math.max((text.length / 10), 2);
      setTimeout(safeDone, estimatedSec * 1000 + 2000);

      window.speechSynthesis.speak(utterance);
    } catch (e) {
      onDone();
    }
  };

  // Safely stop only microphone recording/recognition without ending call session
  const stopMicOnly = () => {
    clearTimeout(restartTimerRef.current);
    clearTimeout(silenceTimerRef.current);
    clearInterval(vadIntervalRef.current);

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
    setIsManualRecording(false);
    isManualRecordingRef.current = false;
    setLiveTranscript('');
  };

  // Stop recording and send audio immediately
  const stopManualRecordingAndSend = () => {
    clearInterval(vadIntervalRef.current);
    clearTimeout(silenceTimerRef.current);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try { mediaRecorderRef.current.stop(); } catch (e) {}
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch (e) {}
    }
  };

  // Primary Server STT Recording Engine (Sarvam AI / Groq Whisper + Web Audio VAD)
  const startServerSttRecording = async (isManual = false) => {
    if (callStateRef.current !== 'active' && !isManual) return;
    if (isPlayingAudioRef.current || isProcessingRef.current || isMicMutedByUserRef.current) return;

    const stream = await getOrInitMicStream();
    if (!stream) {
      setIsRecording(false);
      return;
    }

    stopMicOnly();

    try {
      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
        else if (MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
        else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) mimeType = 'audio/ogg;codecs=opus';
        else if (MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
      }

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      hasSpokenRef.current = false;
      isManualRecordingRef.current = isManual;
      setIsManualRecording(isManual);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstart = () => {
        setIsRecording(true);
        setVoiceActivityState('listening');
        setMicStatusNotice(null);
      };

      recorder.onstop = async () => {
        setIsRecording(false);
        setIsManualRecording(false);
        isManualRecordingRef.current = false;

        const chunks = [...audioChunksRef.current];
        audioChunksRef.current = [];

        if (chunks.length === 0 || callStateRef.current !== 'active') {
          return;
        }

        const audioBlob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });

        if (audioBlob.size > 500 && (hasSpokenRef.current || isManualRecordingRef.current)) {
          try {
            isProcessingRef.current = true;
            setIsProcessing(true);
            setVoiceActivityState('processing');

            const targetLang = activeLanguageRef.current;
            const res = await transcribeAudio(audioBlob, targetLang);
            if (res && res.text && res.text.trim()) {
              handleSendMessage(res.text.trim());
              return;
            }
          } catch (sttErr: any) {
            console.warn('STT transcription notice:', sttErr);
          } finally {
            isProcessingRef.current = false;
            setIsProcessing(false);
          }
        }

        // If no speech captured in this slice and hands-free is on, resume listening loop
        if (
          callStateRef.current === 'active' &&
          isHandsFreeRef.current &&
          !isMicMutedByUserRef.current &&
          !isPlayingAudioRef.current
        ) {
          clearTimeout(restartTimerRef.current);
          restartTimerRef.current = setTimeout(() => {
            startListening();
          }, 250);
        } else {
          setVoiceActivityState('idle');
        }
      };

      recorder.start(200);

      // Automated Voice Activity Detection (VAD) for Hands-Free mode
      if (!isManual) {
        let speechDetected = false;
        let silenceCount = 0;
        let totalElapsed = 0;

        clearInterval(vadIntervalRef.current);
        vadIntervalRef.current = setInterval(() => {
          totalElapsed += 100;
          const currentVol = audioLevelRef.current;

          // Lowered threshold for VAD detection to be more sensitive
          if (currentVol >= 8) {
            speechDetected = true;
            hasSpokenRef.current = true;
            silenceCount = 0;
            setLiveTranscript('🎙️ Hearing voice...');
          } else if (speechDetected) {
            silenceCount += 100;
            // 1.0 seconds of silence after speech -> user done speaking!
            if (silenceCount >= 1000) {

              clearInterval(vadIntervalRef.current);
              setLiveTranscript('');
              if (recorder.state === 'recording') {
                recorder.stop();
              }
            }
          }

          // Cycle every 10 seconds if no speech to prevent memory build-up
          if (totalElapsed >= 10000) {
            clearInterval(vadIntervalRef.current);
            setLiveTranscript('');
            if (recorder.state === 'recording') {
              recorder.stop();
            }
          }
        }, 100);
      }
    } catch (e: any) {
      console.warn('startServerSttRecording error:', e);
      setMicStatusNotice('Could not start microphone recording: ' + e.message);
    }
  };

  // Start continuous listening (attempts WebSpeech if supported, with persistent server fallback)
  const startListening = () => {
    if (
      callStateRef.current !== 'active' ||
      isPlayingAudioRef.current ||
      isProcessingRef.current ||
      isMicMutedByUserRef.current
    ) {
      return;
    }

    // If server STT is preferred, use Server STT pipeline
    if (preferServerSttRef.current) {
      startServerSttRecording(false);
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      preferServerSttRef.current = true;
      startServerSttRecording(false);
      return;
    }

    stopMicOnly();

    try {
      const recognition = new SpeechRecognition();
      recognitionRef.current = recognition;
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      const targetLang = activeLanguageRef.current === 'kn' ? 'kn-IN' : (activeLanguageRef.current === 'hi' ? 'hi-IN' : 'en-IN');
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
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => {
            if (interim.trim() && callStateRef.current === 'active' && !isProcessingRef.current && !finalCaptured) {
              finalCaptured = true;
              stopMicOnly();
              handleSendMessage(interim.trim());
            }
          }, 1400);
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
        if (err === 'no-speech' || err === 'aborted') {
          return;
        }
        if (err === 'not-allowed' || err === 'audio-capture') {
          setMicPermission('denied');
          setMicStatusNotice('Microphone access blocked. Please allow mic in browser settings.');
          return;
        }
        // If network or speech service error, switch to server STT
        if (err === 'network' || err === 'service-not-allowed' || err === 'language-not-supported') {
          preferServerSttRef.current = true;
          setMicStatusNotice('Using Sarvam AI / Whisper speech engine for voice calls...');
        }
      };

      recognition.onend = () => {
        setIsRecording(false);
        recognitionRef.current = null;

        if (preferServerSttRef.current && callStateRef.current === 'active' && !isMicMutedByUserRef.current) {
          startServerSttRecording(false);
          return;
        }

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
              startListening();
            }
          }, 200);
        }
      };

      recognition.start();
    } catch (err) {
      console.warn('SpeechRecognition startup error, using server STT:', err);
      preferServerSttRef.current = true;
      startServerSttRecording(false);
    }
  };

  // Start Call Simulation (Auto-starts continuous turn-taking)
  const startCall = () => {
    // Eagerly connect to microphone hardware on user gesture
    getOrInitMicStream();

    setCallCompletionNotice(null);
    setCalendarBookingNotice(null);
    setIsEndingCall(false);
    isEndingCallRef.current = false;
    setCallState('ringing');
    updateRecordId(null);
    updateCollectedData({});
    updateMessages([]);
    setLastExecutedTools([]);
    setActiveUrgency('Normal');
    const configuredLanguage = getConfiguredLanguage();
    activeLanguageRef.current = configuredLanguage;
    setActiveLanguage(configuredLanguage);
    setLanguageSwitchNotice(null);
    setMicStatusNotice(null);
    setLiveTranscript('');
    isMicMutedByUserRef.current = false;

    setTimeout(async () => {
      setCallState('active');
      callStateRef.current = 'active';
      isHandsFreeRef.current = true;
      setIsHandsFree(true);

      const isLogistics = activeWorkflow?.id === 'wf-logistics-01' || activeWorkflow?.industry === 'Logistics & Delivery';
      const isCakeShop = activeWorkflow?.id === 'wf-cake-01' || activeWorkflow?.industry === 'Cake Shop';

      if (isLogistics) {
        try {
          const callbackInit = await triggerDeliveryMissedCall(callerName, callerPhone, configuredLanguage);
          if (callbackInit) {
            updateRecordId(callbackInit.record_id);
            setLastExecutedTools(callbackInit.executed_tools || []);
            const reply = callbackInit.assistant_reply;
            updateMessages([{ role: 'assistant', content: reply }]);
            speakText(reply, configuredLanguage);
            return;
          }
        } catch (e) {
          console.warn('Could not initialize delivery callback webhook, using default greeting', e);
        }
      } else if (isCakeShop) {
        try {
          const callbackInit = await triggerCakeMissedCall(callerName, callerPhone, configuredLanguage);
          if (callbackInit) {
            updateRecordId(callbackInit.record_id);
            setLastExecutedTools(callbackInit.executed_tools || []);
            const reply = callbackInit.assistant_reply;
            updateMessages([{ role: 'assistant', content: reply }]);
            speakText(reply, configuredLanguage);
            return;
          }
        } catch (e) {
          console.warn('Could not initialize cake callback webhook, using default greeting', e);
        }
      }

      const fallbackGreeting = configuredLanguage === 'kn'
        ? (isLogistics 
            ? 'ನಮಸ್ಕಾರ, ನಿಮ್ಮ ಮಿಸ್ಡ್ ಕಾಲ್ ಕುರಿತು ಡೆಲಿವರಿ ಸಹಾಯಕರು ಮರಳಿ ಕರೆ ಮಾಡುತ್ತಿದ್ದಾರೆ. ನೀವು ಹೊಸ ಡೆಲಿವರಿ ಬುಕ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಾ, ಈಗಿರುವ ಡೆಲಿವರಿ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಲು ಬಯಸುತ್ತೀರಾ ಅಥವಾ ಸಹಾಯ ಬೇಕೇ?'
            : isCakeShop
            ? 'ನಮಸ್ಕಾರ! ಸ್ವೀಟ್ ಟ್ರೀಟ್ಸ್ ಬೇಕರಿಗೆ ಸುಸ್ವಾಗತ. ನಿಮ್ಮ ಮಿಸ್ಡ್ ಕಾಲ್ ನೋಡಿದೆವು. ನೀವು ಕೇಕ್ ಆರ್ಡರ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಾ ಅಥವಾ ಯಾವುದೇ ವಿಚಾರಣೆ ಇದೆಯೇ?'
            : 'ನಮಸ್ಕಾರ! ಕರೆ ಮಾಡಿದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?')
        : configuredLanguage === 'hi'
          ? (isLogistics
              ? 'नमस्ते, मिस्ड कॉल के संबंध में डिलीवरी सहायक आपको वापस कॉल कर रहा है। क्या आप एक नई डिलीवरी बुक करना चाहते हैं, मौजूदा डिलीवरी का स्टेटस जानना चाहते हैं, या किसी डिलीवरी में सहायता चाहते हैं?'
              : isCakeShop
              ? 'नमस्ते! स्वीट ट्रीट्स बेकरी में आपका स्वागत है। हमें आपका मिस्ड कॉल मिला। क्या आप केक ऑर्डर करना चाहते हैं या कोई सामान्य पूछताछ है?'
              : 'नमस्ते! कॉल करने के लिए धन्यवाद। मैं आपकी कैसे सहायता कर सकता हूँ?')
          : (isLogistics
              ? 'Hi, this is the delivery assistant calling you back regarding your missed call. Are you looking to create a new delivery, check the status of an existing delivery, or get help with an existing delivery?'
              : isCakeShop
              ? 'Namaste! Welcome to Sweet Treats Bakery. We missed your call. How can we help you today with your cake order or bakery enquiry?'
              : 'Hello! Thank you for calling. How may I help you?');

      const initialGreeting: ChatMessage = {
        role: 'assistant',
        content: configuredLanguage === 'en'
          ? (activeWorkflow?.greeting || fallbackGreeting)
          : fallbackGreeting
      };
      updateMessages([initialGreeting]);
      // Speak greeting, then automatically activate continuous microphone
      speakText(initialGreeting.content, configuredLanguage);
    }, 1200);
  };

  const endCall = async (force: boolean = false) => {
    if (force || isEndingCallRef.current || callStateRef.current !== 'active') {
      isEndingCallRef.current = false;
      setIsEndingCall(false);
      setCallState('ended');
      callStateRef.current = 'ended';
      setVoiceActivityState('idle');
      stopMicOnly();
      releaseMicStream();
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
      if (onDataChanged) {
        onDataChanged();
      }
      return;
    }

    // Gracefully conclude the call: AI speaks a warm thank you message before hanging up
    isEndingCallRef.current = true;
    setIsEndingCall(true);
    stopMicOnly();
    setIsRecording(false);
    setVoiceActivityState('speaking');

    const bizName = activeBusiness?.name || 'us';
    const closingMsgFromWf = activeWorkflow?.closing_message;
    const targetLang = activeLanguageRef.current;

    let thankYouText = `Thank you for contacting ${bizName}! ${closingMsgFromWf ? `${closingMsgFromWf} ` : ''}Have a wonderful day, goodbye!`;
    if (targetLang === 'kn') {
      thankYouText = `${bizName} ge samparkisiddakke thumba dhanyavadagalu! ${closingMsgFromWf ? `${closingMsgFromWf} ` : ''}Shubhadina, dhanyavadagalu!`;
    } else if (targetLang === 'hi') {
      thankYouText = `${bizName} mein call karne ke liye aapka bahut-bahut dhanyawad! ${closingMsgFromWf ? `${closingMsgFromWf} ` : ''}Aapka din shubh ho, alvida!`;
    }

    const assistantClosingMsg: ChatMessage = {
      role: 'assistant',
      content: thankYouText
    };
    updateMessages([...messagesRef.current, assistantClosingMsg]);

    await speakText(thankYouText, targetLang, true);
  };

  // Speak AI text with ultra-natural human voice and automatically resume continuous listening (or end call if complete)
  const speakText = async (text: string, languageOverride?: string, shouldEndCallAfter: boolean = false) => {
    // 1. Mute microphone during speech to prevent audio echo loop
    stopMicOnly();

    isPlayingAudioRef.current = true;
    setIsPlayingAudio(true);
    setVoiceActivityState('speaking');

    const cleanSpeech = cleanTextForSpeech(text);
    const targetLang = languageOverride || (selectedLanguage === 'auto' ? activeLanguage : selectedLanguage);
    const lang = targetLang === 'kn' ? 'kn' : (targetLang === 'hi' ? 'hi' : 'en');

    let isFinished = false;
    const onSpeechFinished = () => {
      if (isFinished) return;
      isFinished = true;

      isPlayingAudioRef.current = false;
      setIsPlayingAudio(false);

      // If call is concluding (all fields collected, user said goodbye, or end call triggered), end call after thank you
      if (shouldEndCallAfter) {
        isEndingCallRef.current = false;
        setIsEndingCall(false);
        setVoiceActivityState('idle');
        stopMicOnly();
        releaseMicStream();
        setCallState('ended');
        callStateRef.current = 'ended';
        setCallCompletionNotice('Thank you message delivered. Call concluded.');
        if (onDataChanged) {
          onDataChanged();
        }
        return;
      }

      // AUTOMATICALLY RESUME LISTENING: User never has to click mic again!
      if (callStateRef.current === 'active' && isHandsFreeRef.current && !isMicMutedByUserRef.current) {
        setVoiceActivityState('listening');
        clearTimeout(restartTimerRef.current);
        // Buffer 300ms to allow room echo to decay before mic opens
        restartTimerRef.current = setTimeout(() => {
          if (callStateRef.current === 'active' && !isPlayingAudioRef.current && !isProcessingRef.current) {
            startListening();
          }
        }, 300);
      } else {
        setVoiceActivityState('idle');
      }
    };

    try {
      const ttsData = await generateTTS(cleanSpeech, lang);

      if (ttsData?.audio_base64) {
        const audioSrc = `data:${ttsData.format || 'audio/wav'};base64,${ttsData.audio_base64}`;
        if (audioRef.current) {
          try { audioRef.current.pause(); } catch (e) {}
        }
        const audio = new Audio(audioSrc);
        audioRef.current = audio;

        audio.onended = () => {
          onSpeechFinished();
        };

        audio.onerror = () => {
          console.warn('Audio element error, utilizing natural browser speech fallback');
          speakBrowserFallback(cleanSpeech, lang, onSpeechFinished);
        };

        // Safety fallback if audio play hangs or does not fire onended
        const estimatedAudioMs = Math.max((cleanSpeech.length / 8) * 1000 + 2000, 3500);
        setTimeout(() => {
          onSpeechFinished();
        }, estimatedAudioMs);

        try {
          await audio.play();
        } catch (playErr) {
          console.warn('audio.play() error or autoplay blocked, using fallback:', playErr);
          speakBrowserFallback(cleanSpeech, lang, onSpeechFinished);
        }
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
    const updatedMessages = [...messagesRef.current, userMsg];
    updateMessages(updatedMessages);
    setLanguageSwitchNotice(null);

    try {
      const response = await sendChatMessage({
        business_id: activeBusiness.id,
        workflow_id: activeWorkflow.id,
        caller_name: callerName,
        caller_phone: callerPhone,
        language: selectedLanguage,
        messages: updatedMessages,
        record_id: currentRecordIdRef.current || undefined
      });

      if (response.record_id) {
        updateRecordId(response.record_id);
      }
      if (response.collected_data) {
        const prev = collectedDataRef.current;
        const changedKeys = Object.keys(response.collected_data).filter(
          k => !k.startsWith('_') && prev[k] !== undefined && prev[k] !== null && String(prev[k]) !== String(response.collected_data[k])
        );
        if (changedKeys.length > 0) {
          setRecentlyUpdatedFields(changedKeys);
          setTimeout(() => setRecentlyUpdatedFields([]), 5000);
        }
        updateCollectedData(response.collected_data);
      }

      // Check if user signaled end of conversation / thank you
      const isEndingIntent = /(?:thank\s*you|thanks|goodbye|bye|hang\s*up|end\s*call|that(?:'s|\s+is)\s+all|nothing\s+else|no\s+more|done|alvida|shukriya|dhanyawad|dhanyavad)/i.test(textToSend);

      // Check if all required database fields are satisfied
      const allReqFilled = (() => {
        const reqFields = (activeWorkflow?.fields || []).filter(f => f.required);
        if (reqFields.length === 0) return Boolean(response.is_complete);
        const mergedData = { ...collectedDataRef.current, ...(response.collected_data || {}) };
        return reqFields.every(f => {
          const val = mergedData[f.key];
          return val !== undefined && val !== null && String(val).trim() !== '';
        });
      })();

      // CRITICAL: Never permanently lock the call or auto-hangup just because fields are filled!
      // The call should only conclude after speech when the caller explicitly signals an ending intent (goodbye/thank you/hang up).
      const shouldEndCallAfter = Boolean(isEndingIntent);

      // Ensure assistant reply contains a clear, warm thank you message if caller signaled ending
      let finalAssistantReply = response.assistant_reply;
      if (isEndingIntent) {
        const hasThankYou = /(?:thank\s*you|thanks|dhanyawad|dhanyavad|shukriya|dhanyavadagalu)/i.test(finalAssistantReply);
        if (!hasThankYou) {
          const bizName = activeBusiness?.name || 'us';
          if (response.language === 'kn') {
            finalAssistantReply += ` ${bizName} ge call madidakke thumba dhanyavadagalu! Shubhadina!`;
          } else if (response.language === 'hi') {
            finalAssistantReply += ` ${bizName} mein call karne ke liye aapka bahut dhanyawad! Alvida!`;
          } else {
            finalAssistantReply += ` Thank you for contacting ${bizName}! Have a wonderful day, goodbye!`;
          }
        }
      }

      const assistantMsg: ChatMessage = { role: 'assistant', content: finalAssistantReply };
      updateMessages([...updatedMessages, assistantMsg]);
      setLastExecutedTools(response.executed_tools || []);

      const calTool = (response.executed_tools || []).find(
        (t: any) => t.tool === 'create_calendar_event' || t.tool === 'update_calendar_event'
      );
      if (calTool) {
        setCalendarBookingNotice({
          title: calTool.args?.title || (collectedDataRef.current.cake_flavor ? `Cake Order (${collectedDataRef.current.cake_flavor})` : 'Appointment Scheduled'),
          time: calTool.args?.start_time || collectedDataRef.current.required_date || new Date().toISOString()
        });
        if (onDataChanged) {
          onDataChanged();
        }
      }
      if (response.urgency) setActiveUrgency(response.urgency);
      if (response.language) {
        activeLanguageRef.current = response.language;
        setActiveLanguage(response.language);
      }

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

      // Speak AI response with human-like voice; only end call if caller signaled ending intent
      await speakText(finalAssistantReply, response.language, shouldEndCallAfter);
    } catch (err: any) {
      isProcessingRef.current = false;
      setIsProcessing(false);
      setVoiceActivityState('idle');
      alert(`AI Call Error: ${err.message}`);
      // Resume listening so call does not freeze on network glitch
      if (callStateRef.current === 'active' && isHandsFreeRef.current) {
        startListening();
      }
    }
  };

  // Manual Mic Toggle (Done Speaking / Tap to Speak)
  const toggleRecording = () => {
    if (callState !== 'active') {
      startCall();
      return;
    }
    if (isRecording) {
      stopManualRecordingAndSend();
    } else {
      isMicMutedByUserRef.current = false;
      setMicStatusNotice(null);
      startServerSttRecording(true);
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
    <div className="space-y-6 sm:space-y-8">
      {/* Header & Scenario Selector */}
      <div className="glass-panel p-4 sm:p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            <i className="fa-solid fa-phone text-indigo-400" />
            Real-Time Live Voice Phone Simulator
          </h2>
          <p className="text-xs text-slate-400">Continuous hands-free phone conversation with sub-300ms Groq LPU LLM & Sarvam AI voice synthesis</p>
        </div>

        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 w-full md:w-auto">
          {/* Hands-Free Live Call Toggle */}
          <label className="flex items-center justify-center sm:justify-start gap-2 bg-slate-900 border border-white/10 px-3 py-2 sm:py-1.5 rounded-xl text-xs font-semibold cursor-pointer w-full sm:w-auto">
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

          <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full sm:w-auto">
            <span className="text-xs font-semibold text-slate-400 whitespace-nowrap">Workflow Scenario:</span>
            <select
              value={selectedWorkflowId}
              onChange={(e) => {
                setSelectedWorkflowId(e.target.value);
                setCallState('idle');
                setMessages([]);
              }}
              className="w-full sm:w-auto min-w-0 bg-slate-900 border border-white/10 text-xs font-bold rounded-xl px-3 py-2 text-indigo-300 focus:outline-none focus:border-indigo-500 cursor-pointer"
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
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-6 lg:gap-8 items-start">
        {/* Left Column: Config Controls & Live Database (order-2 on mobile, order-1 on lg) */}
        <div className="order-2 lg:order-1 lg:col-span-4 space-y-4">

          {/* Mobile Accordion Toggle for Caller Profile & Hardware Settings */}
          <button
            type="button"
            onClick={() => setShowMobileSettings(!showMobileSettings)}
            className="w-full lg:hidden flex items-center justify-between p-3.5 rounded-xl bg-slate-900/90 border border-white/10 text-xs font-bold text-slate-200 cursor-pointer shadow-sm"
          >
            <span className="flex items-center gap-2">
              <i className="fa-solid fa-user-gear text-indigo-400 text-sm" />
              Simulated Caller & Hardware Settings
            </span>
            <i className={`fa-solid fa-chevron-down text-slate-400 transition-transform duration-200 ${showMobileSettings ? 'rotate-180' : ''}`} />
          </button>

          {/* Caller Details & Diagnostic Test (Collapsible on mobile < lg, always visible on lg+) */}
          <div className={`${showMobileSettings ? 'block' : 'hidden lg:block'} space-y-4 animate-fade-in`}>
            {/* Caller Details Config */}
            <div className="glass-panel p-4 sm:p-5 space-y-3">
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

          {/* Microphone Hardware Diagnostic & Test */}
          <div className="glass-panel p-4 space-y-2 border border-emerald-500/20">
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                <i className="fa-solid fa-microphone text-emerald-400" />
                Mic Hardware Status
              </h4>
              <span className={`text-[10px] px-2 py-0.5 rounded font-bold flex-shrink-0 ${
                micPermission === 'granted' ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/30' :
                micPermission === 'denied' ? 'bg-rose-950 text-rose-300 border border-rose-500/30' :
                'bg-slate-800 text-slate-400'
              }`}>
                {micPermission === 'granted' ? '● Ready' : micPermission === 'denied' ? '⚠️ Blocked' : '○ Not Tested'}
              </span>
            </div>

            {/* Live Volume Meter Bar */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span>Input Signal</span>
                <span className="font-mono text-emerald-400 font-bold">{audioLevel}%</span>
              </div>
              <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden border border-white/5">
                <div
                  className={`h-full transition-all duration-75 ${audioLevel > 15 ? 'bg-emerald-400' : 'bg-indigo-500'}`}
                  style={{ width: `${Math.max(2, audioLevel)}%` }}
                />
              </div>
            </div>

            <button
              type="button"
              onClick={runMicTest}
              disabled={isMicTesting}
              className="w-full mt-2 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-white/10 text-xs font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-50 cursor-pointer"
            >
              <i className={`fa-solid ${isMicTesting ? 'fa-spinner animate-spin text-indigo-400' : 'fa-vial text-emerald-400'}`} />
              <span>{isMicTesting ? 'Testing Microphone (3s)...' : 'Test Microphone & Transcribe'}</span>
            </button>

            {micTestResult && (
              <p className="text-[11px] p-2 bg-slate-950 rounded border border-white/10 text-slate-300 leading-snug break-words animate-fade-in">
                {micTestResult}
              </p>
            )}
            </div>
          </div>

          {/* Live Database Fields Tracking Card */}
          <div className="glass-panel p-4 sm:p-5 space-y-3 border border-indigo-500/30 shadow-lg">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-bold text-slate-200 uppercase flex items-center gap-1.5">
                <i className="fa-solid fa-database text-indigo-400" /> Database Fields (Live)
              </h3>
              {currentRecordId && (
                <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-500/40 truncate max-w-[40%]">
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
                  <div className="space-y-2 max-h-[300px] sm:max-h-[380px] overflow-y-auto pr-1">
                    {allFields.map((field) => {
                      const val = collectedData[field.key];
                      const isFilled = val !== undefined && val !== null && val !== '';
                      const isUpdated = recentlyUpdatedFields.includes(field.key);

                      return (
                        <div
                          key={field.key}
                          className={`p-2.5 rounded-xl border text-xs transition-all ${
                            isUpdated
                              ? 'bg-cyan-950/50 border-cyan-400 shadow-md ring-1 ring-cyan-400/60 animate-pulse'
                              : isFilled
                              ? 'bg-slate-900/90 border-emerald-500/50 shadow-sm'
                              : field.required
                              ? 'bg-slate-900/50 border-amber-500/30'
                              : 'bg-slate-900/30 border-white/5'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-semibold text-slate-200 text-[11px] flex items-center gap-1 min-w-0 truncate">
                              {field.label}
                              {field.required && <span className="text-amber-400 font-bold flex-shrink-0" title="Required">*</span>}
                            </span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium flex-shrink-0 ${
                              isUpdated
                                ? 'bg-cyan-500/30 text-cyan-200 border border-cyan-400 font-bold'
                                : isFilled
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : field.required
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse'
                                : 'bg-slate-800 text-slate-400'
                            }`}>
                              {isUpdated ? '✓ Updated' : isFilled ? '✓ Stored' : field.required ? 'Pending Question' : 'Optional'}
                            </span>
                          </div>

                          <div className="mt-1 text-[11px]">
                            {isFilled ? (
                              <span className={`font-mono font-semibold break-words block ${isUpdated ? 'text-cyan-300 font-bold' : 'text-emerald-400'}`}>
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

        {/* Center & Right Column: Interactive Phone Device Frame (order-1 on mobile, order-2 on lg) */}
        <div className="order-1 lg:order-2 lg:col-span-8">
          <div className="glass-panel p-3 sm:p-6 max-w-2xl mx-auto border-2 border-indigo-500/30 shadow-2xl relative">
            {/* Phone Top Notch & Status */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-white/10 pb-4 mb-4 gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-3 h-3 rounded-full flex-shrink-0 ${callState === 'active' ? 'bg-emerald-500 animate-ping' : callState === 'ringing' ? 'bg-amber-500 animate-pulse' : 'bg-slate-600'}`} />
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-white truncate">
                    {activeBusiness?.name || 'Voice Assistant'}
                  </h3>
                  <p className="text-[11px] text-indigo-300 truncate">{activeWorkflow?.name}</p>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
                <div className="flex items-center flex-wrap gap-2">
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
                    className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs sm:text-sm shadow-lg shadow-emerald-500/25 transition-all cursor-pointer"
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
                    onClick={() => endCall(false)}
                    className="w-full sm:w-auto flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 text-rose-200 border border-rose-500/30 text-xs font-bold transition-all cursor-pointer"
                    title={isEndingCall ? "Click to disconnect immediately" : "Conclude call with closing thank you message"}
                  >
                    {isEndingCall ? (
                      <>
                        <i className="fa-solid fa-spinner animate-spin text-amber-300" /> Ending Call...
                      </>
                    ) : (
                      <>
                        <i className="fa-solid fa-phone-slash" /> End Call
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            {/* Call Finished / Database Fields Satisfied Banner */}
            {callCompletionNotice && (
              <div className="bg-emerald-950/80 border-2 border-emerald-500/60 p-3.5 rounded-2xl mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-emerald-100 shadow-xl animate-fade-in">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-400 flex-shrink-0">
                    <i className="fa-solid fa-circle-check text-base" />
                  </div>
                  <div className="min-w-0 break-words">
                    <div className="font-bold text-sm text-emerald-300">All Database Fields Captured • Call Concluded</div>
                    <div className="text-[11px] text-emerald-200/90">{callCompletionNotice}</div>
                  </div>
                </div>
                <button
                  onClick={startCall}
                  className="w-full sm:w-auto px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md transition-all cursor-pointer flex items-center justify-center gap-1.5 flex-shrink-0"
                >
                  <i className="fa-solid fa-rotate-right" />
                  <span>Start New Call</span>
                </button>
              </div>
            )}

            {/* Calendar Event Confirmed & Scheduled Banner */}
            {calendarBookingNotice && (
              <div className="bg-gradient-to-r from-emerald-950/90 to-purple-950/90 border-2 border-emerald-500/50 p-3.5 rounded-2xl mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-emerald-100 shadow-xl animate-fade-in">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-400 flex-shrink-0 text-base">
                    📅
                  </div>
                  <div className="min-w-0 break-words">
                    <div className="font-bold text-sm text-emerald-300 flex flex-wrap items-center gap-2">
                      <span>Order Confirmed & Scheduled in Google Calendar!</span>
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full font-mono font-bold">
                        ✓ Confirmed
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-300 mt-0.5 break-words">
                      <strong>{calendarBookingNotice.title}</strong> &bull; {new Date(calendarBookingNotice.time).toLocaleString()}
                    </div>
                  </div>
                </div>
                {onNavigateToCalendar && (
                  <button
                    onClick={() => onNavigateToCalendar(calendarBookingNotice.time)}
                    className="w-full sm:w-auto px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs shadow-md transition-all cursor-pointer flex items-center justify-center gap-1.5 flex-shrink-0"
                  >
                    <i className="fa-solid fa-calendar-days" />
                    <span>View in Calendar</span>
                  </button>
                )}
              </div>
            )}

            {/* Dynamic Natural Language Switch Banner Notice */}
            {languageSwitchNotice && (
              <div className="bg-gradient-to-r from-indigo-950 to-slate-900 p-2.5 rounded-xl border border-indigo-500/40 mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-indigo-200 animate-bounce">
                <span className="font-bold flex items-center gap-2 break-words">
                  <i className="fa-solid fa-arrows-rotate text-indigo-300" />
                  {languageSwitchNotice}
                </span>
                <span className="text-[10px] text-indigo-300">Sarvam AI / ElevenLabs voice updated</span>
              </div>
            )}

            {/* Continuous Voice Session Active Notification */}
            {callState === 'active' && isHandsFree && (
              <div className="bg-emerald-950/40 border border-emerald-500/30 px-3.5 py-2 rounded-xl mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-emerald-200">
                <span className="flex items-center gap-2 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping flex-shrink-0" />
                  🎙️ Continuous Voice Testing Active: Mic stays ON after each AI reply. Speak turn-by-turn hands-free!
                </span>
                <span className="text-[10px] text-emerald-400 font-bold bg-emerald-900/50 px-2 py-0.5 rounded-lg border border-emerald-500/20 flex-shrink-0">
                  Turn-by-Turn
                </span>
              </div>
            )}

            {/* Microphone Status / Guidance Notice */}
            {micStatusNotice && (
              <div className="bg-slate-900/90 p-2.5 rounded-xl border border-amber-500/30 mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-amber-200 animate-fade-in">
                <span className="font-semibold flex items-center gap-2 break-words">
                  <i className="fa-solid fa-info-circle text-amber-400 flex-shrink-0" />
                  {micStatusNotice}
                </span>
                <button onClick={() => setMicStatusNotice(null)} className="text-slate-400 hover:text-white text-xs flex-shrink-0">✕</button>
              </div>
            )}

            {/* Audio Waveform Equalizer & Live Voice Status */}
            {(isPlayingAudio || isRecording || isProcessing || liveTranscript) && (
              <div className="bg-gradient-to-r from-slate-900 via-indigo-950/80 to-slate-900 p-3 sm:p-3.5 rounded-2xl border border-indigo-500/40 mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xl">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-8 h-8 rounded-full border flex items-center justify-center animate-pulse flex-shrink-0 ${
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
                  <div className="min-w-0">
                    <span className="text-xs font-bold text-white block break-words">
                      {isPlayingAudio
                        ? `AI Assistant Speaking (Human Voice • ${langInfo.label})`
                        : liveTranscript
                        ? `Hearing: "${liveTranscript}..."`
                        : isRecording
                        ? `🎙️ Listening... ${isHandsFree ? 'Continuous Hands-Free' : 'Tap-to-Talk'} (Live Mic: ${audioLevel}%)`
                        : `AI Assistant thinking & checking tools...`}
                    </span>
                    <span className="text-[10px] text-indigo-300 block break-words">
                      {isPlayingAudio
                        ? 'Natural speech streaming • Mic temporarily paused to prevent echo'
                        : isRecording
                        ? (audioLevel > 12 ? '🗣️ Voice detected! Speak naturally (auto-sends on pause)' : 'Speak into your microphone or tap "Done Speaking"')
                        : 'Evaluating conversation state & executing tools'}
                    </span>
                  </div>
                </div>
                {/* 8-Bar Dynamic Equalizer Reactive to Real Mic Level */}
                <div className="flex items-center gap-1.5 h-8 px-2 bg-slate-950/60 rounded-xl border border-indigo-500/20 self-center sm:self-auto flex-shrink-0">
                  {[0.7, 1.0, 0.85, 1.2, 0.9, 1.1, 0.8, 0.95].map((factor, idx) => {
                    const dynamicHeight = isPlayingAudio
                      ? undefined
                      : isRecording
                      ? Math.min(100, Math.max(16, Math.round(audioLevel * factor)))
                      : 20;

                    return (
                      <div
                        key={idx}
                        className={`w-1.5 rounded-full transition-all duration-75 ${
                          isPlayingAudio
                            ? 'eq-bar bg-indigo-500'
                            : isRecording
                            ? (audioLevel > 14 ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-emerald-600/50')
                            : 'bg-slate-700'
                        }`}
                        style={dynamicHeight !== undefined ? { height: `${dynamicHeight}%` } : undefined}
                      />
                    );
                  })}
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
                    <div key={idx} className="bg-slate-900 border border-indigo-500/30 px-3 py-1.5 rounded-lg text-xs font-mono text-indigo-200 flex items-start gap-2 max-w-full">
                      <span className="text-emerald-400 flex-shrink-0">✓ {t.tool}</span>
                      <span className="text-[10px] text-slate-400 break-all">({JSON.stringify(t.args)})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Chat Transcript Area */}
            <div className="bg-slate-900/90 rounded-2xl p-3 sm:p-4 min-h-[260px] sm:min-h-[320px] max-h-[380px] sm:max-h-[420px] overflow-y-auto border border-white/5 space-y-3">
              {messages.length === 0 ? (
                <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-xs space-y-2 text-center px-4">
                  <i className="fa-solid fa-phone-slash text-3xl text-slate-600 animate-bounce" />
                  <p>Click "Start Live Voice Call" or start speaking to initiate the phone call!</p>
                </div>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-3 rounded-2xl max-w-[90%] sm:max-w-[85%] text-xs space-y-1 break-words ${
                      msg.role === 'user'
                        ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white ml-auto rounded-br-none shadow-md shadow-indigo-500/20'
                        : 'bg-slate-800 border border-white/10 text-slate-200 mr-auto rounded-bl-none'
                    }`}
                  >
                    <div className="text-[10px] font-bold text-slate-400 flex items-center justify-between gap-2">
                      <span className="truncate">{msg.role === 'user' ? `👤 ${callerName}` : `🤖 AI Voice Assistant`}</span>
                      {msg.role === 'assistant' && (
                        <button
                          onClick={() => speakText(msg.content)}
                          className="hover:text-indigo-300 cursor-pointer flex-shrink-0"
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
                <div className="bg-emerald-950/60 border border-emerald-500/30 text-emerald-200 p-3 rounded-2xl ml-auto rounded-br-none text-xs flex items-center gap-2 max-w-[90%] sm:max-w-[85%] break-words animate-pulse">
                  <i className="fa-solid fa-microphone text-emerald-400 text-xs flex-shrink-0" />
                  <span className="font-semibold text-emerald-300 flex-shrink-0">Hearing:</span>
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

            {/* Controls Bar: Voice Recording & Text Input */}
            {callState === 'active' && (
              <div className="mt-4 space-y-2">
                {/* Voice Action & Hardware Status Strip */}
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 bg-slate-900/90 border border-white/10 p-2.5 rounded-xl">
                  <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
                    <button
                      type="button"
                      onClick={toggleRecording}
                      className={`w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs sm:text-sm font-bold transition-all shadow-md cursor-pointer ${
                        isRecording
                          ? 'bg-rose-600 hover:bg-rose-500 text-white animate-pulse ring-2 ring-rose-400/50'
                          : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-500/20'
                      }`}
                    >
                      <i className={`fa-solid ${isRecording ? 'fa-stop' : 'fa-microphone'} text-sm`} />
                      <span>{isRecording ? '⏹️ Done Speaking (Send)' : '🎙️ Tap to Speak (Voice Input)'}</span>
                    </button>

                    {/* Live Audio Volume Level Meter */}
                    <div className="flex items-center justify-between sm:justify-start gap-1.5 px-3 py-1.5 bg-slate-950 rounded-lg border border-white/5 text-[11px]">
                      <span className="text-slate-400">Mic Level:</span>
                      <div className="w-16 h-2 bg-slate-800 rounded-full overflow-hidden flex">
                        <div
                          className={`h-full transition-all duration-75 ${audioLevel > 15 ? 'bg-emerald-400' : 'bg-indigo-400'}`}
                          style={{ width: `${Math.max(5, audioLevel)}%` }}
                        />
                      </div>
                      <span className={`font-mono text-[10px] ${audioLevel > 15 ? 'text-emerald-400 font-bold' : 'text-slate-500'}`}>
                        {audioLevel}%
                      </span>
                    </div>
                  </div>

                  {/* Mode & Permissions Toggle */}
                  <div className="flex items-center gap-2 text-[11px] justify-between sm:justify-end">
                    <button
                      type="button"
                      onClick={() => setIsHandsFree(!isHandsFree)}
                      className={`px-2.5 py-1 rounded-lg border text-[10px] font-semibold transition-all cursor-pointer ${
                        isHandsFree
                          ? 'bg-indigo-950/60 text-indigo-300 border-indigo-500/30'
                          : 'bg-slate-800 text-slate-400 border-white/10'
                      }`}
                      title="Turn Hands-Free Automatic Turn-Taking ON or OFF"
                    >
                      {isHandsFree ? '⚡ Hands-Free: ON' : '✋ Tap-to-Speak Mode'}
                    </button>

                    {micPermission === 'denied' && (
                      <button
                        onClick={getOrInitMicStream}
                        className="text-rose-400 hover:text-rose-300 text-[10px] font-bold underline cursor-pointer"
                      >
                        ⚠️ Allow Mic
                      </button>
                    )}
                  </div>
                </div>

                {/* Text Fallback Input Row */}
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Or type customer reply in English, Hindi (हिन्दी), or Kannada (ಕನ್ನಡ)..."
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                    className="flex-1 min-w-0 bg-slate-900 border border-white/10 rounded-xl px-3 sm:px-4 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />

                  <button
                    type="button"
                    onClick={() => handleSendMessage()}
                    disabled={!inputMessage.trim() || isProcessing}
                    className="px-3 sm:px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition-all disabled:opacity-50 cursor-pointer text-xs flex items-center gap-1.5 flex-shrink-0"
                  >
                    <span className="hidden xs:inline">Send</span>
                    <i className="fa-solid fa-paper-plane text-xs" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
