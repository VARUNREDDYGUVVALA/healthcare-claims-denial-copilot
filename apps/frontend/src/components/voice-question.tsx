import { useEffect, useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'

type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: {results: ArrayLike<ArrayLike<{transcript: string}>>}) => void) | null
  onerror: ((event: {error: string}) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
type SpeechWindow = Window & {
  SpeechRecognition?: new () => Recognition
  webkitSpeechRecognition?: new () => Recognition
}

const errors: Record<string, string> = {
  'not-allowed': 'Microphone permission was not granted. Allow microphone access for this site or type your question.',
  'service-not-allowed': 'The browser blocked speech recognition. You can still type your question.',
  'audio-capture': 'No microphone was available. Check your device or type your question.',
  'no-speech': 'No speech was detected. Try again or type your question.',
  network: 'The browser’s speech service could not be reached. Try again or type your question.',
}

export function VoiceQuestion({ onTranscript }: {onTranscript: (transcript: string) => void}) {
  const speech = window as SpeechWindow
  const RecognitionClass = speech.SpeechRecognition ?? speech.webkitSpeechRecognition
  const active = useRef<Recognition | null>(null)
  const [mode, setMode] = useState<'idle' | 'listening' | 'stopping'>('idle')
  const [feedback, setFeedback] = useState('')

  useEffect(() => () => {
    const instance = active.current
    active.current = null
    if (instance) {
      instance.onresult = null
      instance.onerror = null
      instance.onend = null
      instance.abort()
    }
  }, [])

  function start() {
    if (!RecognitionClass || active.current) return
    const instance = new RecognitionClass()
    active.current = instance
    let transcript = ''
    let failed = false
    instance.lang = 'en-US'
    instance.continuous = true
    instance.interimResults = false
    instance.onresult = event => {
      transcript = Array.from(event.results, result => (result[0]?.transcript ?? '').trim()).join(' ').trim()
    }
    instance.onerror = event => {
      failed = true
      setFeedback(errors[event.error] ?? 'Voice input stopped. Try again or type your question.')
    }
    instance.onend = () => {
      active.current = null
      setMode('idle')
      if (transcript) onTranscript(transcript)
      else if (!failed) setFeedback('No speech was detected. Try again or type your question.')
    }
    try {
      instance.start()
      setMode('listening')
      setFeedback('')
    } catch {
      active.current = null
      setFeedback('Could not start the microphone. You can still type your question.')
    }
  }

  function stop() {
    if (!active.current || mode !== 'listening') return
    setMode('stopping')
    active.current.stop()
  }

  return <div className="voice-question">
    {RecognitionClass ? <>
      <button className="voice-button" type="button" disabled={mode === 'stopping'} onClick={mode === 'idle' ? start : stop}>
        {mode === 'idle' ? <><Mic size={16}/> Use microphone</> : <><Square size={14}/> {mode === 'listening' ? 'Stop microphone' : 'Finishing transcription…'}</>}
      </button>
      <small>Use fictional data only. Your browser may send microphone audio to its speech recognition service.</small>
    </> : <small>Voice input is unavailable in this browser. You can still type your question.</small>}
    <div aria-live="polite">{feedback || (mode === 'listening' ? 'Listening. Speak your question, then stop the microphone.' : '')}</div>
  </div>
}
