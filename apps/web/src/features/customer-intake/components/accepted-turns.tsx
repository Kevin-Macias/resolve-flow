import type { CustomerRun } from '../schemas'

export function AcceptedTurns({ turns }: { turns: CustomerRun['turns'] }) {
  if (!turns.length) return null
  return (
    <section className="mt-6" aria-labelledby="accepted-answers-heading">
      <h3 id="accepted-answers-heading" className="font-semibold">
        Previous answers
      </h3>
      {turns.map((turn) => (
        <div className="mt-4" key={turn.round_number}>
          <p className="hint">Round {turn.round_number}</p>
          <dl>
            {turn.questions.map((question, index) => (
              <div className="mt-3" key={index}>
                <dt>{question}</dt>
                <dd className="whitespace-pre-wrap">{turn.answers[index]}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  )
}
