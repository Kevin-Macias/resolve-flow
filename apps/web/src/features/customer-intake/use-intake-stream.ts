import { useCallback, useEffect, useState } from 'react'

import {
  startCustomerStream,
  type ConnectionState,
} from '../workflow-stream/client'
import type { CustomerSnapshot } from '../workflow-stream/contract'

type IntakeStreamOptions = {
  token: string
  url?: string
  savedSnapshot?: CustomerSnapshot
  onEnd: () => void
  onAccessLost: () => void
}

export function useIntakeStream({
  token,
  url,
  savedSnapshot,
  onEnd,
  onAccessLost,
}: IntakeStreamOptions) {
  const [streamedSnapshot, setStreamedSnapshot] = useState<CustomerSnapshot>()
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [subscription, setSubscription] = useState(0)

  const restart = useCallback(() => {
    setStreamedSnapshot(undefined)
    setSubscription((value) => value + 1)
  }, [])

  useEffect(() => {
    if (!url || !savedSnapshot) return
    // This flag belongs to this subscription, including after a restart.
    let stopped = false
    const stream = startCustomerStream({
      url,
      token,
      runId: savedSnapshot.run_id,
      initialSnapshot: savedSnapshot,
      onSnapshot: (snapshot) => {
        if (!stopped) setStreamedSnapshot(snapshot)
      },
      onEnd: () => {
        if (!stopped) onEnd()
      },
      onState: (state) => {
        if (stopped) return
        setConnection(state)
        if (state === 'access_lost') onAccessLost()
      },
    })
    return () => {
      stopped = true
      stream.stop()
    }
  }, [url, token, savedSnapshot, subscription, onEnd, onAccessLost])

  const snapshot =
    streamedSnapshot &&
    savedSnapshot &&
    streamedSnapshot.run_id === savedSnapshot.run_id &&
    streamedSnapshot.revision > savedSnapshot.revision
      ? streamedSnapshot
      : savedSnapshot
  const connectionFailed = [
    'reconnecting',
    'unavailable',
    'protocol_error',
    'access_lost',
  ].includes(connection)

  return { snapshot, connection, connectionFailed, restart }
}
