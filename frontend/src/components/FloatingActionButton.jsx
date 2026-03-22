export default function FloatingActionButton({ onNewCase }) {
  return (
    <div className="floating-actions" aria-label="Actions">
      <div className="floating-menu" role="menu" aria-label="Create">
        <button
          type="button"
          className="floating-menu-item"
          role="menuitem"
          onClick={() => onNewCase?.()}
        >
          New Case
        </button>
      </div>
      <button
        type="button"
        className="floating-action-button"
        aria-haspopup="menu"
        aria-label="Show new case option (hover or focus)"
      >
        +
      </button>
    </div>
  )
}
