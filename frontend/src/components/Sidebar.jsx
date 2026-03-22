import { NavLink } from 'react-router-dom'

export default function Sidebar() {
  const items = [
    { to: '/', end: true, icon: 'H', label: 'Home' },
    { to: '/chat', end: true, icon: 'C', label: 'Assistant chat' },
  ]

  return (
    <aside className="left-sidebar" aria-label="Primary">
      <div className="left-sidebar-icons">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar-icon-button${isActive ? ' sidebar-icon-button--active' : ''}`
            }
            aria-label={item.label}
            title={item.label}
          >
            <span aria-hidden="true">{item.icon}</span>
          </NavLink>
        ))}
      </div>
    </aside>
  )
}
