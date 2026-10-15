import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useDemoToken, useSessionIsCurrent } from '../session/demo-session'
import {
  actionsApi,
  actionAccessLost,
  actionErrorMessage,
  ActionResponseError,
  ActionApiError,
} from './api'
import {
  proposalRequestSchema,
  type SupportAction,
  type ProposalRequest,
  type ProposalFields,
  type DecisionRequest,
} from './schemas'

type Saved =
  | { kind: 'ready'; value: SupportAction }
  | { kind: 'unavailable'; message: string; accessLost: boolean }
type Command =
  | { kind: 'prepare'; body: ProposalRequest }
  | { kind: 'decide'; runId: string; body: DecisionRequest }

export function useSupportAction(reportId: string, onAccessLost: () => void) {
  const token = useDemoToken()
  const isCurrent = useSessionIsCurrent()
  const client = useQueryClient()
  const key = useMemo(
    () => ['support-action', token, reportId],
    [token, reportId],
  )
  const api = useMemo(() => actionsApi(token, reportId), [token, reportId])
  // Late results must not restore a report after navigation or access loss.
  const mounted = useRef(true)
  const accessRevoked = useRef(false)
  // The synchronous guard covers the interval before React disables the controls.
  const submissionInFlight = useRef(false)
  // Retry uncertain preparation with its original UUID and immutable body.
  const [acceptedPreparation, setAcceptedPreparation] =
    useState<ProposalRequest>()
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [online, setOnline] = useState(
    () => typeof navigator === 'undefined' || navigator.onLine,
  )
  useEffect(() => {
    mounted.current = true
    const update = () => {
      setOnline(navigator.onLine)
      setNeedsRefresh(true)
    }
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      mounted.current = false
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  const current = () => mounted.current && isCurrent() && !accessRevoked.current
  const query = useQuery({
    queryKey: key,
    gcTime: 0,
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }): Promise<Saved> => {
      try {
        return { kind: 'ready', value: await api.read(signal) }
      } catch (error) {
        if (actionAccessLost(error) || error instanceof ActionResponseError) {
          if (actionAccessLost(error)) accessRevoked.current = true
          return {
            kind: 'unavailable',
            message: actionErrorMessage(error),
            accessLost: actionAccessLost(error),
          }
        }
        throw error
      }
    },
  })
  const saved = query.data?.kind === 'ready' ? query.data.value : undefined
  const lost = query.data?.kind === 'unavailable' && query.data.accessLost
  useEffect(() => {
    if (lost) onAccessLost()
  }, [lost, onAccessLost])
  const mutation = useMutation({
    retry: false,
    mutationFn: (command: Command) =>
      command.kind === 'prepare'
        ? api.prepare(command.body)
        : api.decide(command.runId, command.body),
    onMutate: async () => {
      await client.cancelQueries({ queryKey: key })
    },
    onSuccess: async (value, command) => {
      if (!current()) return
      await client.cancelQueries({ queryKey: key })
      if (!current()) return
      client.setQueryData<Saved>(key, () => ({ kind: 'ready', value }))
      if (command.kind === 'prepare') setAcceptedPreparation(undefined)
      setNeedsRefresh(false)
    },
    onError: async (error) => {
      if (!current()) return
      setNeedsRefresh(true)
      if (actionAccessLost(error) || error instanceof ActionResponseError) {
        if (actionAccessLost(error)) accessRevoked.current = true
        await client.cancelQueries({ queryKey: key })
        if (!mounted.current || !isCurrent()) return
        client.setQueryData<Saved>(key, () => ({
          kind: 'unavailable',
          message: actionErrorMessage(error),
          accessLost: actionAccessLost(error),
        }))
      } else if (error instanceof ActionApiError && error.status === 409) {
        await query.refetch() // Read-only reconciliation; confirmation remains closed.
      }
    },
    onSettled: () => {
      submissionInFlight.current = false
    },
  })
  const busy = mutation.isPending || query.isFetching
  const blocked = busy || needsRefresh || query.isError || !saved || !online
  const decisionDisabled =
    blocked ||
    saved?.status !== 'awaiting_decision' ||
    saved.archived ||
    saved.input_stale
  const prepareDisabled = blocked || !saved?.can_prepare
  function submit(command: Command) {
    if (blocked || submissionInFlight.current || !current()) return
    submissionInFlight.current = true
    mutation.mutate(command)
  }
  function prepare(fields: ProposalFields) {
    if (prepareDisabled || submissionInFlight.current) return
    const body =
      acceptedPreparation ??
      proposalRequestSchema.parse({
        ...fields,
        operation_id: crypto.randomUUID(),
        expected_fingerprint: saved?.fingerprint ?? null,
      })
    setAcceptedPreparation(body)
    submit({ kind: 'prepare', body })
  }
  function finishPreparation() {
    if (!blocked && saved?.pending_preparation)
      submit({ kind: 'prepare', body: saved.pending_preparation })
  }
  async function refresh() {
    const result = await query.refetch()
    if (!current() || !result.isSuccess || result.data.kind !== 'ready') return
    if (
      acceptedPreparation &&
      result.data.value.status !== 'preparing' &&
      (result.data.value.preparation_id === acceptedPreparation.operation_id ||
        result.data.value.fingerprint !==
          acceptedPreparation.expected_fingerprint)
    )
      setAcceptedPreparation(undefined)
    setNeedsRefresh(false)
    mutation.reset()
  }
  function decide(body: DecisionRequest) {
    if (decisionDisabled || !saved?.run_id) return
    submit({ kind: 'decide', runId: saved.run_id, body })
  }
  const error =
    query.data?.kind === 'unavailable'
      ? query.data.message
      : mutation.isError
        ? actionErrorMessage(mutation.error)
        : query.isError
          ? actionErrorMessage(query.error)
          : undefined
  return {
    query,
    saved,
    mutation,
    busy,
    blocked,
    decisionDisabled,
    prepareDisabled,
    needsRefresh,
    online,
    error,
    prepare,
    finishPreparation,
    refresh,
    decide,
    acceptedPreparation,
    retryPreparation: () => {
      if (acceptedPreparation)
        submit({ kind: 'prepare', body: acceptedPreparation })
    },
  }
}
