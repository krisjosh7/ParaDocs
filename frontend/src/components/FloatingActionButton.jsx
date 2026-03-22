export default function FloatingActionButton({ onNewCase }) {
  return (
    <button
      type="button"
      className="floating-new-case-fab"
      aria-label="New case"
      onClick={() => onNewCase?.()}
    >
      <span className="floating-new-case-fab__grow">
        <span className="floating-new-case-fab__label">New Case</span>
      </span>
      <span className="floating-new-case-fab__icon" aria-hidden>
        +
      </span>
    </button>
  )
}
