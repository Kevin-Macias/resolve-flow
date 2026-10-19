export function limitErrorMessage(status: number): string | undefined {
  if (status === 408)
    return 'The upload took too long. Check your connection before trying again.'
  if (status === 413)
    return 'This request is too large. Shorten the supplied text before trying again.'
  if (status === 429)
    return 'Too many requests. Wait before trying again.'
  return undefined
}
