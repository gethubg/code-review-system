import { useState, useEffect, useRef, useCallback } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export type ProgressEventType =
  | 'agent_start'
  | 'agent_complete'
  | 'finding'
  | 'progress'
  | 'error'
  | 'complete'

export interface ProgressMessage {
  type: ProgressEventType
  timestamp: string
  agent?: string
  message: string
  data?: Record<string, unknown>
}

// ── Constants ────────────────────────────────────────────────────────────────

const RECONNECT_DELAY_MS = 2_000
const MAX_RECONNECT_ATTEMPTS = 10

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useProgressFeed(runId: string | null): {
  messages: ProgressMessage[]
  isConnected: boolean
  clearMessages: () => void
} {
  const [messages, setMessages] = useState<ProgressMessage[]>([])
  const [isConnected, setIsConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const attemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const clearMessages = useCallback(() => setMessages([]), [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    if (!runId) {
      // Clean up any existing connection when runId is cleared.
      wsRef.current?.close()
      wsRef.current = null
      setIsConnected(false)
      return
    }

    attemptsRef.current = 0

    function connect() {
      if (!mountedRef.current) return
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) return

      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const host = window.location.host
      const url = `${protocol}://${host}/ws/progress/${runId}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return }
        attemptsRef.current = 0
        setIsConnected(true)
      }

      ws.onmessage = (event: MessageEvent<string>) => {
        if (!mountedRef.current) return
        try {
          const msg = JSON.parse(event.data) as ProgressMessage
          setMessages(prev => [...prev, msg])
        } catch {
          // Ignore unparseable frames.
        }
      }

      ws.onerror = () => {
        // onclose will fire immediately after; handle reconnect there.
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setIsConnected(false)
        wsRef.current = null
        attemptsRef.current += 1

        if (attemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }
    }

    connect()

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
      setIsConnected(false)
    }
  }, [runId])

  return { messages, isConnected, clearMessages }
}
