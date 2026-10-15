import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useDemoToken, useSessionIsCurrent } from '../session/demo-session'
import {
  evidenceAccessLost,
  evidenceApi,
  evidenceErrorMessage,
  EvidenceResponseError,
} from './api'
import type { SupportEvidence } from './schemas'

type Saved =
  | { kind: 'ready'; value: SupportEvidence }
  | { kind: 'unavailable'; message: string; accessLost: boolean }

export function useSupportEvidence({
  reportId,
  onAccessLost,
}: {
  reportId: string
  onAccessLost: () => void
}) {
  const token = useDemoToken()
  const isCurrent = useSessionIsCurrent()
  const client = useQueryClient()
  const key = useMemo(
    () => ['support-evidence', token, reportId],
    [token, reportId],
  )
  const api = useMemo(() => evidenceApi(token, reportId), [token, reportId])
  // Ignore mutation results after navigating away from this report.
  const mounted = useRef(true)
  // Access loss immediately blocks late results and further commands.
  const accessRevoked = useRef(false)
  // Block a second submission before mutation.isPending reaches the UI.
  const submissionInFlight = useRef(false)
  // Keep the same operation identity after an uncertain write, including refresh.
  const operationId = useRef<string | undefined>(undefined)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
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
        if (
          evidenceAccessLost(error) ||
          error instanceof EvidenceResponseError
        ) {
          if (evidenceAccessLost(error)) accessRevoked.current = true
          return {
            kind: 'unavailable',
            message: evidenceErrorMessage(error),
            accessLost: evidenceAccessLost(error),
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
    mutationFn: (id: string) => api.create(id),
    onMutate: async () => {
      await client.cancelQueries({ queryKey: key })
    },
    onSuccess: async (value) => {
      if (!current()) return
      await client.cancelQueries({ queryKey: key })
      if (!current()) return
      client.setQueryData<Saved>(key, () => ({ kind: 'ready', value }))
      operationId.current =
        value.status === 'pending'
          ? (value.operation_id ?? undefined)
          : undefined
      setNeedsRefresh(false)
    },
    onError: (error) => {
      if (!current()) return
      setNeedsRefresh(true)
      if (evidenceAccessLost(error) || error instanceof EvidenceResponseError) {
        if (evidenceAccessLost(error)) accessRevoked.current = true
        void client.cancelQueries({ queryKey: key })
        client.setQueryData<Saved>(key, () => ({
          kind: 'unavailable',
          message: evidenceErrorMessage(error),
          accessLost: evidenceAccessLost(error),
        }))
      }
    },
    onSettled: () => {
      submissionInFlight.current = false
    },
  })
  const busy = query.isFetching || mutation.isPending
  const disabled =
    busy ||
    needsRefresh ||
    query.isError ||
    !saved ||
    saved.status === 'pending'
  function analyze() {
    if (disabled || submissionInFlight.current || !current()) return
    submissionInFlight.current = true
    operationId.current ??= crypto.randomUUID()
    mutation.mutate(operationId.current)
  }
  async function refresh() {
    const result = await query.refetch()
    if (!current() || !result.isSuccess) return
    if (
      result.data.kind === 'ready' &&
      result.data.value.operation_id === operationId.current &&
      result.data.value.status !== 'pending'
    )
      operationId.current = undefined
    setNeedsRefresh(false)
    mutation.reset()
  }
  const error =
    query.data?.kind === 'unavailable'
      ? query.data.message
      : mutation.isError
        ? evidenceErrorMessage(mutation.error)
        : query.isError
          ? evidenceErrorMessage(query.error)
          : undefined
  return {
    query,
    saved,
    mutation,
    needsRefresh,
    busy,
    disabled,
    analyze,
    refresh,
    error,
  }
}
