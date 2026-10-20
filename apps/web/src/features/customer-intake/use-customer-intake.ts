import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useSessionToken, useSessionIsCurrent } from '../session/workspace-session'
import {
  IntakeApiError,
  IntakeResponseError,
  intakeApi,
  intakeErrorMessage,
  intakeKeys,
  isAccessLost,
} from './api'
import type { ClarificationRequest, CustomerRun } from './schemas'
import { useIntakeStream } from './use-intake-stream'

type SavedIntake =
  | { kind: 'run'; run: CustomerRun }
  | { kind: 'absent' }
  | { kind: 'unavailable'; message: string; accessLost: boolean }
type Action =
  | { kind: 'start' }
  | { kind: 'reply'; runId: string; body: ClarificationRequest }
  | { kind: 'recover'; runId: string; revision: number }

export function useCustomerIntake(reportId: string, onAccessLost: () => void) {
  const token = useSessionToken()
  const isCurrent = useSessionIsCurrent()
  const client = useQueryClient()
  const key = useMemo(
    () => intakeKeys.report(token, reportId),
    [token, reportId],
  )
  const api = useMemo(() => intakeApi(token, reportId), [token, reportId])
  // Ignore mutation results after leaving this report.
  const isMounted = useRef(true)
  // Access loss blocks actions and late results immediately.
  const accessRevoked = useRef(false)
  // Block duplicate submissions before mutation.isPending reaches the UI.
  const submissionInFlight = useRef(false)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  useEffect(() => {
    isMounted.current = true
    return () => {
      isMounted.current = false
    }
  }, [])
  const save = useCallback(
    (value: SavedIntake) => {
      client.setQueryData<SavedIntake>(key, () => value)
    },
    [client, key],
  )
  const canApplyResult = () =>
    isMounted.current && isCurrent() && !accessRevoked.current
  const markAccessLost = useCallback(
    (message: string) => {
      accessRevoked.current = true
      void client.cancelQueries({ queryKey: key })
      save({ kind: 'unavailable', message, accessLost: true })
    },
    [client, key, save],
  )
  const query = useQuery({
    queryKey: key,
    gcTime: 0,
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }): Promise<SavedIntake> => {
      try {
        return { kind: 'run', run: await api.read(signal) }
      } catch (error) {
        const previous = client.getQueryData<SavedIntake>(key)
        if (
          error instanceof IntakeApiError &&
          error.status === 404 &&
          previous?.kind !== 'run' &&
          previous?.kind !== 'unavailable'
        )
          return { kind: 'absent' }
        if (isAccessLost(error)) accessRevoked.current = true
        if (isAccessLost(error) || error instanceof IntakeResponseError)
          return {
            kind: 'unavailable',
            message: intakeErrorMessage(error),
            accessLost: isAccessLost(error),
          }
        throw error
      }
    },
  })
  const run = query.data?.kind === 'run' ? query.data.run : undefined
  const unavailable = query.data?.kind === 'unavailable'
  const lost = query.data?.kind === 'unavailable' && query.data.accessLost
  useEffect(() => {
    if (lost) onAccessLost()
  }, [lost, onAccessLost])
  const refetch = query.refetch
  const refreshAfterStream = useCallback(() => {
    void refetch()
  }, [refetch])
  const handleStreamAccessLost = useCallback(() => {
    markAccessLost('Your access to this intake is no longer available.')
  }, [markAccessLost])
  const { snapshot, connection, connectionFailed, restart } = useIntakeStream({
    token,
    url: run ? api.streamUrl(run.run_id) : undefined,
    savedSnapshot: run?.snapshot,
    onEnd: refreshAfterStream,
    onAccessLost: handleStreamAccessLost,
  })
  const mutation = useMutation({
    retry: false,
    mutationFn: (action: Action) => {
      if (action.kind === 'start') return api.start()
      if (action.kind === 'recover')
        return api.recover(action.runId, action.revision)
      return api.clarify(action.runId, action.body)
    },
    onMutate: async () => {
      await client.cancelQueries({ queryKey: key })
    },
    onSuccess: async (saved) => {
      if (!canApplyResult()) return
      await client.cancelQueries({ queryKey: key })
      if (!canApplyResult()) return
      save({ kind: 'run', run: saved })
      setNeedsRefresh(false)
      restart()
    },
    onError: (error) => {
      if (!canApplyResult()) return
      setNeedsRefresh(true)
      if (isAccessLost(error)) {
        markAccessLost(intakeErrorMessage(error))
      }
    },
    onSettled: () => {
      submissionInFlight.current = false
    },
  })
  const busy = mutation.isPending || query.isFetching
  const disabled =
    busy ||
    needsRefresh ||
    query.isError ||
    unavailable ||
    (Boolean(run) && (connectionFailed || snapshot?.revision !== run?.revision))
  async function refresh() {
    const result = await query.refetch()
    if (!canApplyResult()) return
    if (result.isSuccess) {
      setNeedsRefresh(false)
      mutation.reset()
      restart()
    }
  }
  function submit(action: Action) {
    if (disabled || submissionInFlight.current || !canApplyResult()) return
    submissionInFlight.current = true
    mutation.mutate(action)
  }
  function reply(action: 'answer' | 'continue_incomplete', answers: string[]) {
    if (disabled || !run?.pending) return
    submit({
      kind: 'reply',
      runId: run.run_id,
      body: {
        operation_id: crypto.randomUUID(),
        expected_revision: run.revision,
        pending_id: run.pending.pending_id,
        action,
        answers,
      },
    })
  }
  return {
    query,
    run,
    snapshot,
    connection,
    connectionFailed,
    mutation,
    needsRefresh,
    busy,
    disabled,
    unavailable,
    refresh,
    start: () => {
      submit({ kind: 'start' })
    },
    reply,
    recover: () => {
      if (!disabled && run?.operation_pending)
        submit({
          kind: 'recover',
          runId: run.run_id,
          revision: run.revision,
        })
    },
  }
}
