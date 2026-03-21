export default function Sidebar({ currentView, onGoHome, onShowChat }) {
  const items = [
    { id: 'home', icon: 'H', label: 'Home', onClick: onGoHome },
    { id: 'chat', icon: 'C', label: 'Chat', onClick: onShowChat },
  ]

  return (
    <aside className="left-sidebar" aria-label="Primary">
      <div className="left-sidebar-icons">
        {items.map((item) => {
          const isActive =
            (item.id === 'home' && currentView === 'home') ||
            (item.id === 'chat' && currentView === 'chat')

          return (
            <button
              key={item.id}
              type="button"
              className={`sidebar-icon-button${isActive ? ' sidebar-icon-button--active' : ''}`}
              aria-label={item.label}
              title={item.label}
              onClick={item.onClick}
            >
              <span aria-hidden="true">{item.icon}</span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}