export function ServiceInput({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  disabled: boolean
}) {
  return (
    <>
      <label className="form-label" htmlFor="service-code">
        Affected service code (optional)
      </label>
      <input
        className="form-field"
        id="service-code"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        autoComplete="off"
        aria-describedby="service-help"
      />
      <p id="service-help" className="hint">
        Enter a known service code, or leave blank for no service. Unknown codes
        are rejected.
      </p>
    </>
  )
}
