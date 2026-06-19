import { NavLink } from 'react-router-dom'
import { ShieldCheck, History, Search } from 'lucide-react'

export function NavBar() {
  return (
    <header className="navbar">
      <div className="navbar__brand">
        <ShieldCheck size={22} aria-hidden="true" />
        <span>Code Review</span>
      </div>
      <nav className="navbar__nav" aria-label="Main navigation">
        <NavLink
          to="/"
          end
          className={({ isActive }) => `navbar__link${isActive ? ' navbar__link--active' : ''}`}
        >
          <Search size={16} aria-hidden="true" />
          Review
        </NavLink>
        <NavLink
          to="/history"
          className={({ isActive }) => `navbar__link${isActive ? ' navbar__link--active' : ''}`}
        >
          <History size={16} aria-hidden="true" />
          History
        </NavLink>
      </nav>
    </header>
  )
}
